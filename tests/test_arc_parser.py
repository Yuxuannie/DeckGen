"""Tests for core.parsers.arc - cell_arc_pt identifier parser."""
import pytest
from core.parsers.arc import parse_arc_identifier, parse_arc_list


# ---------------------------------------------------------------------------
# parse_arc_identifier
# ---------------------------------------------------------------------------

class TestCombinationalNoCondition:
    ID = 'combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4'

    def test_arc_type(self):
        r = parse_arc_identifier(self.ID)
        assert r['arc_type'] == 'combinational'

    def test_cell_name(self):
        r = parse_arc_identifier(self.ID)
        assert r['cell_name'] == 'ND2MDLIMZD0P7BWP130HPNPN3P48CPD'

    def test_probe(self):
        r = parse_arc_identifier(self.ID)
        assert r['probe_pin'] == 'ZN'
        assert r['probe_dir'] == 'rise'

    def test_rel(self):
        r = parse_arc_identifier(self.ID)
        assert r['rel_pin'] == 'A1'
        assert r['rel_dir'] == 'fall'

    def test_when(self):
        r = parse_arc_identifier(self.ID)
        assert r['when'] == 'NO_CONDITION'

    def test_indices(self):
        r = parse_arc_identifier(self.ID)
        assert r['i1'] == 4
        assert r['i2'] == 4

    def test_raw_preserved(self):
        r = parse_arc_identifier(self.ID)
        assert r['raw'] == self.ID


class TestCombinationalWithWhen:
    ID = ('combinational_MUX4MDLIMZD0P7BWP130HPNPN3P48CPD_Z_rise_S1_rise'
          '_notI0_notI1_notI2_I3_S0_4_4')

    def test_when_condition(self):
        r = parse_arc_identifier(self.ID)
        assert r['when'] == '!I0&!I1&!I2&I3&S0'

    def test_cell_and_pins(self):
        r = parse_arc_identifier(self.ID)
        assert r['cell_name'] == 'MUX4MDLIMZD0P7BWP130HPNPN3P48CPD'
        assert r['probe_pin'] == 'Z'
        assert r['rel_pin'] == 'S1'

    def test_indices(self):
        r = parse_arc_identifier(self.ID)
        assert r['i1'] == 4
        assert r['i2'] == 4


class TestHoldArc:
    ID = 'hold_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2'

    def test_arc_type(self):
        r = parse_arc_identifier(self.ID)
        assert r['arc_type'] == 'hold'

    def test_indices(self):
        r = parse_arc_identifier(self.ID)
        assert r['i1'] == 3
        assert r['i2'] == 2

    def test_when(self):
        r = parse_arc_identifier(self.ID)
        assert r['when'] == '!SE&SI'

    def test_cell_and_pins(self):
        r = parse_arc_identifier(self.ID)
        assert r['cell_name'] == 'DFFQ1'
        assert r['probe_pin'] == 'Q'
        assert r['rel_pin'] == 'CP'


class TestSetupArc:
    ID = 'setup_DFFQ1_Q_rise_CP_rise_NO_CONDITION_2_3'

    def test_arc_type(self):
        r = parse_arc_identifier(self.ID)
        assert r['arc_type'] == 'setup'

    def test_when(self):
        r = parse_arc_identifier(self.ID)
        assert r['when'] == 'NO_CONDITION'


class TestMinPulseWidthArc:
    ID = 'min_pulse_width_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1'

    def test_arc_type(self):
        r = parse_arc_identifier(self.ID)
        assert r['arc_type'] == 'min_pulse_width'

    def test_indices(self):
        r = parse_arc_identifier(self.ID)
        assert r['i1'] == 1
        assert r['i2'] == 1


class TestDifferentIndices:
    """Verify various i1/i2 combinations are parsed correctly."""

    def test_1_1(self):
        r = parse_arc_identifier('hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1')
        assert r['i1'] == 1 and r['i2'] == 1

    def test_7_3(self):
        r = parse_arc_identifier('hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_7_3')
        assert r['i1'] == 7 and r['i2'] == 3


class TestInvalidInputs:
    def test_garbage(self):
        assert parse_arc_identifier('garbage') is None

    def test_empty_string(self):
        assert parse_arc_identifier('') is None

    def test_whitespace_only(self):
        assert parse_arc_identifier('   ') is None

    def test_too_few_parts(self):
        # Fewer than 8 tokens
        assert parse_arc_identifier('hold_A_B_rise') is None

    def test_no_direction_keywords(self):
        # No rise/fall tokens
        assert parse_arc_identifier('hold_DFFQ1_Q_up_CP_up_NO_CONDITION_1_1') is None


# ---------------------------------------------------------------------------
# parse_arc_list
# ---------------------------------------------------------------------------

class TestParseArcList:
    def test_newline_separated(self):
        text = (
            'combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4\n'
            'hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_3_2'
        )
        results = parse_arc_list(text)
        assert len(results) == 2
        assert results[0]['arc_type'] == 'combinational'
        assert results[1]['arc_type'] == 'hold'

    def test_skips_invalid_lines(self):
        text = 'garbage\nhold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1\nbad'
        results = parse_arc_list(text)
        assert len(results) == 1
        assert results[0]['arc_type'] == 'hold'

    def test_empty_text(self):
        assert parse_arc_list('') == []

    def test_blank_lines_ignored(self):
        text = '\n\nhold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1\n\n'
        assert len(parse_arc_list(text)) == 1
