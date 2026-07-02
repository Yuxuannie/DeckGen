# tests/test_explain_sidecar.py
#
# G0 audit layer (spec docs/superpowers/specs/2026-07-02-generative-grammar-
# design.md): every assembled deck carries an explain record produced by the
# SAME pass that produced the deck -- selection evidence, engine bias with a
# why per line, collateral value sources, and a per-line origin map covering
# 100% of deck lines (conservation). Plus the Demo-1 parity classifier.
import json
import os

from core.deck_assemble import assemble_combinational, assemble_sequential
from core.deck_assemble_check import classify_parity
from core.measurement.emit import load_grammar

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")
_SDFX = os.path.join(_REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")


def _comb_info():
    return {"CELL_NAME": "AOI22", "ARC_TYPE": "delay", "REL_PIN": "A1",
            "REL_PIN_DIR": "rise", "CONSTR_PIN": "A1", "CONSTR_PIN_DIR": "rise",
            "PROBE_PIN_1": "ZN", "WHEN": "A2&!B1&!B2",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2n",
            "INDEX_2_VALUE": "0.5f", "MAX_SLEW": "0.1u", "OUTPUT_LOAD": "0.5f",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22,
            "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}


def _comb_result():
    return assemble_combinational(_comb_info(), open(_AOI22).read(),
                                  load_grammar())


def _seq_result():
    src = open(_SDFX, encoding="ascii").read()
    info = _comb_info()
    info.update(CELL_NAME="SDFX_LPE_PLACEHOLDER", ARC_TYPE="hold",
                REL_PIN="CP", REL_PIN_DIR="fall", CONSTR_PIN="D",
                PROBE_PIN_1="Q", WHEN="NO_CONDITION",
                NETLIST_PATH=_SDFX, NETLIST_PINS="")
    return assemble_sequential(info, src, load_grammar())


def test_comb_explain_present_and_line_conserving():
    r = _comb_result()
    assert r["status"] == "OK", r["error"]
    ex = r["explain"]
    lines = ex["audit"]["lines"]
    # conservation: every deck line has exactly one origin record, in order
    assert len(lines) == len(r["deck_text"].split("\n"))
    assert [l["n"] for l in lines] == list(range(1, len(lines) + 1))
    assert all(l["src"] in ("frame", "subst", "engine", "load") for l in lines)


def test_comb_explain_engine_lines_have_pin_value_why():
    r = _comb_result()
    eng = [l for l in r["explain"]["audit"]["lines"] if l["src"] == "engine"]
    assert {l["pin"] for l in eng} == set(r["bias"])
    for l in eng:
        assert l["value"] == r["bias"][l["pin"]]
        assert l["why"]


def test_comb_explain_selection_and_collateral():
    r = _comb_result()
    ex = r["explain"]
    assert ex["selection"]["arc_class"] == "combinational"
    assert ex["selection"]["provenance"]          # names the mined template(s)
    assert ex["engine"]["kit_match"] is True
    assert ex["collateral"]["vdd"]["value"] == "0.45"
    assert ex["collateral"]["vdd"]["source"] == "corner name voltage"
    assert ex["collateral"]["load_index_2"]["source"] == \
        "template.tcl index_2[i2]"


def test_comb_explain_load_line_recorded():
    r = _comb_result()
    loads = [l for l in r["explain"]["audit"]["lines"] if l["src"] == "load"]
    assert [l["pin"] for l in loads] == ["ZN"]


def test_seq_explain_selection_names_cluster_and_depth():
    r = _seq_result()
    assert r["status"] == "OK", r["error"]
    sel = r["explain"]["selection"]
    assert sel["arc_class"] == "sequential"
    assert sel["cluster_tag"] == r["cluster_tag"]
    assert sel["depth"] == r["depth"]
    assert r["explain"]["engine"]["p1_proven"] is True
    lines = r["explain"]["audit"]["lines"]
    assert len(lines) == len(r["deck_text"].split("\n"))


def test_explain_is_ascii_json_serializable():
    for r in (_comb_result(), _seq_result()):
        s = json.dumps(r["explain"], sort_keys=True)
        s.encode("ascii")                        # raises if non-ASCII leaked
        assert json.loads(s) == json.loads(s)


def test_explain_does_not_change_deck_bytes():
    # audit is metadata: assembling with and without it must give the same deck
    from core.deck_assemble import fill_frame
    g = load_grammar()
    entry = next(e for e in g["entries"]
                 if e["key"].get("arc_type") == "delay"
                 and e["key"].get("rel_dir") == "rise"
                 and e["key"].get("other_dir") == "fall")
    info = _comb_info()
    bias = {"A2": 1, "B1": 0, "B2": 0}
    audit = {}
    with_a = fill_frame(entry["frame_text"], info, bias, info["WHEN"],
                        audit=audit)
    without = fill_frame(entry["frame_text"], info, bias, info["WHEN"])
    assert with_a == without
    assert audit["lines"]


# --- parity classifier ------------------------------------------------------

def test_classify_parity_byte():
    assert classify_parity("a\nb\n", "a\nb\n") == "byte"


def test_classify_parity_engine_extras():
    gold = "a\n* Pin definitions\nb\n"
    ours = "a\n* Pin definitions\nVSE SE 0 'vss_value'\nb\n"
    assert classify_parity(ours, gold) == "engine_extras"


def test_classify_parity_diff_on_changed_line():
    assert classify_parity("a\nX\n", "a\nb\n") == "diff"


def test_classify_parity_diff_on_non_vline_addition():
    gold = "a\nb\n"
    ours = "a\nCEXTRA X 0 'cl'\nb\n"
    assert classify_parity(ours, gold) == "diff"


def test_classify_parity_diff_on_missing_golden_line():
    # ours missing a golden line must NOT count as extras
    assert classify_parity("a\n", "a\nb\n") == "diff"
