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
