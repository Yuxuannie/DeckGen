from core.deck_assemble import engine_bias_section


def test_engine_bias_section_sorted_and_railed():
    lines = engine_bias_section({"A2": 1, "A1": 0})
    assert lines == [
        "* ===== ENGINE-DERIVED side-pin bias =====",
        "VA1 A1 0 'vss_value'",
        "VA2 A2 0 'vdd_value'",
    ]


def test_engine_bias_section_empty():
    assert engine_bias_section({}) == ["* ===== ENGINE-DERIVED side-pin bias ====="]
