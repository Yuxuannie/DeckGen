"""GOAL 2 -- engine WHEN-derivation on a DEEPER multi-level cell (spec 2d).

AOAI: ZN = !((A1*A2 + A3) * A4) -- three logic levels (AND, OR, AND) then invert,
a nested series-parallel network. Confirms the Boolean-difference region method
scales past the two-level AOI/OAI structures, including a 5-state region that the
kit would write as a MIX of a 2-literal and a 1-literal conjunction.
"""
import itertools
import os

import pytest

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine import switchlevel
from engine.types import Arc, CombStatus

INS = ["A1", "A2", "A3", "A4"]


def _graph():
    with open(os.path.join(ENGINE_DIR, "fixtures", "AOAI_RECON.subckt"),
              "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), "AOAI")


def _derive(rel):
    g = _graph()
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell="AOAI", arc_type="combinational", rel_pin=rel, rel_dir="rise",
              constr_pin="ZN", constr_dir="rise", when="NO_CONDITION",
              measurement="", raw={"probe_pin": "ZN"})
    return g, ccc, arc, stage2_sensitize.derive_combinational(g, arc, ccc)


def _v(res, whens):
    return stage2_sensitize.comb_verdict(res, whens).status


class TestVectorGate:
    def test_truth(self):
        g = _graph()
        for c in itertools.product((0, 1), repeat=4):
            a1, a2, a3, a4 = c
            want = int(not (((a1 and a2) or a3) and a4))
            assert switchlevel.evaluate(g, dict(zip(INS, c))).get("ZN") == want


class TestDeepRegions:
    def test_dispatch_combinational_no_state_node(self):
        g, ccc, arc, _ = _derive("A1")
        assert ccc.state_nodes == []
        assert stage2_sensitize.is_combinational_arc(g, arc, ccc) is True

    def test_a1_single_state_unconditional(self):
        _, _, _, res = _derive("A1")
        assert {cs.label for cs in res.sensitizing} == {"A2&!A3&A4"}
        assert _v(res, ["NO_CONDITION"]) is CombStatus.MATCH

    def test_a3_three_state_region(self):
        _, _, _, res = _derive("A3")
        assert {cs.label for cs in res.sensitizing} == {
            "!A1&!A2&A4", "!A1&A2&A4", "A1&!A2&A4"}

    def test_a4_five_state_region(self):
        _, _, _, res = _derive("A4")
        assert {cs.label for cs in res.sensitizing} == {
            "!A1&!A2&A3", "!A1&A2&A3", "A1&!A2&A3", "A1&A2&!A3", "A1&A2&A3"}
        assert res.needs_split is True
        assert all(len(cs.sig) > 0 for cs in res.sensitizing)


class TestDeepReducedWhen:
    def test_a3_reduced_correct_matches(self):
        _, _, _, res = _derive("A3")
        assert _v(res, ["!A1&A4", "!A2&A4"]) is CombStatus.MATCH

    def test_a3_reduced_wrong_diverges(self):
        _, _, _, res = _derive("A3")
        v = stage2_sensitize.comb_verdict(res, ["!A1&A4"])
        assert v.status is CombStatus.DIVERGENCE
        assert "A1&!A2&A4" in v.missing

    def test_a4_mixed_literal_reduced_correct_matches(self):
        # 5-state region as one 2-literal + one 1-literal conjunction.
        _, _, _, res = _derive("A4")
        assert _v(res, ["A1&A2", "A3"]) is CombStatus.MATCH

    def test_a4_partial_reduced_diverges(self):
        _, _, _, res = _derive("A4")
        assert _v(res, ["A1&A2"]) is CombStatus.DIVERGENCE
        assert _v(res, ["A3"]) is CombStatus.DIVERGENCE

    def test_or_form_unsupported(self):
        _, _, _, res = _derive("A4")
        assert _v(res, ["A1&A2 | A3"]) is CombStatus.UNSUPPORTED_WHEN
