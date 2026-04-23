"""
End-to-end tests: 2 arcs x 2 corners = 4 decks.

Uses:
  - Real templates from templates/min_pulse_width/
  - Synthetic DFFQ1 netlist written to tmp_path
  - Fake (non-existent) model/waveform paths (resolver only checks non-empty)
  - core.batch.plan_jobs + execute_jobs
"""
import os
import pytest
from core.batch import plan_jobs, execute_jobs, run_batch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DFFQ1_NETLIST = """\
* Synthetic DFFQ1 netlist for testing
.subckt DFFQ1 VDD VSS CP D Q SE SI
* (body omitted)
.ends DFFQ1
"""

ARC_IDS = [
    # hold arc: CP/rise, constr_dir=fall (opposite) -> template__CP__rise__fall__1.sp
    'hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1',
    # hold arc: CP/fall, constr_dir=rise (opposite) -> template__CP__fall__rise__1.sp
    'hold_DFFQ1_Q_fall_CP_fall_NO_CONDITION_1_1',
]

CORNER_NAMES = [
    'ssgnp_0p450v_m40c',
    'ttgnp_0p800v_25c',
]


@pytest.fixture
def netlist_dir(tmp_path):
    """Create a tmp directory with a synthetic DFFQ1 netlist."""
    # NetlistResolver tries suffixes: _c_qa.spi, _c.spi, .spi, .sp, .spice
    p = tmp_path / 'DFFQ1_c.spi'
    p.write_text(DFFQ1_NETLIST)
    return str(tmp_path)


@pytest.fixture
def output_dir(tmp_path):
    out = tmp_path / 'output'
    out.mkdir()
    return str(out)


@pytest.fixture
def files(netlist_dir):
    return {
        'netlist_dir':      netlist_dir,
        'netlist':          '',
        'model':            '/fake/model.spi',
        'waveform':         '/fake/waveform.spi',
        'template_tcl_dir': '',
    }


# ---------------------------------------------------------------------------
# plan_jobs
# ---------------------------------------------------------------------------

class TestPlanJobs:
    def test_returns_four_jobs(self, files):
        jobs, errors = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        assert len(jobs) == 4

    def test_no_fatal_errors(self, files):
        _, errors = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        assert errors == []

    def test_all_jobs_have_template(self, files):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        for job in jobs:
            assert job['template'] is not None, f"Job {job['id']} has no template"
            assert job['error'] is None, f"Job {job['id']} has error: {job['error']}"

    def test_job_ids_sequential(self, files):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        ids = [j['id'] for j in jobs]
        assert ids == list(range(1, 5))

    def test_corner_vdd_parsed(self, files):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        vdds = {j['corner']: j['vdd'] for j in jobs}
        assert vdds['ssgnp_0p450v_m40c'] == '0.450'
        assert vdds['ttgnp_0p800v_25c']  == '0.800'

    def test_corner_temp_parsed(self, files):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        temps = {j['corner']: j['temperature'] for j in jobs}
        assert temps['ssgnp_0p450v_m40c'] == '-40'
        assert temps['ttgnp_0p800v_25c']  == '25'

    def test_netlist_resolved(self, files):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        for job in jobs:
            assert job['netlist'] is not None
            assert 'DFFQ1' in job['netlist']

    def test_pins_extracted(self, files):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        for job in jobs:
            assert job['netlist_pins'] is not None
            assert 'CP' in job['netlist_pins']

    def test_invalid_arc_id_is_fatal_error(self, files):
        _, errors = plan_jobs(['garbage'], CORNER_NAMES, files)
        assert len(errors) >= 1

    def test_invalid_corner_is_fatal_error(self, files):
        _, errors = plan_jobs(ARC_IDS, ['bad_corner'], files)
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# execute_jobs
# ---------------------------------------------------------------------------

