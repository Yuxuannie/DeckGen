# tests/test_measurement_decompile.py
#
# G1 gates (Phase G spec): every grammar recipe line is owned by a NAMED
# semantic rule with a why; re-emission from the IR is byte-exact; verbatim
# residue on the LOCAL corpus is zero (the airgap corpus may grow residue --
# that is what the report enumerates); the sidecar's per-line records carry
# the semantic rule/why, written by the same pass that writes the deck.
import os

from core.measurement.decompile import (decompile_entry, explain_recipe_line,
                                        explain_frame_line, report)
from core.measurement.emit import load_grammar

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")


def test_roundtrip_byte_exact_all_entries():
    g = load_grammar()
    assert g["entries"]
    for e in g["entries"]:
        nodes = decompile_entry(e)
        assert [n["line"] for n in nodes] == e["recipe_lines"], \
            e["provenance"][0]


def test_local_corpus_has_zero_verbatim_residue():
    # 100% on the LOCAL corpus (census-built battery). If this fails after a
    # re-mine, the report names the exact lines to add rules for -- extend
    # the battery, do not weaken this gate for the local corpus.
    rep = report(load_grammar())
    assert rep["total"] > 2000
    assert rep["verbatim"] == []
    assert rep["coverage_pct"] == 100.0


def test_report_conserves_line_count():
    rep = report(load_grammar())
    assert sum(rep["by_rule"].values()) == rep["total"]


def test_representative_rules_and_params():
    r, p, w = explain_recipe_line(
        ".nodeset v(X1.ml*_a) = 'vdd_value'")
    assert r == "nodeset" and dict(p)["node"] == "X1.ml*_a"
    assert "known state" in w

    r, p, w = explain_recipe_line(
        ".param related_pin_t04 = '50 * max_slew + constr_pin_offset'")
    assert r == "timing_param" and dict(p)["phase"] == "04"
    assert "t04" in w

    r, p, _ = explain_recipe_line(
        ".meas cp2cp trig v($REL_PIN) val='vdd_value/2' cross=3 "
        "targ v($CONSTR_PIN) val='vdd_value/2' cross=4")
    assert r == "meas" and dict(p)["name"] == "cp2cp"
    assert dict(p)["crosses"] == ["3", "4"]

    r, p, _ = explain_recipe_line(
        "XV$REL_PIN $REL_PIN 0 stdvs_mpw_fall_rise_fall_rise VDD='vdd_value'"
        " slew='rel_pin_slew' t01='related_pin_t01' t02='related_pin_t02'"
        " t03='related_pin_t03' t04='related_pin_t04'")
    assert r == "stimulus"
    assert dict(p)["model"] == "stdvs_mpw_fall_rise_fall_rise"

    r, p, _ = explain_recipe_line("* MEAS_DEGRADE_PER cp2q_del1 | $PUSHOUT_PER")
    assert r == "opt_search" and dict(p)["meas"] == "cp2q_del1"

    r, p, _ = explain_recipe_line("VS S 0 'vss_value'")
    assert r == "fixed_tie" and dict(p)["pin"] == "S"

    r, p, _ = explain_recipe_line("* DONT_TOUCH_PINS I1,S")
    assert r == "dont_touch" and dict(p)["pins"] == "I1,S"

    r, _, _ = explain_recipe_line("totally novel airgap line syntax")
    assert r == "verbatim"


def test_frame_line_router_covers_collateral_and_bias():
    assert explain_frame_line(".inc '/c/model.inc'")["rule"] == "collateral"
    assert explain_frame_line("* Pin definitions")["rule"] == "section"
    assert explain_frame_line("")["rule"] == "blank"
    assert explain_frame_line(".tran 1p 5000n sweep monte=1")["rule"] == "tran"


def test_sidecar_lines_carry_semantic_rule_and_why():
    from core.deck_assemble import assemble_combinational
    info = {"CELL_NAME": "AOI22", "ARC_TYPE": "delay", "REL_PIN": "A1",
            "REL_PIN_DIR": "rise", "CONSTR_PIN": "A1",
            "PROBE_PIN_1": "ZN", "WHEN": "A2&!B1&!B2",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40",
            "INDEX_1_VALUE": "1.2n", "INDEX_2_VALUE": "0.5f",
            "MAX_SLEW": "0.1u", "OUTPUT_LOAD": "0.5f",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22,
            "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}
    r = assemble_combinational(info, open(_AOI22).read(), load_grammar())
    assert r["status"] == "OK", r["error"]
    lines = r["explain"]["audit"]["lines"]
    deck = r["deck_text"].split("\n")
    # every frame/subst record now has rule + why (engine/load already do)
    assert all(("rule" in l and l.get("why"))
               for l in lines if l["src"] in ("frame", "subst"))
    # spot-check: the .tran deck line's record is rule 'tran'
    n_tran = deck.index(".tran 1p 5000n sweep monte=1") + 1
    rec = next(l for l in lines if l["n"] == n_tran)
    assert rec["rule"] == "tran"
    # and a .meas line maps to rule 'meas'
    n_meas = next(i for i, t in enumerate(deck) if t.startswith(".meas")) + 1
    assert next(l for l in lines if l["n"] == n_meas)["rule"] == "meas"
