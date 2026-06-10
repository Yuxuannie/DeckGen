"""core/verify_sidecar.py -- v1 -> engine adapter for the --verify audit layer.
Spec: docs/superpowers/specs/2026-06-09-v2-audit-sidecar-design.md
"""
import json
import os

import pytest

from core.verify_sidecar import build_record, to_lit_when

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arc_info(**over):
    """Minimal collateral-path arc_info (spec section 3.1)."""
    info = {
        'CELL_NAME': 'DFFQ1', 'ARC_TYPE': 'hold',
        'REL_PIN': 'CP', 'REL_PIN_DIR': 'rise',
        'CONSTR_PIN': 'D', 'CONSTR_PIN_DIR': 'fall',
        'WHEN': '!SE&SI', 'LIT_WHEN': 'notSE_SI',
        'VECTOR': 'xxRxFxx',
        'PROBE_PIN_1': 'Q',
        'NETLIST_PATH': '/no/such.spi', 'INCLUDE_FILE': '/no/model.inc',
        'VDD_VALUE': '0.45', 'SIDE_PIN_STATES': '',
    }
    info.update(over)
    return info


class TestToLitWhen:
    def test_literal_converts(self):
        assert to_lit_when('!SE&SI') == 'notSE_SI'

    def test_multi_term(self):
        assert to_lit_when('!I0 & !I1 & I2') == 'notI0_notI1_I2'

    def test_no_condition_is_empty(self):
        assert to_lit_when('NO_CONDITION') == ''
        assert to_lit_when('') == ''
        assert to_lit_when(None) == ''


class TestBuildRecord:
    def test_collateral_fields(self):
        rec = build_record(_arc_info(), {'arc_id': 'a1', 'corner': 'c1'})
        assert rec['cell'] == 'DFFQ1'
        assert rec['arc_type'] == 'hold'
        assert rec['rel_pin'] == 'CP' and rec['rel_dir'] == 'rise'
        assert rec['constr_pin'] == 'D' and rec['constr_dir'] == 'fall'
        assert rec['when'] == 'notSE_SI'          # LIT_WHEN verbatim
        assert rec['when_literal'] == '!SE&SI'
        assert rec['vector'] == 'xxRxFxx'
        assert rec['probe_list'] == ['Q']
        assert rec['arc_id'] == 'a1' and rec['corner'] == 'c1'

    def test_no_condition_normalizes_to_empty(self):
        # Spec 3.1: the sentinel must never reach parse_when as a token.
        rec = build_record(_arc_info(WHEN='NO_CONDITION',
                                     LIT_WHEN='NO_CONDITION'), None)
        assert rec['when'] == ''

    def test_legacy_when_converted(self):
        # legacy arc_info (from _job_to_arc_info) has no WHEN/LIT_WHEN keys
        info = _arc_info()
        for k in ('WHEN', 'LIT_WHEN', 'VECTOR'):
            del info[k]
        rec = build_record(info, {'when': '!SE&SI', 'probe_pin': 'Q'})
        assert rec['when'] == 'notSE_SI'
        assert rec['vector'] == ''
        assert rec['probe_list'] == ['Q']

    def test_probe_list_numeric_order(self):
        rec = build_record(_arc_info(PROBE_PIN_2='QN'), None)
        assert rec['probe_list'] == ['Q', 'QN']

    def test_engine_version_constant_exists(self):
        import engine
        assert engine.__version__ == '2.0-2b'


from core.verify_sidecar import extract_meas_block

DECK_LINES = [
    "* Slew and load information\n",
    ".param cl = '0.001p'\n",
    "* Measurements\n",
    ".meas cp2q_del1 trig v(CP) val='vdd_value/2' cross=3 targ v(Q) val='vdd_value/2' cross=1 td='related_pin_t03'\n",
    ".meas cp2cp trig v(CP) val='vdd_value/2' cross=3 targ v(D) val='vdd_value/2' cross=4\n",
    " \n",
    "* Transient Sim Command\n",
    ".tran 1p 50u sweep monte=1\n",
    ".end\n",
]


