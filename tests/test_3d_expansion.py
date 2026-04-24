"""Tests for 3D constraint expansion (5x5x5 -> 3 arc_info entries)."""
import os
from core.parsers.template_tcl import parse_template_tcl_full
from core.arc_info_builder import build_arc_infos

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


def _setup():
    info = parse_template_tcl_full(os.path.join(FIX, 'constraint_5x5x5.tcl'))
    arc = info['arcs'][0]
    cell = info['cells']['DFFQ1_3D']
    corner = {'process': 'ssgnp', 'vdd': '0.450',
              'temperature': '-40', 'rc_type': 'cworst_CCworst_T',
              'netlist_dir': '/fake'}
    return arc, cell, info, corner


def test_3d_yields_three_arc_infos():
    arc, cell, info, corner = _setup()
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    # MCQC: skip endpoints (0 and 4), keep indices 1, 2, 3 of index_3
    assert len(results) == 3


def test_3d_index_3_values():
    arc, cell, info, corner = _setup()
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    idx3_set = {r['INDEX_3_INDEX'] for r in results}
    assert idx3_set == {'1', '2', '3'}


def test_3d_deck_suffix():
    arc, cell, info, corner = _setup()
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    # Each result has _deck_suffix '-2', '-3', '-4' (MCQC: INDEX_3_INDEX+1)
    suffixes = {r.get('_deck_suffix') for r in results}
    assert suffixes == {'-2', '-3', '-4'}


def test_non_3d_returns_single_result():
    info = parse_template_tcl_full(
        os.path.join(FIX, 'non_cons_full.tcl'))
    arc = info['arcs'][0]
    cell = info['cells']['DFFQ1']
    corner = {'process':'ssgnp','vdd':'0.450','temperature':'-40',
              'rc_type':'cworst_CCworst_T','netlist_dir':'/fake'}
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    assert len(results) == 1
    assert results[0].get('_deck_suffix') in ('', None)
