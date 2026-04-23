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


class TestParseConditionLoad:
    def test_three_cells_found(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_load.tcl'))
        p.parse_condition_load()
        assert set(p.conditions.keys()) == {'DFFQ1', 'SYNC2DFF', 'LAT1'}

    def test_output_load_indices(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_load.tcl'))
        p.parse_condition_load()
        assert p.conditions['DFFQ1']['OUTPUT_LOAD'] == '2'
        assert p.conditions['SYNC2DFF']['OUTPUT_LOAD'] == '3'
        assert p.conditions['LAT1']['OUTPUT_LOAD'] == '1'

    def test_values_are_strings(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_load.tcl'))
        p.parse_condition_load()
        for cell in p.conditions:
            assert isinstance(p.conditions[cell]['OUTPUT_LOAD'], str)


class TestParseConditionGlitch:
    def test_glitch_values(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_glitch.tcl'))
        p.parse_condition_glitch()
        assert p.conditions['CELLA']['GLITCH'] == '0.05'
        assert p.conditions['CELLB']['GLITCH'] == '0.1'
        assert p.conditions['CELLC']['GLITCH'] == '1e-3'


class TestParseConditionPushout:
    def test_pushout_values(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_pushout.tcl'))
        p.parse_condition_delay_degrade()
        assert p.conditions['DFFQ1']['PUSHOUT_PER'] == '0.25'
        assert p.conditions['SYNC2DFF']['PUSHOUT_PER'] == '0.5'


class TestLastMatchWins:
    def test_later_value_overwrites(self):
        p = ChartclParser(os.path.join(FIX, 'last_match_wins.tcl'))
        p.parse_condition_glitch()
        # MCQC parity: last regex match wins
        assert p.conditions['DFFQ1']['GLITCH'] == '0.2'


class TestAmdSmcDegrade:
    def test_smc_degrade_extracted(self):
        p = ChartclParser(os.path.join(FIX, 'smc_degrade.tcl'))
        p.parse_amd_smc_degrade()
        assert p.vars['smc_degrade'] == '0.25'


class TestAmdGlitch:
    def test_amd_glitch_cells_extracted(self):
        p = ChartclParser(os.path.join(FIX, 'amd_glitch.tcl'))
        p.parse_amd_glitch_high_threshold()
        assert 'amd_glitch' in p.vars
        assert set(p.vars['amd_glitch']['cells']) == {'AND2X1', 'AND2X2', 'OR2X1'}

    def test_amd_glitch_default_glitch(self):
        p = ChartclParser(os.path.join(FIX, 'amd_glitch.tcl'))
        p.parse_amd_glitch_high_threshold()
        # 'set glitch_low_threshold 0.05' -> default_glitch
        assert p.vars['amd_glitch']['default_glitch'] == '0.05'


from core.parsers.chartcl import chartcl_parse_all, resolve_chartcl_for_arc


class TestChartclParseAll:
    def test_wrapper_runs_all_methods(self):
        p = chartcl_parse_all(os.path.join(FIX, 'combined.tcl'))
        assert p.vars['constraint_glitch_peak'] == '0.1'
        assert p.conditions['DFFQ1']['OUTPUT_LOAD'] == '3'
        assert p.conditions['DFFQ1']['GLITCH'] == '0.15'


class TestResolveChartclForArc:
    def _fresh(self):
        return chartcl_parse_all(os.path.join(FIX, 'combined.tcl'))

    def test_global_glitch_used_when_no_cell_condition(self):
        p = self._fresh()
        # 'UNKNOWN' cell has no condition -> falls back to constraint_glitch_peak
        v = resolve_chartcl_for_arc(p, 'UNKNOWN', 'hold')
        assert v['GLITCH'] == '0.1'

    def test_cell_glitch_overrides_global(self):
        p = self._fresh()
        # DFFQ1 has per-cell GLITCH=0.15 in combined.tcl
        v = resolve_chartcl_for_arc(p, 'DFFQ1', 'hold')
        assert v['GLITCH'] == '0.15'

    def test_global_pushout_used(self):
        p = self._fresh()
        v = resolve_chartcl_for_arc(p, 'UNKNOWN', 'hold')
        assert v['PUSHOUT_PER'] == '0.4'

    def test_global_output_load_index(self):
        p = self._fresh()
        v = resolve_chartcl_for_arc(p, 'UNKNOWN', 'hold')
        assert v['OUTPUT_LOAD_INDEX'] == '2'

    def test_cell_output_load_overrides_global(self):
        p = self._fresh()
        v = resolve_chartcl_for_arc(p, 'DFFQ1', 'hold')
        assert v['OUTPUT_LOAD_INDEX'] == '3'