class TestExtractMeasBlock:
    def test_marker_block_extracted(self):
        meas, note = extract_meas_block(DECK_LINES)
        assert note is None
        assert meas.count('.meas') == 2
        assert '.tran' not in meas

    def test_no_marker_falls_back_to_meas_lines(self):
        lines = [l for l in DECK_LINES if 'Measurements' not in l]
        meas, note = extract_meas_block(lines)
        assert note is None
        assert meas.count('.meas') == 2

    def test_nothing_found_is_loud(self):
        # Spec 3.3: an empty meas block is NEVER silent.
        lines = [l for l in DECK_LINES if '.meas' not in l
                 and 'Measurements' not in l]
        meas, note = extract_meas_block(lines)
        assert meas == ''
        assert note is not None and 'meas extraction failed' in note


from core.verify_sidecar import classify_bias_match, derive_golden_biases


class TestGoldenBiases:
    def test_from_when_literal_skips_driven_pins(self):
        # mirrors deck_builder._generate_when_condition_lines semantics
        g = derive_golden_biases(_arc_info(WHEN='!SE&SI&D'))
        assert g == {'SE': 0, 'SI': 1}      # D is the constr pin -> skipped

    def test_side_pin_states_wins(self):
        g = derive_golden_biases(_arc_info(SIDE_PIN_STATES='SE=1 SI=0'))
        assert g == {'SE': 1, 'SI': 0}

    def test_no_condition_empty(self):
        assert derive_golden_biases(_arc_info(WHEN='NO_CONDITION')) == {}


class TestBiasMatch:
    # spec section 5: per-pin three-state, masked pins are NEVER mismatches
    def test_match(self):
        out = classify_bias_match({'SE': 0, 'SI': 1}, ['SE'], ['SI'],
                                  {'SE': 0, 'SI': 1})
        assert out == 'MATCH'

    def test_critical_mismatch(self):
        out = classify_bias_match({'SE': 1, 'SI': 1}, ['SE'], ['SI'],
                                  {'SE': 0, 'SI': 1})
        assert out.startswith('MISMATCH:') and 'SE' in out

    def test_masked_disagreement_is_not_mismatch(self):
        out = classify_bias_match({'SE': 0, 'SI': 1}, ['SE'], ['SI'],
                                  {'SE': 0, 'SI': 0})
        assert out.startswith('MATCH')
        assert 'non-critical' in out and 'SI' in out

    def test_only_masked_compared(self):
        out = classify_bias_match({'SI': 1}, [], ['SI'], {'SI': 0})
        assert out == 'NON_CRITICAL'

    def test_no_golden(self):
        out = classify_bias_match({'SE': 0}, ['SE'], [], {})
        assert out.startswith('N/A')


from core.verify_sidecar import build_meas_context

# Substituted v1 deck shape -- the worked example from the spec
# (mpw/template__CP__rise__fall__1.sp with max_slew = 1n).
WORKED_DECK = [
    ".param max_slew = '1n'\n",
    ".param search_window = '1n'\n",
    ".param opt_init = '5 * search_window'\n",
    ".param constr_pin_offset = opt_init\n",
    ".param related_pin_t01 = '10 * max_slew'\n",
    ".param related_pin_t02 = '20 * max_slew'\n",
    ".param related_pin_t03 = '50 * max_slew'\n",
    ".param related_pin_t04 = '50 * max_slew + constr_pin_offset'\n",
    "XVCP CP 0 stdvs_mpw_rise_fall_rise_fall VDD='vdd_value' slew='rel_pin_slew'"
    " t01='related_pin_t01' t02='related_pin_t02' t03='related_pin_t03'"
    " t04='related_pin_t04'\n",
    "* Measurements\n",
    ".meas cp2q_del1 trig v(CP) val='vdd_value/2' cross=3 targ v(Q)"
    " val='vdd_value/2' cross=1 td='related_pin_t03'\n",
    ".tran 1p 50u sweep monte=1\n",
]


