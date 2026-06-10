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
