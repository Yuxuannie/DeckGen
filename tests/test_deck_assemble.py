from core.deck_assemble import engine_bias_section, collateral_section, choose_bias
from engine.types import CombState


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
