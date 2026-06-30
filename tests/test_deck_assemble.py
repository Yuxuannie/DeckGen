import os
from core.deck_assemble import engine_bias_section, collateral_section, choose_bias
from core.deck_assemble import assemble_combinational
from engine.types import CombState
from core.measurement.mine import mine

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")


def _grammar():
    return mine(os.path.join(_REPO, "templates/N2P_v1.0/delay"))


def _arc_info(rel_pin, probe_pin):
    return {"CELL_NAME": "AOI22", "ARC_TYPE": "delay",
            "REL_PIN": rel_pin, "REL_PIN_DIR": "rise",
            "PROBE_PIN_1": probe_pin, "WHEN": "NO_CONDITION",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40",
            "INDEX_1_VALUE": "1.2n", "INDEX_2_VALUE": "0.5f", "MAX_SLEW": "0.1u",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22,
            "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}


def test_assemble_combinational_ok():
    src = open(_AOI22).read()
    r = assemble_combinational(_arc_info("A1", "ZN"), src, _grammar())
    assert r["status"] == "OK", r["error"]
    deck = r["deck_text"]
    assert "$" not in deck                               # every placeholder resolved
    assert "X1 A1 A2 B1 B2 ZN VDD VSS AOI22" in deck     # instance line
    assert ".param vdd_value = '0.45'" in deck           # collateral
    assert "0 'vdd_value'" in deck or "0 'vss_value'" in deck   # bias present
    assert ".meas" in deck and ".tran" in deck           # recipe present
    assert r["output"] == "ZN"


def test_assemble_combinational_sequential_is_named_error():
    # a flip-flop netlist -> CCC has a state node -> not B1's job
    dff = os.path.join(_REPO,
        "tests/fixtures/collateral/N2P_v1.0/test_lib/Netlist/"
        "LPE_cworst_CCworst_T_m40c/DFFQ1_c.spi")
    src = open(dff).read()
    ai = _arc_info("CP", "Q"); ai["CELL_NAME"] = "DFFQ1"
    r = assemble_combinational(ai, src, _grammar())
    assert r["status"] == "ERROR"
    assert "sequential" in r["error"].lower()


_ARC_INFO = {
    "VDD_VALUE": "0.45", "TEMPERATURE": "-40",
    "INDEX_1_VALUE": "1.2n", "INDEX_2_VALUE": "0.5f",
    "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
    "NETLIST_PATH": "/c/AOI22.spi",
}


def test_collateral_section_has_real_values_no_placeholders():
    lines = collateral_section(_ARC_INFO)
    text = "\n".join(lines)
    assert "$" not in text                              # all values resolved
    assert ".param vdd_value = '0.45'" in text
    assert ".temp -40" in text
    assert ".param cl = '0.5f'" in text                 # INDEX_2 = load
    assert ".param rel_pin_slew = '1.2n'" in text       # INDEX_1 = slew
    assert ".inc '/c/model.inc'" in text
    assert ".inc '/c/wv.spi'" in text
    assert ".inc '/c/AOI22.spi'" in text
    assert "VVDD VDD 0 'vdd_value'" in text
    assert "VVSS VSS 0 'vss_value'" in text
    assert "VVPP VPP 0 'vdd_value'" in text
    assert "VVBB VBB 0 'vss_value'" in text


def test_engine_bias_section_sorted_and_railed():
    lines = engine_bias_section({"A2": 1, "A1": 0})
    assert lines == [
        "* ===== ENGINE-DERIVED side-pin bias =====",
        "VA1 A1 0 'vss_value'",
        "VA2 A2 0 'vdd_value'",
    ]


def test_engine_bias_section_empty():
    assert engine_bias_section({}) == ["* ===== ENGINE-DERIVED side-pin bias ====="]


def _states():
    # AOI-like: sensitizing when the other input is non-controlling
    return [
        CombState("!A2", {"A2": 0}, "F", frozenset()),
        CombState("A2", {"A2": 1}, "R", frozenset()),
    ]


def test_choose_bias_matches_kit_when():
    r = choose_bias(_states(), "A2")              # kit says A2=1
    assert r["bias"] == {"A2": 1}
    assert r["kit_match"] is True
    assert r["chosen_label"] == "A2"


def test_choose_bias_no_kit_picks_first_sorted():
    r = choose_bias(_states(), None)
    assert r["bias"] == {"A2": 0}                 # "!A2" sorts before "A2"
    assert r["kit_match"] is False


def test_choose_bias_kit_diverges_engine_wins():
    # kit claims A2=0&extra that no sensitizing state has -> engine still picks one
    r = choose_bias(_states(), "A2&A3")
    assert r["kit_match"] is False
    assert r["bias"] in ({"A2": 0}, {"A2": 1})


def test_assemble_combinational_internal_error_is_named_not_raised():
    # An unexpected failure after parse must become a named ERROR, never propagate.
    src = open(_AOI22).read()
    r = assemble_combinational(_arc_info("A1", "ZN"), src, None)  # grammar=None -> downstream blows up
    assert r["status"] == "ERROR"
    assert r["error"]  # non-empty, names the failure
