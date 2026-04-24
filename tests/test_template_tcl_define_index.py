"""Tests for define_index override parsing."""
import os
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


def test_define_index_parsed():
    info = parse_template_tcl_full(os.path.join(FIX, 'define_index_override.tcl'))
    assert 'index_overrides' in info
    assert len(info['index_overrides']) == 1
    o = info['index_overrides'][0]
    assert o['cell']     == 'DFFQ1'
    assert o['pin']      == 'D'
    assert o['rel_pin']  == 'CP'
    assert o['when']     == 'NO_CONDITION'
    assert o['index_1']  == [0.3, 0.6, 0.9, 1.2, 1.5]
    assert o['index_2']  == [0.08, 0.12, 0.16, 0.20, 0.24]


def test_find_define_index_override_helper():
    from core.parsers.template_tcl import find_define_index_override
    info = parse_template_tcl_full(os.path.join(FIX, 'define_index_override.tcl'))
    # matching lookup
    o = find_define_index_override(info['index_overrides'],
                                    cell='DFFQ1', pin='D',
                                    rel_pin='CP', when='NO_CONDITION')
    assert o is not None
    assert o['index_1'] == [0.3, 0.6, 0.9, 1.2, 1.5]

    # miss
    miss = find_define_index_override(info['index_overrides'],
                                       cell='DFFQ1', pin='Q',
                                       rel_pin='CP', when='NO_CONDITION')
    assert miss is None
