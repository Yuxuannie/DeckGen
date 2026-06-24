"""core/arc_detail.py -- per-arc detail bundle for the audit view."""
import os

import pytest

from core.arc_detail import arc_detail, boolean_sop, truth_table
from engine.stages import stage0_parse

FIX = os.path.join(os.path.dirname(__file__), "..", "engine", "fixtures")


def _detail(cell, rel, out, whens=None):
    return arc_detail(os.path.join(FIX, cell + "_RECON.subckt"),
                      cell, rel, out, when_strings=whens)


class TestBooleanFunction:
    def test_aioi21_reduces_to_two_terms(self):
        d = _detail("AIOI21", "B", "ZN")
        # ZN = B*!(A1*A2) reduces to !A1*B + !A2*B
        parts = set(d["boolean"].split("=")[1].replace(" ", "").split("+"))
        assert parts == {"!A1*B", "!A2*B"}

    def test_sop_evaluates_to_truth_table(self):
        # round-trip: the recovered SOP must reproduce the truth table exactly
        g = stage0_parse.parse(open(os.path.join(FIX, "AOI22_RECON.subckt")).read(),
                               "AOI22")
        ins = ["A1", "A2", "B1", "B2"]
        rows = truth_table(g, ins, "ZN")
        sop = boolean_sop(rows, ins, "ZN").split("=")[1].strip()
        for r in rows:
            env = {p: r["inputs"][p] for p in ins}
            val = _eval_sop(sop, env)
            assert val == r["out"], (sop, r["inputs"])


def _eval_sop(sop, env):
    if sop == "0":
        return 0
    if sop == "1":
        return 1
    for term in sop.split("+"):
        lits = term.strip().split("*")
        ok = True
        for lit in lits:
            lit = lit.strip()
            neg = lit.startswith("!")
            pin = lit[1:] if neg else lit
            v = env[pin]
            if (v == 0) != neg:    # literal false
                ok = False
                break
        if ok:
            return 1
    return 0


class TestRegionTable:
    def test_match_when_correct(self):
        d = _detail("AIOI21", "B", "ZN",
                    whens=["!A1&!A2", "!A1&A2", "A1&!A2"])
        assert d["verdict"]["status"] == "MATCH"
        blk = next(r for r in d["region"] if r["label"] == "A1&A2")
        assert blk["engine"] == "BLOCKED" and blk["kit"] == "-" and blk["diff"] == ""
        sens = next(r for r in d["region"] if r["label"] == "!A1&!A2")
        assert sens["engine"] == "SENS" and sens["out_dir"] == "R"

    def test_catch_marks_diff_states(self):
        d = _detail("AIOI21", "B", "ZN", whens=["A1&A2"])
        assert d["verdict"]["status"] == "DIVERGENCE"
        blk = next(r for r in d["region"] if r["label"] == "A1&A2")
        assert blk["diff"] == "EXTRA"            # kit marks a blocked state
        miss = next(r for r in d["region"] if r["label"] == "!A1&!A2")
        assert miss["diff"] == "MISS"            # engine sens, kit omits


class TestTruthAndTopology:
    def test_truth_table_size_and_values(self):
        d = _detail("AIOI21", "B", "ZN")
        assert len(d["truth_table"]) == 8
        row = next(r for r in d["truth_table"]
                   if r["inputs"] == {"A1": 1, "A2": 1, "B": 0})
        assert row["out"] == 0

    def test_topology_blocks_and_per_state_on(self):
        d = _detail("AIOI21", "B", "ZN")
        nets = {b["net"] for b in d["topology"]["blocks"]}
        assert "ZN" in nets
        st = next(s for s in d["topology"]["states"] if s["label"] == "!A1&!A2")
        assert "XPA1" in st["on"] and "XPA2" in st["on"]   # parallel PMOS lit
