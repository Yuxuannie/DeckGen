"""Tests for core.parsers.template_tcl - Liberty template.tcl parser."""
import os
import pytest
from core.parsers.template_tcl import parse_template_tcl, lookup_slew_load


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEMPLATE_TCL_CONTENT = """\
lu_table_template "delay_template_5x5" {
  variable_1 : input_net_transition;
  variable_2 : total_output_net_capacitance;
  index_1 ("0.05 0.1 0.2 0.5 1.0");
  index_2 ("0.0005 0.001 0.005 0.01 0.05");
}
lu_table_template "hold_template_5x5" {
  variable_1 : constrained_pin_transition;
  variable_2 : related_pin_transition;
  variable_3 : total_output_net_capacitance;
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
  index_3 ("0.001 0.01");
}
"""


@pytest.fixture
def tcl_file(tmp_path):
    p = tmp_path / 'template.tcl'
    p.write_text(TEMPLATE_TCL_CONTENT)
    return str(p)


@pytest.fixture
def parsed(tcl_file):
    return parse_template_tcl(tcl_file)


# ---------------------------------------------------------------------------
# parse_template_tcl
# ---------------------------------------------------------------------------

class TestParsing:
    def test_templates_discovered(self, parsed):
        assert 'delay_template_5x5' in parsed['templates']
        assert 'hold_template_5x5' in parsed['templates']

    def test_delay_index1(self, parsed):
        idx = parsed['templates']['delay_template_5x5']['index_1']
        assert idx == [0.05, 0.1, 0.2, 0.5, 1.0]

    def test_delay_index2(self, parsed):
        idx = parsed['templates']['delay_template_5x5']['index_2']
        assert idx == [0.0005, 0.001, 0.005, 0.01, 0.05]

    def test_hold_index3(self, parsed):
        idx = parsed['templates']['hold_template_5x5']['index_3']
        assert idx == [0.001, 0.01]

    def test_global_fallback_set(self, parsed):
        # Global should pick up first index_1 encountered
        assert 'index_1' in parsed['global']
        assert len(parsed['global']['index_1']) == 5


# ---------------------------------------------------------------------------
# lookup_slew_load - delay arc
# ---------------------------------------------------------------------------

class TestLookupDelay:
    """For delay arcs: index_1=input slew, index_2=output load."""

    def test_i1_1_i2_1(self, parsed):
        r = lookup_slew_load(parsed, i1=1, i2=1, template_name='delay_template_5x5',
                             arc_type='delay')
        # index_1[0] = 0.05 ns -> "0.05n"
        assert r['rel_pin_slew'] == '0.05n'
        assert r['constr_pin_slew'] == '0.05n'
        # index_2[0] = 0.0005 pF; < 1e-3 so _format_load uses aF: 0.0005*1e6 = 500a
        assert r['output_load'] == '500a'

    def test_i1_5_is_last_entry(self, parsed):
        r = lookup_slew_load(parsed, i1=5, i2=5, template_name='delay_template_5x5',
                             arc_type='delay')
        assert r['rel_pin_slew'] == '1n'
        assert r['output_load'] == '50f'

    def test_max_slew_is_max_index1(self, parsed):
        r = lookup_slew_load(parsed, i1=1, i2=1, template_name='delay_template_5x5',
                             arc_type='delay')
        # max of [0.05, 0.1, 0.2, 0.5, 1.0] = 1.0 -> "1n"
        assert r['max_slew'] == '1n'

    def test_falls_back_to_global_when_template_missing(self, parsed):
        r = lookup_slew_load(parsed, i1=1, i2=1, template_name='nonexistent',
                             arc_type='delay')
        # Should fall back to global (first template's data)
        assert r['rel_pin_slew'] is not None


# ---------------------------------------------------------------------------
# lookup_slew_load - constraint arc (hold/setup)
# ---------------------------------------------------------------------------

class TestLookupConstraint:
    """For hold arcs: index_1=constr_pin slew, index_2=rel_pin slew, index_3=load."""

    def test_i1_1_constr_slew(self, parsed):
        r = lookup_slew_load(parsed, i1=1, i2=1, template_name='hold_template_5x5',
                             arc_type='hold')
        # index_1[0] = 0.1 -> "0.1n"
        assert r['constr_pin_slew'] == '0.1n'

    def test_i2_2_rel_slew(self, parsed):
        r = lookup_slew_load(parsed, i1=1, i2=2, template_name='hold_template_5x5',
                             arc_type='hold')
        # index_2[1] = 0.1 -> "0.1n"
        assert r['rel_pin_slew'] == '0.1n'

    def test_output_load_from_index3(self, parsed):
        r = lookup_slew_load(parsed, i1=1, i2=1, template_name='hold_template_5x5',
                             arc_type='hold')
        # index_3[0] = 0.001 pF -> 0.001*1e3 fF = 1f
        assert r['output_load'] == '1f'

    def test_setup_treated_same_as_hold(self, parsed):
        r = lookup_slew_load(parsed, i1=1, i2=1, template_name='hold_template_5x5',
                             arc_type='setup')
        assert r['constr_pin_slew'] is not None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_out_of_range_index_returns_none(self, parsed):
        r = lookup_slew_load(parsed, i1=99, i2=99, template_name='delay_template_5x5',
                             arc_type='delay')
        assert r['rel_pin_slew'] is None
        assert r['output_load'] is None

    def test_none_indices(self, parsed):
        r = lookup_slew_load(parsed, i1=None, i2=None, template_name='delay_template_5x5',
                             arc_type='delay')
        assert r['rel_pin_slew'] is None

    def test_empty_parsed(self, parsed):
        empty = {'templates': {}, 'global': {}}
        r = lookup_slew_load(empty, i1=1, i2=1, arc_type='delay')
        assert r['rel_pin_slew'] is None
        assert r['output_load'] is None
        assert r['max_slew'] is None