class TestExecuteJobs:
    def test_four_decks_written(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, files=files)
        ok = [r for r in results if r['success']]
        assert len(ok) == 4

    def test_nominal_files_exist(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, files=files)
        for r in results:
            assert r['success'], f"Job {r['id']} failed: {r['error']}"
            assert os.path.isfile(r['nominal']), f"nominal_sim.sp not found: {r['nominal']}"

    def test_mc_files_exist(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, files=files)
        for r in results:
            assert r['mc'] is not None
            assert os.path.isfile(r['mc']), f"mc_sim.sp not found: {r['mc']}"

    def test_nominal_only_skips_mc(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, nominal_only=True, files=files)
        for r in results:
            assert r['success']
            assert r['mc'] is None
            assert os.path.isfile(r['nominal'])

    def test_corner_dirs_separate(self, files, output_dir):
        """Each arc x corner gets its own subdirectory."""
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, files=files)
        dirs = {os.path.dirname(r['nominal']) for r in results if r['success']}
        assert len(dirs) == 4  # 4 unique output directories

    def test_results_sorted_by_id(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, files=files)
        ids = [r['id'] for r in results]
        assert ids == sorted(ids)

    def test_nominal_deck_nonempty(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, files=files)
        for r in results:
            size = os.path.getsize(r['nominal'])
            assert size > 0, f"nominal_sim.sp is empty for job {r['id']}"

    def test_mc_deck_contains_monte(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        results = execute_jobs(jobs, output_dir, files=files)
        for r in results:
            with open(r['mc']) as f:
                content = f.read()
            assert 'monte=' in content.lower(), \
                f"mc_sim.sp for job {r['id']} missing monte= sweep"

    def test_selected_ids_only_run_selected(self, files, output_dir):
        jobs, _ = plan_jobs(ARC_IDS, CORNER_NAMES, files)
        # Only run jobs 1 and 2
        sel = [j for j in jobs if j['id'] in {1, 2}]
        results = execute_jobs(sel, output_dir, files=files)
        assert len(results) == 2
        assert {r['id'] for r in results} == {1, 2}


# ---------------------------------------------------------------------------
# run_batch (high-level wrapper)
# ---------------------------------------------------------------------------

class TestRunBatch:
    def test_run_batch_returns_four_decks(self, files, output_dir):
        jobs, results, errors = run_batch(
            arc_ids=ARC_IDS,
            corner_names=CORNER_NAMES,
            files=files,
            output_dir=output_dir,
        )
        assert errors == []
        assert len(jobs) == 4
        assert len(results) == 4
        assert all(r['success'] for r in results)

    def test_selected_ids_filter(self, files, output_dir):
        jobs, results, errors = run_batch(
            arc_ids=ARC_IDS,
            corner_names=CORNER_NAMES,
            files=files,
            output_dir=output_dir,
            selected_ids=[1, 3],
        )
        assert len(results) == 2
        assert {r['id'] for r in results} == {1, 3}

    def test_vdd_override_applied(self, files, output_dir):
        """VDD override should appear in the generated deck."""
        jobs, results, errors = run_batch(
            arc_ids=[ARC_IDS[0]],
            corner_names=[CORNER_NAMES[0]],
            files=files,
            overrides={'vdd': '0.999'},
            output_dir=output_dir,
        )
        assert len(results) == 1 and results[0]['success']
        with open(results[0]['nominal']) as f:
            content = f.read()
        assert '0.999' in content


# ---------------------------------------------------------------------------
# Error reporting
# ---------------------------------------------------------------------------

class TestErrorReporting:
    def test_bad_arc_id_reported(self, files):
        _, errors = plan_jobs(['not_an_arc_id'], CORNER_NAMES, files)
        assert len(errors) == 1
        assert 'not_an_arc_id' in errors[0] or 'parse' in errors[0].lower()

    def test_bad_corner_reported(self, files):
        _, errors = plan_jobs(ARC_IDS, ['bad_corner_name'], files)
        assert len(errors) >= 1  # one error per arc that uses the bad corner

    def test_missing_netlist_is_warning_not_error(self, tmp_path):
        """Missing netlist is a warning on the job, not a fatal error."""
        empty_dir = str(tmp_path / 'no_netlists')
        os.makedirs(empty_dir, exist_ok=True)
        files = {
            'netlist_dir': empty_dir,
            'netlist': '',
            'model': '/fake/model.spi',
            'waveform': '/fake/wv.spi',
            'template_tcl_dir': '',
        }
        jobs, errors = plan_jobs([ARC_IDS[0]], [CORNER_NAMES[0]], files)
        # Fatal errors should be empty (bad corner/arc syntax); netlist miss = warning
        assert errors == []
        # The job should have a warning
        assert len(jobs) == 1
        assert len(jobs[0]['warnings']) > 0