class TestBuildMeasContext:
    def test_worked_example(self):
        ctx = build_meas_context(WORKED_DECK, _arc_info())
        assert [(t, d) for _, t, d in ctx.rel_edges] == \
            [(10.0, 'rise'), (20.0, 'fall'), (50.0, 'rise'), (55.0, 'fall')]
        assert ctx.trig_cross == 3
        assert ctx.trig_td_ns == 0.0          # td is in the TARG clause
        assert ctx.capture_t_ns == 50.0       # 3rd crossing from t=0 = rise@t03
        assert ctx.capture_dir == 'rise'
        assert ctx.vdd == 0.45

    def test_td_moved_into_trig_clause_shifts_the_count(self):
        # Pins the normative convention: only a trig-clause td gates counting.
        lines = [l.replace(
            "cross=3 targ v(Q) val='vdd_value/2' cross=1 td='related_pin_t03'",
            "cross=3 td='related_pin_t03' targ v(Q) val='vdd_value/2' cross=1")
            for l in WORKED_DECK]
        ctx = build_meas_context(lines, _arc_info())
        assert ctx.trig_td_ns == 50.0
        # only 2 edges at/after 50ns -> no 3rd crossing -> unresolved
        assert ctx.capture_t_ns is None
        assert any('cross=3' in n for n in ctx.notes)

    def test_unresolved_param_is_stub_not_crash(self):
        lines = [l.replace("'50 * max_slew'", "'sin(x)'") for l in WORKED_DECK]
        ctx = build_meas_context(lines, _arc_info())
        assert ctx.capture_t_ns is None
        assert any('UNRESOLVED' in n for n in ctx.notes)

    def test_no_toggling_line_is_unresolved(self):
        lines = [l for l in WORKED_DECK if not l.startswith('XVCP')]
        ctx = build_meas_context(lines, _arc_info())
        assert ctx.capture_t_ns is None


import core.verify_sidecar as vs

SDFX = os.path.join(REPO, 'engine', 'fixtures', 'SDFX_LPE_PLACEHOLDER.subckt')


def _sdfx_arc_info(**over):
    info = _arc_info(CELL_NAME='SDFX_LPE_PLACEHOLDER', NETLIST_PATH=SDFX)
    info.update(over)
    return info


