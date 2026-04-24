"""Tests for core.arc_info_builder.build_arc_info (non-cons subset)."""
import os
import pytest
from core.arc_info_builder import build_arc_info, format_index_value
from core.parsers.chartcl import chartcl_parse_all
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def template_info():
    return parse_template_tcl_full(
        os.path.join(FIX, 'template_tcl', 'non_cons_full.tcl'))


@pytest.fixture
def chartcl():
    return chartcl_parse_all(
        os.path.join(FIX, 'collateral', 'N2P_v1.0', 'test_lib', 'Char',
                     'char_test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.non_cons.tcl'))


@pytest.fixture
def delay_arc(template_info):
    return [a for a in template_info['arcs']
            if a['arc_type'] == 'combinational'][0]


@pytest.fixture
def dffq1_cell(template_info):
    return template_info['cells']['DFFQ1']


@pytest.fixture
def fake_corner():
    return {
        'process':     'ssgnp',
        'vdd':         '0.450',
        'temperature': '-40',
        'rc_type':     'cworst_CCworst_T',
        'netlist_dir': '/fake/netlist/dir',
    }


class TestCoreFields:
    def test_cell_and_arc_type(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='/fake/DFFQ1_c.spi', netlist_pins='VDD VSS CP D Q SE SI',
            include_file='/fake/model.delay.inc', waveform_file='/fake/wv.spi',
            overrides={})
        assert info['CELL_NAME'] == 'DFFQ1'
        assert info['ARC_TYPE']  == 'combinational'

    def test_rel_and_constr_pins(self, delay_arc, dffq1_cell, template_info,
                                  chartcl, fake_corner):
        # non-cons: CONSTR_PIN == REL_PIN
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='/fake', netlist_pins='',
            include_file='', waveform_file='', overrides={})
        assert info['REL_PIN']    == 'CP'
        assert info['CONSTR_PIN'] == 'CP'
        assert info['REL_PIN_DIR']    == 'rise'
        assert info['CONSTR_PIN_DIR'] == 'rise'

    def test_probe_pin_1(self, delay_arc, dffq1_cell, template_info,
                          chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='/fake', netlist_pins='',
            include_file='', waveform_file='', overrides={})
        assert info['PROBE_PIN_1'] == 'Q'


class TestWhenFields:
    def test_when_and_lit_when_separate(self, delay_arc, dffq1_cell,
                                         template_info, chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='',
            include_file='', waveform_file='', overrides={})
        assert info['WHEN']     == '!SE&SI'
        assert info['LIT_WHEN'] == 'notSE_SI'


class TestVectorAndPinlist:
    def test_vector_propagated(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['VECTOR'] == 'RxxRxx'

    def test_template_pinlist(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['TEMPLATE_PINLIST'] == 'VDD VSS CP D Q SE SI'


class TestIndexValues:
    def test_index_1_value_nanoseconds(self, delay_arc, dffq1_cell,
                                         template_info, chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={'index_1_index': 1, 'index_2_index': 1})
        # index_1 = [0.05, 0.1, 0.2, 0.5, 1.0], index at 1 = 0.05
        assert info['INDEX_1_VALUE'] == '0.05n'

    def test_index_2_value_picoseconds_for_non_cons(self, delay_arc,
                                                      dffq1_cell, template_info,
                                                      chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={'index_1_index': 1, 'index_2_index': 1})
        # non-cons: INDEX_2_VALUE suffix is 'p'
        assert info['INDEX_2_VALUE'].endswith('p')


class TestEnvironmentFields:
    def test_vdd_and_temp_from_corner(self, delay_arc, dffq1_cell,
                                        template_info, chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['VDD_VALUE']   == '0.450'
        assert info['TEMPERATURE'] == '-40'

    def test_override_vdd_wins(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={'vdd': '0.999'})
        assert info['VDD_VALUE'] == '0.999'


class TestChartclFields:
    def test_glitch_from_chartcl(self, delay_arc, dffq1_cell, template_info,
                                   chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        # non_cons.tcl has constraint_glitch_peak 0.05
        assert info['GLITCH'] == '0.05'

    def test_pushout_from_chartcl(self, delay_arc, dffq1_cell, template_info,
                                    chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['PUSHOUT_PER'] == '0.25'


class TestFormatIndexValue:
    def test_nanosecond_suffix(self):
        assert format_index_value(0.05, 'n') == '0.05n'

    def test_picosecond_suffix(self):
        assert format_index_value(0.5, 'p') == '0.5p'

    def test_integer_value(self):
        assert format_index_value(1.0, 'n') == '1n'


class TestDefineIndexOverride:
    def test_define_index_overrides_template_indices(self):
        from core.parsers.template_tcl import parse_template_tcl_full
        from core.arc_info_builder import build_arc_info
        import os
        FIX2 = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')
        info = parse_template_tcl_full(os.path.join(FIX2, 'define_index_override.tcl'))
        arc = info['arcs'][0]
        cell = info['cells']['DFFQ1']
        corner = {'process':'ssgnp','vdd':'0.450','temperature':'-40',
                  'rc_type':'cworst_CCworst_T','netlist_dir':'/fake'}
        # With override, index_1[0] should be 0.3 (from define_index), NOT 0.1 (from template)
        result = build_arc_info(arc, cell, info, None, corner,
                                netlist_path='', netlist_pins='',
                                include_file='', waveform_file='',
                                overrides={'index_1_index': 1, 'index_2_index': 1})
        assert result['INDEX_1_VALUE'] == '0.3n'
        # index_2[0] overridden: 0.08; suffix 'n' for hold
        assert result['INDEX_2_VALUE'] == '0.08n'
