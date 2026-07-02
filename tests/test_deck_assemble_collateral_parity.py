# tests/test_deck_assemble_collateral_parity.py
#
# Regression gate for the 2026-07-02 finding: the golden (template-substitution)
# flow injects two collateral pieces at BUILD time that appear in no template's
# text -- the std waveform library .inc (stdvs_* subckt definitions) and the
# output-load cap C<pin> <pin> 0 'cl'. Because they are absent from template
# text, the mined grammar can never carry them; the assembler must emit them.
# Before the fix, every grammar-path deck measured an UNLOADED output and, when
# WAVEFORM_FILE != std_wv, referenced stdvs_* sources with no definition.
import os

from core.deck_assemble import (assemble_combinational, assemble_sequential,
                                collateral_section)
from core.deck_recipe import STD_WV
from core.measurement.emit import load_grammar

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")


def _arc_info(**over):
    info = {"CELL_NAME": "AOI22", "ARC_TYPE": "delay", "REL_PIN": "A1",
            "REL_PIN_DIR": "rise", "PROBE_PIN_1": "ZN", "WHEN": "NO_CONDITION",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2n",
            "INDEX_2_VALUE": "0.5f", "MAX_SLEW": "0.1u",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22,
            "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}
    info.update(over)
    return info


def test_collateral_has_std_waveform_and_arc_waveform():
    text = "\n".join(collateral_section(_arc_info()))
    assert ".inc '%s'" % STD_WV in text
    assert ".inc '/c/wv.spi'" in text


def test_collateral_dedups_waveform_when_equal_to_std():
    lines = collateral_section(_arc_info(WAVEFORM_FILE=STD_WV))
    assert lines.count(".inc '%s'" % STD_WV) == 1


def test_collateral_has_output_load_cap_on_probe():
    text = "\n".join(collateral_section(_arc_info()))
    assert "CZN ZN 0 'cl'" in text


def test_collateral_output_pins_override_probe_for_load():
    text = "\n".join(collateral_section(_arc_info(OUTPUT_PINS="Q QN")))
    assert "CQ Q 0 'cl'" in text
    assert "CQN QN 0 'cl'" in text
    assert "CZN" not in text


def test_assembled_combinational_deck_carries_load_and_std_wv():
    g = load_grammar()
    r = assemble_combinational(_arc_info(), open(_AOI22).read(), g)
    assert r["status"] == "OK", r["error"]
    assert "CZN ZN 0 'cl'" in r["deck_text"]
    assert ".inc '%s'" % STD_WV in r["deck_text"]


def test_assembled_sequential_deck_carries_load_and_std_wv():
    # Same fixture + arc_info shape as test_deck_assemble_sequential.py's
    # passing hold case, so a failure here isolates the collateral fix.
    sdfx = os.path.join(_REPO, "engine", "fixtures",
                        "SDFX_LPE_PLACEHOLDER.subckt")
    g = load_grammar()
    info = _arc_info(CELL_NAME="SDFX_LPE_PLACEHOLDER", ARC_TYPE="hold",
                     REL_PIN="CP", REL_PIN_DIR="fall", CONSTR_PIN="D",
                     CONSTR_PIN_DIR="fall", PROBE_PIN_1="Q",
                     NETLIST_PATH=sdfx, NETLIST_PINS="",
                     WAVEFORM_FILE="std_wv.spi")
    r = assemble_sequential(info, open(sdfx, encoding="ascii").read(), g)
    assert r["status"] == "OK", r["error"]
    assert "CQ Q 0 'cl'" in r["deck_text"]
    assert ".inc '%s'" % STD_WV in r["deck_text"]
