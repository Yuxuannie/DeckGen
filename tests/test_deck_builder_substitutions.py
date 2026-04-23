"""Tests for new MCQC-parity substitutions in deck_builder."""
import pytest
from core.deck_builder import build_deck


def _fake_arc_info(**overrides):
    base = {
        'CELL_NAME': 'DFFQ1', 'ARC_TYPE': 'combinational',
        'REL_PIN': 'CP', 'REL_PIN_DIR': 'rise',
        'CONSTR_PIN': 'CP', 'CONSTR_PIN_DIR': 'rise',
        'PROBE_PIN_1': 'Q',
        'TEMPLATE_DECK_PATH': '',
        'NETLIST_PATH': '/fake/DFFQ1_c.spi',
        'NETLIST_PINS': 'VDD VSS CP D Q SE SI',
        'VDD_VALUE': '0.450', 'TEMPERATURE': '-40',
        'INCLUDE_FILE': '/fake/model.inc',
        'WAVEFORM_FILE': '/fake/wv.spi',
        'GLITCH': '0.1', 'PUSHOUT_PER': '0.4', 'PUSHOUT_DIR': 'high',
        'WHEN': '!SE&SI', 'LIT_WHEN': 'notSE_SI',
        'VECTOR': 'RxxRxx',
        'SIDE_PIN_STATES': 'SE=0 SI=1',
        'DONT_TOUCH_PINS': 'VDD VSS',
        'OUTPUT_PINS': 'Q',
        'TEMPLATE_PINLIST': 'VDD VSS CP D Q SE SI',
        'HEADER_INFO': 'test_header',
        'INDEX_1_INDEX': '1', 'INDEX_1_VALUE': '0.05n',
        'INDEX_2_INDEX': '1', 'INDEX_2_VALUE': '0.5p',
        'INDEX_3_INDEX': '',
        'OUTPUT_LOAD': '0.5p', 'MAX_SLEW': '1n',
    }
    base.update(overrides)
    return base


def test_all_new_vars_substituted(tmp_path):
    """Every new $VAR in a template must be replaced by the arc_info value."""
    tpl = tmp_path / 'test.sp'
    tpl.write_text(
        "* $CELL_NAME $WHEN $LIT_WHEN $VECTOR\n"
        "* $SIDE_PIN_STATES $DONT_TOUCH_PINS $OUTPUT_PINS\n"
        "* $TEMPLATE_PINLIST $HEADER_INFO\n"
        "* $INDEX_1_VALUE $INDEX_2_VALUE $OUTPUT_LOAD $MAX_SLEW\n"
        "* $GLITCH $PUSHOUT_PER $PUSHOUT_DIR\n"
    )
    info = _fake_arc_info(TEMPLATE_DECK_PATH=str(tpl))
    lines = build_deck(info, slew=('0.05n', '0.05n'), load='0.5p',
                       when='!SE&SI', max_slew='1n')
    text = '\n'.join(lines)
    assert '$CELL_NAME' not in text
    assert 'DFFQ1' in text
    assert '!SE&SI' in text
    assert 'notSE_SI' in text
    assert 'RxxRxx' in text
    assert 'SE=0 SI=1' in text
    assert 'test_header' in text
    assert '0.05n' in text
    assert '0.5p' in text
    assert '0.1' in text


def test_missing_var_substitutes_empty(tmp_path):
    """Missing arc_info keys substitute to empty string (MCQC parity)."""
    tpl = tmp_path / 'test.sp'
    tpl.write_text("* $VECTOR $HEADER_INFO\n")
    info = _fake_arc_info(TEMPLATE_DECK_PATH=str(tpl),
                           VECTOR='', HEADER_INFO='')
    lines = build_deck(info, slew=('0n', '0n'), load='0p',
                       when='NO_CONDITION', max_slew='0n')
    text = '\n'.join(lines)
    assert '$VECTOR' not in text
    assert '$HEADER_INFO' not in text
