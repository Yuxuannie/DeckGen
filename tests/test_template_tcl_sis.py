"""Tests for SIS template sidecar parsing."""
import os
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


def test_sis_sidecar_parsed():
    info = parse_template_tcl_full(os.path.join(FIX, 'sis_sidecar.tcl'))
    assert 'sis' in info
    sis = info['sis']
    assert 'O' in sis
    assert sis['O']['glitch_high_threshold'] == '0.35'
    assert sis['O']['glitch_low_threshold']  == '0.1'
    assert sis['I']['glitch_high_threshold'] == '0.40'


def test_sis_sidecar_missing_ok():
    info = parse_template_tcl_full(os.path.join(FIX, 'non_cons_full.tcl'))
    # non_cons_full.tcl has no matching .sis file -> 'sis' key absent or empty
    assert info.get('sis', {}) == {}


def test_sis_fields_in_arc_info():
    """When a cell has output pins, their pintype glitch thresholds flow into arc_info."""
    from core.arc_info_builder import build_arc_info
    info = parse_template_tcl_full(os.path.join(FIX, 'sis_sidecar.tcl'))
    arc = info['arcs'][0]
    cell = info['cells']['DFFQ1']
    corner = {'process':'ssgnp','vdd':'0.450','temperature':'-40',
              'rc_type':'cworst_CCworst_T','netlist_dir':'/fake'}
    ai = build_arc_info(arc, cell, info, None, corner,
                        netlist_path='', netlist_pins='',
                        include_file='', waveform_file='',
                        overrides={'index_1_index': 1, 'index_2_index': 1})
    # 'Q' is output -> pintype 'O' -> injected as O_GLITCH_HIGH_THRESHOLD
    assert ai.get('O_GLITCH_HIGH_THRESHOLD') == '0.35'
    assert ai.get('O_GLITCH_LOW_THRESHOLD')  == '0.1'
