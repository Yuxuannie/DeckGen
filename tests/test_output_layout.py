"""Verify MCQC-matching output directory layout when collateral is used."""
import os
import shutil
import pytest
from core.batch import run_batch

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE   = 'N2P_v1.0'
LIB    = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), NODE, LIB)
    return str(dest)


def test_output_layout_matches_mcqc(tmp_path, collateral_root):
    arc_id = 'hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1'
    out = tmp_path / 'output'
    jobs, results, errors = run_batch(
        arc_ids=[arc_id],
        corner_names=[CORNER],
        files={},
        output_dir=str(out),
        node=NODE, lib_type=LIB,
        collateral_root=collateral_root,
        nominal_only=True)
    assert not errors, errors
    assert results, "No results returned"
    r = results[0]
    assert r['success'], r.get('error')
    # Expect: output/{LIB}/{CORNER}/hold/{arc_id}/nominal_sim.sp
    expected = out / LIB / CORNER / 'hold' / arc_id / 'nominal_sim.sp'
    assert expected.is_file(), (
        f"Expected {expected}; got nominal={r.get('nominal')}")


def test_legacy_layout_no_lib_type(tmp_path):
    """Without lib_type, old corner-suffix layout is preserved."""
    from core.batch import plan_jobs, execute_jobs
    import tempfile

    # Minimal netlist
    nl = tmp_path / 'DFFQ1_c.spi'
    nl.write_text('.subckt DFFQ1 VDD VSS CP D Q SE SI\n.ends DFFQ1\n')
    files = {
        'netlist_dir': str(tmp_path),
        'model':       '/fake/model.spi',
        'waveform':    '/fake/waveform.spi',
    }
    arc_id = 'hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1'
    corner = 'ssgnp_0p450v_m40c'
    jobs, errors = plan_jobs([arc_id], [corner], files)
    assert not errors
    out = tmp_path / 'legacy_out'
    out.mkdir()
    results = execute_jobs(jobs, str(out), nominal_only=True, files=files)
    r = results[0]
    assert r['success'], r.get('error')
    # Legacy layout: output/{deck_dirname}_{corner}/nominal_sim.sp
    # arc_id must NOT appear as a path component named verbatim
    nom = r['nominal']
    assert nom is not None
    # Must NOT contain the MCQC sub-structure lib_type/corner/arc_type/arc_id
    parts = nom.replace(str(out), '').lstrip('/').split('/')
    # Legacy: depth 2 (dirname + nominal_sim.sp)
    assert len(parts) == 2, f"Expected legacy 2-part path, got {parts}"
