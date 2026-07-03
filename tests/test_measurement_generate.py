# tests/test_measurement_generate.py
#
# G2 gates (Phase G spec): the delay family and the sync{N} ladders are
# produced by parameterized generators; for every (family, N, dirs) instance
# inside the mined corpus the generated recipe byte-matches the mined entry;
# splicing an entry's own recipe into its own frame is the identity (so the
# extrapolation splice is structurally sound); extrapolation is refused by
# default and, when explicitly allowed, the deck's sidecar says so.
import os

import pytest

from core.measurement.emit import load_grammar
from core.measurement.generate import (GenerateError, check, delay_recipe,
                                       generate_entry, generated_recipe,
                                       hold_sync_recipe, mpw_sync_recipe,
                                       splice_frame)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDFX = os.path.join(_REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")


def test_generators_byte_match_every_mined_family_instance():
    g = load_grammar()
    matched = 0
    for e in g["entries"]:
        gen = generated_recipe(e["key"])
        if gen is None:
            continue
        assert gen == e["recipe_lines"], e["key"]
        matched += 1
    # 4 delay dirs + 8 mpw sync + 5 hold sync in the local corpus
    assert matched == 17


def test_generator_coverage_is_exactly_the_three_families():
    g = load_grammar()
    tags = sorted({e["key"]["cluster_tag"] for e in g["entries"]
                   if generated_recipe(e["key"]) is not None})
    assert tags == ["CP.sync2.D", "CP.sync3.D", "CP.sync4.D", "CP.sync5.D",
                    "CP.sync6.D", "common_inpin", "sync2.CP", "sync3.CP",
                    "sync4.CP", "sync5.CP", "sync6.CP"]


def test_self_splice_is_identity_for_every_generated_family_frame():
    g = load_grammar()
    for e in g["entries"]:
        gen = generated_recipe(e["key"])
        if gen is None or "frame_text" not in e:
            continue
        assert splice_frame(e["frame_text"], gen) == e["frame_text"], e["key"]


def test_check_cli_reports_full_parity():
    rep = check(load_grammar())
    assert len(rep["covered"]) == 17
    assert rep["mismatches"] == []


def test_extrapolated_depth7_ladder_structure():
    # hold: 2N+2 anchors, offset on the last, constrained window 20N-4
    r = hold_sync_recipe(7)
    assert ".param related_pin_t16 = '141 * max_slew + constr_pin_offset'" in r
    assert ".param constrained_pin_t02 = '136 * max_slew'" in r
    assert any("cross=16 targ v($PROBE_PIN_1)" in l for l in r)
    # mpw rise: 2N+2 anchors; mpw fall: 4N-1 anchors with recovery tail
    r = mpw_sync_recipe(7, "rise")
    assert ".param related_pin_t16 = '141 * max_slew + constr_pin_offset'" in r
    assert not any("related_pin_t17" in l for l in r)
    r = mpw_sync_recipe(7, "fall")
    assert ".param related_pin_t27 = '261 * max_slew'" in r
    assert any(l.startswith("XV$REL_PIN") and l.count("fall") == 14 for l in r)


def test_extrapolated_recipes_are_fully_owned_by_the_g1_rule_battery():
    # every generated line must classify to a named semantic rule -- the
    # generators may not invent line shapes the decompiler cannot explain
    from core.measurement.decompile import explain_recipe_line
    for recipe in (hold_sync_recipe(7), mpw_sync_recipe(7, "rise"),
                   mpw_sync_recipe(9, "fall"), delay_recipe("rise", "fall")):
        for line in recipe:
            rule, _p, _w = explain_recipe_line(line)
            assert rule != "verbatim", line


def test_generate_entry_synthesizes_frame_and_is_stamped():
    g = load_grammar()
    entry, tag, sel_rel, sel_other = generate_entry(
        g, family="hold", depth=7, rel_dir="fall")
    assert (tag, sel_rel, sel_other) == ("CP.sync7.D", "fall", "rise")
    assert entry["generated"] is True
    assert entry["provenance"][0].startswith("generated:hold depth=7 donor=")
    assert entry["recipe_lines"] == hold_sync_recipe(7)
    # the spliced frame keeps the donor's collateral skeleton and carries the
    # depth-7 recipe verbatim
    ft = entry["frame_text"]
    assert "$HEADER_INFO" in ft
    for line in entry["recipe_lines"]:
        assert line in ft
    assert "related_pin_t14 = '121 * max_slew + constr_pin_offset'" not in ft


def test_generate_entry_refuses_depth1_and_unknown_family():
    g = load_grammar()
    with pytest.raises(GenerateError):
        generate_entry(g, family="hold", depth=1, rel_dir="fall")
    with pytest.raises(GenerateError):
        generate_entry(g, family="removal", depth=3, rel_dir="rise")


def _arc_info(cell, arc_type, rel_dir="fall"):
    return {
        "CELL_NAME": cell, "ARC_TYPE": arc_type,
        "REL_PIN": "CP", "REL_PIN_DIR": rel_dir,
        "CONSTR_PIN": "D", "CONSTR_PIN_DIR": "fall", "PROBE_PIN_1": "Q",
        "WHEN": "NO_CONDITION",
        "WAVEFORM_FILE": "std_wv.spi", "INCLUDE_FILE": "MODEL.inc",
        "NETLIST_PATH": cell + ".spi", "VDD_VALUE": "0.450",
        "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2e-10",
        "INDEX_2_VALUE": "5e-16", "MAX_SLEW": "1e-9", "OUTPUT_LOAD": "5e-16",
    }


def test_assemble_depth7_refuses_by_default_and_names_the_flag(monkeypatch):
    from engine.stages import stage1b_classify
    from core.deck_assemble import assemble_sequential
    monkeypatch.setattr(stage1b_classify, "depth_of", lambda seq: 7)
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "hold"),
                            src, grammar)
    assert r["status"] == "ERROR"
    assert "allow_extrapolation" in r["error"]


def test_assemble_depth7_extrapolates_with_flag_and_stamps_sidecar(monkeypatch):
    from engine.stages import stage1b_classify
    from core.deck_assemble import assemble_sequential
    monkeypatch.setattr(stage1b_classify, "depth_of", lambda seq: 7)
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "hold"),
                            src, grammar, allow_extrapolation=True)
    assert r["status"] == "OK", r["error"]
    assert r["cluster_tag"] == "CP.sync7.D"
    sel = r["explain"]["selection"]
    assert sel["extrapolated"] is True
    assert "EXTRAPOLATED" in sel["why"]
    assert sel["provenance"][0].startswith("generated:hold depth=7")
    assert "related_pin_t16" in r["deck_text"]
    assert "$" not in r["deck_text"]


def test_assemble_mined_depth_sidecar_says_not_extrapolated():
    from core.deck_assemble import assemble_sequential
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "hold"),
                            src, grammar)
    assert r["status"] == "OK", r["error"]
    assert r["explain"]["selection"]["extrapolated"] is False
