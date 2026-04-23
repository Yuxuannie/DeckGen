"""Tests for parse_template_tcl_full (extension of template_tcl parser)."""
import os
import pytest
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


@pytest.fixture
def info():
    return parse_template_tcl_full(os.path.join(FIX, 'non_cons_full.tcl'))


class TestTemplatesSection:
    def test_delay_template_found(self, info):
        assert 'delay_template_5x5' in info['templates']
        t = info['templates']['delay_template_5x5']
        assert t['index_1'] == [0.05, 0.1, 0.2, 0.5, 1.0]

    def test_hold_template_found(self, info):
        assert 'hold_template_5x5' in info['templates']


class TestCellsSection:
    def test_cell_pinlist(self, info):
        cell = info['cells']['DFFQ1']
        assert cell['pinlist'] == 'VDD VSS CP D Q SE SI'

    def test_cell_output_pins(self, info):
        assert info['cells']['DFFQ1']['output_pins'] == ['Q']

    def test_cell_template_references(self, info):
        cell = info['cells']['DFFQ1']
        assert cell['delay_template']      == 'delay_template_5x5'
        assert cell['constraint_template'] == 'hold_template_5x5'
        assert cell['mpw_template']        == 'delay_template_5x5'


class TestArcsSection:
    def test_two_arcs_found(self, info):
        assert len(info['arcs']) == 2

    def test_combinational_arc_fields(self, info):
        arc = [a for a in info['arcs'] if a['arc_type'] == 'combinational'][0]
        assert arc['cell']        == 'DFFQ1'
        assert arc['pin']         == 'Q'
        assert arc['pin_dir']     == 'rise'
        assert arc['rel_pin']     == 'CP'
        assert arc['rel_pin_dir'] == 'rise'
        assert arc['when']        == '!SE&SI'
        assert arc['lit_when']    == 'notSE_SI'
        assert arc['probe_list']  == ['Q']
        assert arc['vector']      == 'RxxRxx'

    def test_hold_arc_no_condition(self, info):
        arc = [a for a in info['arcs'] if a['arc_type'] == 'hold'][0]
        assert arc['when'] == 'NO_CONDITION'


class TestLegacyCompatibility:
    def test_old_parse_template_tcl_still_works(self):
        from core.parsers.template_tcl import parse_template_tcl
        old = parse_template_tcl(os.path.join(FIX, 'non_cons_full.tcl'))
        # existing key 'templates' preserved
        assert 'delay_template_5x5' in old['templates']
