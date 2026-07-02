# tests/test_deck_assemble_collateral_parity.py
#
# THE parity gate for the shipping (grammar/frame) emitter: when the engine's
# derived bias agrees with the kit -when, the assembled deck must be
# BYTE-IDENTICAL to the golden template-substitution deck (build_deck). This
# is Demo 1's trust-anchor claim, asserted on the path the Run tab actually
# ships -- not only on core/deck_recipe.py.
#
# History: a 2026-07-02 probe found the pre-frame assembler was missing two
# collateral pieces the golden flow injects at BUILD time (the std waveform
# .inc and the output-load cap) and mismapped mpw slew/load params. The frame
# approach (grammar entries carry the family template's full text; assembly
# fills it with deck_builder's own substitution + injection points) makes the
# whole class structurally impossible; these tests keep it that way.
import os

import pytest

from core.deck_assemble import (assemble_combinational, assemble_sequential,
                                fill_frame, _subckt_ports)
from core.deck_builder import build_deck
from core.deck_recipe import STD_WV
from core.measurement.emit import load_grammar

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")
_SDFX = os.path.join(_REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
_DELAY_TPL = os.path.join(
    _REPO, "templates/N2P_v1.0/delay/template_common_inpin_%s_delay_%s.sp")
_HOLD_TPL = os.path.join(
    _REPO, "templates/N2P_v1.0/mpw/template__CP__syncx__D__fall__rise__1.sp")


def _arc_info(**over):
    info = {"CELL_NAME": "AOI22", "ARC_TYPE": "delay", "REL_PIN": "A1",
            "REL_PIN_DIR": "rise", "CONSTR_PIN": "A1", "CONSTR_PIN_DIR": "rise",
            "PROBE_PIN_1": "ZN", "WHEN": "A2&!B1&!B2",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2n",
            "INDEX_2_VALUE": "0.5f", "MAX_SLEW": "0.1u", "OUTPUT_LOAD": "0.5f",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22,
            "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}
    info.update(over)
    return info


# --- byte parity: combinational -------------------------------------------

@pytest.mark.parametrize("rel_dir,out_dir", [("rise", "fall"), ("fall", "rise")])
def test_delay_deck_byte_identical_to_golden(rel_dir, out_dir):
    # AOI22 is inverting, so A1 rise -> ZN fall and A1 fall -> ZN rise; the
    # WHEN names every side pin and matches a sensitizing state, so both
    # flows inject identical V lines -> full byte identity expected.
    info = _arc_info(REL_PIN_DIR=rel_dir,
                     TEMPLATE_DECK_PATH=_DELAY_TPL % (rel_dir, out_dir))
    r = assemble_combinational(info, open(_AOI22).read(), load_grammar())
    assert r["status"] == "OK", r["error"]
    assert r["kit_match"] is True
    golden = "".join(build_deck(info, when=info["WHEN"]))
    assert r["deck_text"] == golden


def test_delay_deck_extra_pins_land_in_unspecified_section():
    # Kit names only A2; the engine also proves B1/B2. The golden flow leaves
    # them floating; ours ties them under '* Unspecified pins'. The byte diff
    # must be EXACTLY those added V lines -- nothing else may move.
    info = _arc_info(WHEN="A2",
                     TEMPLATE_DECK_PATH=_DELAY_TPL % ("rise", "fall"))
    r = assemble_combinational(info, open(_AOI22).read(), load_grammar())
    assert r["status"] == "OK", r["error"]
    golden = "".join(build_deck(info, when="A2")).split("\n")
    ours = r["deck_text"].split("\n")
    added = [l for l in ours if l not in golden or ours.count(l) > golden.count(l)]
    assert sorted(added) == ["VB1 B1 0 'vss_value'", "VB2 B2 0 'vss_value'"]
    i_unspec = ours.index("* Unspecified pins")
    assert ours[i_unspec + 1] == "VB1 B1 0 'vss_value'"
    assert ours[i_unspec + 2] == "VB2 B2 0 'vss_value'"
    # removing the added lines restores the golden deck exactly
    trimmed = list(ours)
    for l in ("VB1 B1 0 'vss_value'", "VB2 B2 0 'vss_value'"):
        trimmed.remove(l)
    assert trimmed == golden


# --- byte parity: sequential (hold family) ---------------------------------

def test_hold_deck_byte_identical_to_golden():
    src = open(_SDFX, encoding="ascii").read()
    pins = _subckt_ports(src, "SDFX_LPE_PLACEHOLDER")
    base = _arc_info(CELL_NAME="SDFX_LPE_PLACEHOLDER", ARC_TYPE="hold",
                     REL_PIN="CP", REL_PIN_DIR="fall", CONSTR_PIN="D",
                     CONSTR_PIN_DIR="fall", PROBE_PIN_1="Q",
                     NETLIST_PATH=_SDFX, NETLIST_PINS=pins,
                     WHEN="NO_CONDITION")
    g = load_grammar()
    first = assemble_sequential(dict(base), src, g)
    assert first["status"] == "OK", first["error"]
    # Encode the engine's proven bias as the kit WHEN (sorted-pin order) so
    # the golden flow injects the same V lines at '* Pin definitions'.
    when = "&".join((p if v else "!" + p)
                    for p, v in sorted(first["bias"].items()))
    info = dict(base, WHEN=when, TEMPLATE_DECK_PATH=_HOLD_TPL)
    r = assemble_sequential(info, src, g)
    assert r["status"] == "OK", r["error"]
    golden = "".join(build_deck(info, when=when))
    assert r["deck_text"] == golden


# --- the 2026-07-02 collateral invariants, now on the shipping deck --------

def test_assembled_deck_carries_std_wv_and_arc_waveform():
    info = _arc_info(TEMPLATE_DECK_PATH=_DELAY_TPL % ("rise", "fall"))
    r = assemble_combinational(info, open(_AOI22).read(), load_grammar())
    assert r["status"] == "OK", r["error"]
    assert ".inc '%s'" % STD_WV in r["deck_text"]
    assert ".inc '/c/wv.spi'" in r["deck_text"]


def test_assembled_deck_dedups_waveform_when_equal_to_std():
    info = _arc_info(WAVEFORM_FILE=STD_WV)
    r = assemble_combinational(info, open(_AOI22).read(), load_grammar())
    assert r["status"] == "OK", r["error"]
    assert r["deck_text"].count(".inc '%s'" % STD_WV) == 1


def test_assembled_deck_has_output_load_cap():
    r = assemble_combinational(_arc_info(), open(_AOI22).read(), load_grammar())
    assert r["status"] == "OK", r["error"]
    assert "CZN ZN 0 'cl'" in r["deck_text"]


def test_fill_frame_output_pins_override_probe_for_load():
    frame = "* Output Load\n* Toggling pins\n"
    out = fill_frame(frame, {"OUTPUT_PINS": "Q QN"}, {})
    assert "CQ Q 0 'cl'" in out and "CQN QN 0 'cl'" in out
    assert "CZN" not in out


def test_mpw_frame_maps_cl_to_output_load_not_index2():
    # Constraint templates wire cl to $OUTPUT_LOAD and rel/constr slews to
    # INDEX_2/INDEX_1 -- the pre-frame assembler emitted the delay mapping for
    # every family, so cl silently carried the related-pin slew.
    src = open(_SDFX, encoding="ascii").read()
    info = _arc_info(CELL_NAME="SDFX_LPE_PLACEHOLDER", ARC_TYPE="hold",
                     REL_PIN="CP", REL_PIN_DIR="fall", CONSTR_PIN="D",
                     PROBE_PIN_1="Q", NETLIST_PATH=_SDFX, NETLIST_PINS="",
                     OUTPUT_LOAD="7e-15", INDEX_1_VALUE="1.1e-10",
                     INDEX_2_VALUE="2.2e-10")
    r = assemble_sequential(info, src, load_grammar())
    assert r["status"] == "OK", r["error"]
    assert ".param cl = '7e-15'" in r["deck_text"]
    assert ".param rel_pin_slew = '2.2e-10'" in r["deck_text"]
    assert ".param constr_pin_slew = '1.1e-10'" in r["deck_text"]
