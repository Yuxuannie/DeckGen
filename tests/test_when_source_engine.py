"""
Step 4: opts.when_source == 'engine' derives the side-pin holds from the LPE
netlist (combinational Boolean difference) instead of copying template.tcl's
WHEN, flags any disagreement, and degrades cleanly to the collateral WHEN when it
cannot derive.

Mechanism is verified on a synthetic 2-input NAND (real transistors); the
degrade path is verified on the placeholder (no transistors). Real derivation on
production cells needs the real LPE netlist.
"""
from core.deck_recipe import RecipeOpts, build_combinational_deck
from core.sensitize_bridge import (collateral_biases, derive_combinational_biases,
                                    side_inputs)

# A 2-input NAND in the macro-transistor LPE form stage0_parse understands:
# ZN = !(A & B). Pull-up: PA,PB in parallel; pull-down: NA,NB in series.
NAND2 = """\
.subckt NAND2 A B ZN VDD VSS VPP VBB
XPA ZN A VDD VPP pch_svt_mac L=3e-09 W=2e-08
XPB ZN B VDD VPP pch_svt_mac L=3e-09 W=2e-08
XNA ZN A mid VBB nch_svt_mac L=3e-09 W=2e-08
XNB mid B VSS VBB nch_svt_mac L=3e-09 W=2e-08
.ends NAND2
"""


def test_bridge_derives_sensitizing_hold_for_nand():
    # To make A control ZN, the other input B must be held HIGH (=1).
    biases, reason = derive_combinational_biases(
        NAND2, "NAND2", rel_pin="A", probe_pin="ZN", side_pins=["B"])
    assert biases == {"B": 1}, reason
    # And B=0 masks A (NAND with a 0 input -> output stuck at 1).
    biasesB, _ = derive_combinational_biases(
        NAND2, "NAND2", rel_pin="B", probe_pin="ZN", side_pins=["A"])
    assert biasesB == {"A": 1}


def test_bridge_degrades_on_placeholder():
    placeholder = ".subckt CELL A ZN VDD VSS\n* (no devices)\n.ends CELL\n"
    biases, reason = derive_combinational_biases(
        placeholder, "CELL", "A", "ZN", ["B"])
    assert biases is None and "no transistors" in reason


def test_side_inputs_and_collateral_biases():
    assert side_inputs("VDD VSS CP D Q SE SI", "CP", "Q") == ["D", "SE", "SI"]
    assert collateral_biases("!SE&SI", "CP", "CP") == {"SE": 0, "SI": 1}


def test_recipe_engine_mode_degrades_and_notes():
    """No readable netlist -> engine mode falls back to collateral WHEN + a note;
    the deck is unchanged from collateral mode."""
    info = {"HEADER_INFO": "", "CELL_NAME": "C", "NETLIST_PINS": "A B Z VDD VSS",
            "REL_PIN": "A", "REL_PIN_DIR": "rise", "PROBE_PIN_1": "Z",
            "CONSTR_PIN": "A", "CONSTR_PIN_DIR": "rise", "OUTPUT_PINS": "Z",
            "WHEN": "B", "NETLIST_PATH": "/no/such/file.spi"}
    notes = []
    eng = build_combinational_deck(info, RecipeOpts(when_source="engine"), notes)
    coll = build_combinational_deck(info, RecipeOpts(when_source="collateral"))
    assert eng == coll                                   # clean degrade
    assert any("unavailable" in n for n in notes)
    assert "VB B 0 'vdd_value'" in "\n".join(eng)        # collateral WHEN held B=1


def test_recipe_engine_mode_flags_divergence(tmp_path):
    """When the engine derives a different hold than the collateral WHEN, the deck
    uses the engine value and a DIVERGENCE note is recorded."""
    p = tmp_path / "NAND2.spi"
    p.write_text(NAND2)
    info = {"HEADER_INFO": "", "CELL_NAME": "NAND2",
            "NETLIST_PINS": "A B ZN VDD VSS VPP VBB",
            "REL_PIN": "A", "REL_PIN_DIR": "rise", "PROBE_PIN_1": "ZN",
            "CONSTR_PIN": "A", "CONSTR_PIN_DIR": "fall", "OUTPUT_PINS": "ZN",
            "WHEN": "!B",                       # collateral wrongly says B=0
            "NETLIST_PATH": str(p)}
    notes = []
    eng = "\n".join(build_combinational_deck(
        info, RecipeOpts(when_source="engine"), notes))
    # engine derives B=1 (correct), overriding the collateral !B
    assert "VB B 0 'vdd_value'" in eng
    assert any("DIVERGENCE B: engine=1 collateral=0" in n for n in notes)
