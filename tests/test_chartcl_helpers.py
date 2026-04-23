"""Tests for core.parsers.chartcl_helpers."""
import os
import pytest
from core.parsers.chartcl_helpers import (
    read_chartcl,
    parse_chartcl_for_cells,
    parse_chartcl_for_inc,
)

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'chartcl')


def test_read_chartcl_returns_raw_string():
    content = read_chartcl(os.path.join(FIX, 'general_set_vars.tcl'))
    assert isinstance(content, str)
    assert 'constraint_glitch_peak' in content


def test_parse_chartcl_for_cells_extracts_list():
    cells = parse_chartcl_for_cells(os.path.join(FIX, 'set_cells.tcl'))
    assert cells == ['AND2X1', 'AND2X2', 'OR2X1', 'OR2X2', 'DFFQ1']


def test_parse_chartcl_for_cells_empty_when_absent():
    cells = parse_chartcl_for_cells(os.path.join(FIX, 'general_set_vars.tcl'))
    assert cells == []


def test_parse_chartcl_for_inc_traditional_entry():
    inc = parse_chartcl_for_inc(os.path.join(FIX, 'extsim_model_include.tcl'))
    # MCQC parity: entry without -type goes under 'traditional'
    assert inc['traditional'] == '/server/path/base_model.inc'


def test_parse_chartcl_for_inc_per_arc_entries():
    inc = parse_chartcl_for_inc(os.path.join(FIX, 'extsim_model_include.tcl'))
    assert inc['hold']  == '/server/path/hold_model.inc'
    assert inc['mpw']   == '/server/path/mpw_model.inc'
    assert inc['delay'] == '/server/path/delay_model.inc'
