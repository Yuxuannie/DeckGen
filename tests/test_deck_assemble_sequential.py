import os

import pytest

from core.deck_assemble import _seq_cluster_tag, SeqScope


def test_hold_family_depth_mapping():
    assert _seq_cluster_tag("hold", 1, "fall") == ("CP.syncx.D", "fall", "rise")
    assert _seq_cluster_tag("hold", 2, "fall") == ("CP.sync2.D", "fall", "rise")
    assert _seq_cluster_tag("hold", 6, "fall") == ("CP.sync6.D", "fall", "rise")


def test_mpw_family_depth_mapping():
    assert _seq_cluster_tag("mpw", 1, "rise") == ("CPN", "rise", "fall")
    assert _seq_cluster_tag("mpw", 3, "fall") == ("sync3.CP", "fall", "rise")
    assert _seq_cluster_tag("mpw", 3, "rise") == ("sync3.CP", "rise", "fall")


def test_depth_beyond_corpus_raises_named_scope():
    with pytest.raises(SeqScope) as e:
        _seq_cluster_tag("hold", 7, "fall")
    assert "7" in str(e.value) and "6" in str(e.value)
    with pytest.raises(SeqScope):
        _seq_cluster_tag("mpw", 0, "rise")


def test_unknown_family_raises():
    with pytest.raises(SeqScope):
        _seq_cluster_tag("removal", 2, "rise")


from core.deck_assemble import assemble_sequential
from core.measurement.emit import load_grammar

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDFX = os.path.join(_REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
_XOR2 = os.path.join(_REPO, "engine", "fixtures", "XOR2_RECON.subckt")
_LATCH = os.path.join(_REPO, "tests", "fixtures", "audit_lib", "netlist",
                      "SYNTH_LATCH.spi")


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


def test_assemble_sequential_hold_sdfx_ok():
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "hold"), src, grammar)
    assert r["status"] == "OK", r["error"]
    assert r["family"] == "hold" and r["cluster_tag"] == "CP.syncx.D"
    assert "$" not in r["deck_text"]
    assert "cp2q_del1" in r["deck_text"]
    assert "cp2q_del2" in r["deck_text"]        # hold discriminator (mpw lacks it)
    assert "X1 " in r["deck_text"] and "SDFX_LPE_PLACEHOLDER" in r["deck_text"]
    assert any(l.startswith("VSE ") or l.startswith("VSI ")
               for l in r["deck_text"].splitlines())


def test_assemble_sequential_mpw_sdfx_ok():
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "mpw", rel_dir="rise"),
                            src, grammar)
    assert r["status"] == "OK", r["error"]
    assert r["family"] == "mpw" and r["cluster_tag"] == "CPN"
    assert "cp2cp" in r["deck_text"]
    assert "cp2q_del2" not in r["deck_text"]


def test_assemble_sequential_header_leads_deck():
    # Regression: the SPICE title banner must be line 1 (SPICE reads line 1 as
    # the title), collateral/instance/bias sit in the middle, and .end is last.
    # Previously the whole recipe was appended after collateral, burying the
    # banner ~line 25.
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "hold"), src, grammar)
    assert r["status"] == "OK", r["error"]
    lines = r["deck_text"].splitlines()
    assert "SPICE Deck created by TSMC ADC Timing Team" in lines[0]
    assert lines[-1].strip() == ".end"
    i_banner = 0
    i_coll = next(i for i, l in enumerate(lines) if "COLLATERAL" in l)
    i_toggle = next(i for i, l in enumerate(lines) if l.strip().startswith("* Toggling"))
    # banner (preamble) < collateral/instance/bias < toggling body
    assert i_banner < i_coll < i_toggle


def _split_recipe_probe():
    from core.deck_assemble import _split_recipe
    return _split_recipe


def test_split_recipe_marker_present():
    _split_recipe = _split_recipe_probe()
    recipe = ["*** banner ***", "* SPICE options", ".option x",
              "* Toggling pins", "V1 a 0 1", ".end"]
    pre, body = _split_recipe(recipe)
    assert pre == ["*** banner ***", "* SPICE options", ".option x"]
    assert body == ["* Toggling pins", "V1 a 0 1", ".end"]
    assert pre + body == recipe                       # no lines lost


def test_split_recipe_marker_absent_falls_back():
    _split_recipe = _split_recipe_probe()
    recipe = ["*** banner ***", ".option x", ".end"]  # no marker
    pre, body = _split_recipe(recipe)
    assert pre == [] and body == recipe               # whole recipe kept as body


def test_assemble_sequential_combinational_is_named_error():
    grammar = load_grammar()
    src = open(_XOR2, encoding="ascii").read()
    r = assemble_sequential(_arc_info("XOR2", "hold"), src, grammar)
    assert r["status"] == "ERROR" and r["deck_text"] is None
    assert "combinational" in r["error"].lower()


def test_assemble_sequential_latch_is_named_error():
    grammar = load_grammar()
    src = open(_LATCH, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SYNTH_LATCH", "hold"), src, grammar)
    assert r["status"] == "ERROR" and "latch" in r["error"].lower()