class TestWriteSidecar:
    def test_ok_sidecar_on_engine_fixture(self, tmp_path):
        path = vs.write_sidecar(str(tmp_path), _sdfx_arc_info(),
                                {'arc_id': 'a1', 'corner': 'c1'}, WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['schema_version'] == 1
        assert data['status'] == 'OK'
        assert data['arc']['cell'] == 'SDFX_LPE_PLACEHOLDER'
        assert data['verdict']['p1']['status'] == 'PASS'
        assert data['verdict']['p3']['status'] in ('STUB', 'PASS', 'FAIL')
        assert data['engine']['version'] == '2.0-2b'
        assert data['biases']['match'].split()[0] in (
            'MATCH', 'MISMATCH:', 'NON_CRITICAL', 'N/A')
        assert 'derived independently' not in data['arc_check']  # when given
        assert data['timestamps']['started'] <= data['timestamps']['finished']

    def test_missing_netlist_is_error_sidecar(self, tmp_path):
        path = vs.write_sidecar(str(tmp_path),
                                _sdfx_arc_info(NETLIST_PATH='/no/such.spi'),
                                None, WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['status'] == 'ERROR'
        assert 'no netlist text available' in data['error']['summary']
        assert 'verdict' not in data

    def test_engine_exception_yields_error_sidecar(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('boom')
        monkeypatch.setattr(vs, 'run_pipeline_src', boom)
        path = vs.write_sidecar(str(tmp_path), _sdfx_arc_info(), None,
                                WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['status'] == 'ERROR'
        assert data['error']['type'] == 'RuntimeError'
        assert any('boom' in t for t in data['error']['traceback_tail'])
        assert 'verdict' not in data

    def test_stripped_meas_marker_is_loud(self, tmp_path):
        lines = [l for l in WORKED_DECK if '.meas' not in l
                 and 'Measurements' not in l]
        path = vs.write_sidecar(str(tmp_path), _sdfx_arc_info(), None, lines)
        data = json.loads(open(path).read())
        assert data['status'] == 'OK'
        assert any('meas extraction failed' in n for n in data['notes'])
        assert data['verdict']['p3']['status'] == 'STUB'
        assert any('no measurement block found' in d
                   for d in data['verdict']['p3']['detail'])

    def test_no_when_reports_derived_independently(self, tmp_path):
        path = vs.write_sidecar(
            str(tmp_path),
            _sdfx_arc_info(WHEN='NO_CONDITION', LIT_WHEN='NO_CONDITION'),
            None, WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['status'] == 'OK'
        assert 'derived independently' in data['arc_check']


import hashlib
import shutil

from core.batch import run_batch

FIXTURE_COLLATERAL = os.path.join(REPO, 'tests', 'fixtures', 'collateral')
ARC_IDS = ['hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1']
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
_NODE = 'N2P_v1.0'
_LIB = 'test_lib'


def _make_collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_COLLATERAL, _NODE, _LIB),
                    str(dest / _NODE / _LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), _NODE, _LIB)
    return str(dest)


def _tree_hashes(root):
    out = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, root)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return out


def _run(outdir, collateral_root, verify):
    return run_batch(arc_ids=ARC_IDS, corner_names=[CORNER], files={},
                     output_dir=str(outdir), nominal_only=True,
                     node=_NODE, lib_type=_LIB,
                     collateral_root=collateral_root, verify=verify)


class TestVerifyBatch:
    def test_byte_identical_whole_tree(self, tmp_path):
        # Every common output file identical; only verify.json may be added.
        croot = _make_collateral_root(tmp_path)
        coll_before = _tree_hashes(croot)
        _run(tmp_path / 'off', croot, verify=False)
        _run(tmp_path / 'on', croot, verify=True)
        off = _tree_hashes(tmp_path / 'off')
        on = _tree_hashes(tmp_path / 'on')
        on_base = {k: v for k, v in on.items()
                   if os.path.basename(k) != 'verify.json'}
        assert on_base == off
        assert any(os.path.basename(k) == 'verify.json' for k in on)
        # the audit layer must not touch any collateral (v1-maintained) file
        assert _tree_hashes(croot) == coll_before

    def test_sidecar_well_formed_per_job(self, tmp_path):
        croot = _make_collateral_root(tmp_path)
        jobs, results, errors = _run(tmp_path / 'out', croot, verify=True)
        assert not errors
        for r in results:
            if not r['success']:
                continue
            assert r.get('sidecar')
            data = json.loads(open(r['sidecar']).read())
            assert data['schema_version'] == 1
            assert data['status'] in ('OK', 'ERROR')
            assert data['arc']['cell'] == 'DFFQ1'

    def test_engine_crash_does_not_abort_batch(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('boom')
        monkeypatch.setattr(vs, 'run_pipeline_src', boom)
        croot = _make_collateral_root(tmp_path)
        jobs, results, errors = _run(tmp_path / 'out', croot, verify=True)
        ok = [r for r in results if r['success']]
        assert ok                                # decks still written
        for r in ok:
            data = json.loads(open(r['sidecar']).read())
            assert data['status'] == 'ERROR'

    def test_cli_flag_exists(self):
        import deckgen
        import sys as _sys
        argv = _sys.argv
        _sys.argv = ['deckgen.py', '--verify', '--cell', 'X', '--arc_type',
                     'hold', '--rel_pin', 'CP', '--rel_dir', 'rise']
        try:
            args = deckgen.parse_args()
            assert args.verify is True
        finally:
            _sys.argv = argv
