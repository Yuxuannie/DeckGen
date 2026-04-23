"""Tests for core.parsers.chartcl -- faithful MCQC ChartclParser port."""
import os
import pytest
from core.parsers.chartcl import ChartclParser

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'chartcl')


class TestParseSetVarGeneral:
    """MCQC parity: values stored as strings, NOT numeric."""

    def test_all_three_vars_found(self):
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        assert p.vars['constraint_glitch_peak'] == '0.1'
        assert p.vars['constraint_delay_degrade'] == '0.4'
        assert p.vars['constraint_output_load'] == '2'  # 'index_' prefix stripped

    def test_index_prefix_stripped(self):
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        assert not p.vars['constraint_output_load'].startswith('index_')

    def test_values_are_strings(self):
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        for key in ('constraint_glitch_peak', 'constraint_delay_degrade',
                    'constraint_output_load'):
            assert isinstance(p.vars[key], str)

    def test_stage_variation_form(self):
        """-stage variation constraint_delay_degrade recognized."""
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        assert p.vars['constraint_delay_degrade'] == '0.4'


class TestParseSetVarMpw:
    def test_mpw_input_threshold_found(self):
        p = ChartclParser(os.path.join(FIX, 'mpw_set_vars.tcl'), variant='mpw')
        p.parse_set_var()
        assert p.vars['mpw_input_threshold'] == '0.5'

    def test_sentinel_stops_parsing(self):
        p = ChartclParser(os.path.join(FIX, 'mpw_set_vars.tcl'), variant='mpw')
        p.parse_set_var()
        assert 'this_must_be_ignored' not in p.vars

    def test_mpw_vars_found(self):
        p = ChartclParser(os.path.join(FIX, 'mpw_set_vars.tcl'), variant='mpw')
        p.parse_set_var()
        assert p.vars['constraint_glitch_peak'] == '0.05'
        assert p.vars['constraint_delay_degrade'] == '0.3'
        assert p.vars['constraint_output_load'] == '1'
