"""GOAL 2 -- engine WHEN-derivation on two-and-two cells AOI22 / OAI22
(spec SS6 2c). These give the REDUCED-WHEN credibility pair that AIOI21 could not:
a pin's sensitizing region spans several states expressible as a single -when
fixing fewer than all side pins.

  AOI22 ZN = !(A1*A2 + B1*B2): A1 -> ZN sensitizes at A2 & !(B1*B2) = 3 states.
    reduced-CORRECT  ["A2&!B1", "A2&!B2"]  -> MATCH (region equivalence).
    reduced-WRONG    ["A2&!B1"]            -> DIVERGENCE (missing A2&B1&!B2).
    over-broad       ["A2"]                -> DIVERGENCE (extra into BLOCKED A2&B1&B2).
  OAI22 ZN = !((A1+A2)*(B1+B2)): A1 -> ZN sensitizes at !A2 & (B1+B2) = 3 states
    (OR/AND dual). The AOI22 reduced whens applied here must DIVERGE -- the engine
    derives from topology, it does not echo a fixed pattern.
"""
import itertools
import os

import pytest

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine import switchlevel
from engine.types import Arc, CombStatus

INS = ["A1", "A2", "B1", "B2"]


def _graph(cell):
    with open(os.path.join(ENGINE_DIR, "fixtures", cell + "_RECON.subckt"),
              "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), cell)


def _derive(cell, rel="A1"):
    g = _graph(cell)
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel, rel_dir="rise",
              constr_pin="ZN", constr_dir="rise", when="NO_CONDITION",
              measurement="", raw={"probe_pin": "ZN"})
    return stage2_sensitize.derive_combinational(g, arc, ccc)


def _v(res, whens):
    return stage2_sensitize.comb_verdict(res, whens).status


# --------------------------------------------------------------------------
# VECTOR GATE
# --------------------------------------------------------------------------
class TestVectorGate:
    def test_aoi22_truth(self):
        g = _graph("AOI22")
        for c in itertools.product((0, 1), repeat=4):
            a1, a2, b1, b2 = c
            want = int(not ((a1 and a2) or (b1 and b2)))
            assert switchlevel.evaluate(g, dict(zip(INS, c))).get("ZN") == want

    def test_oai22_truth(self):
        g = _graph("OAI22")
        for c in itertools.product((0, 1), repeat=4):
            a1, a2, b1, b2 = c
            want = int(not ((a1 or a2) and (b1 or b2)))
            assert switchlevel.evaluate(g, dict(zip(INS, c))).get("ZN") == want


# --------------------------------------------------------------------------
# REGION + SIG
# --------------------------------------------------------------------------
class TestRegions:
    def test_aoi22_a1_region(self):
        res = _derive("AOI22")
        assert {cs.label for cs in res.sensitizing} == {
            "A2&!B1&!B2", "A2&!B1&B2", "A2&B1&!B2"}
        assert "A2&B1&B2" in {cs.label for cs in res.blocked}

    def test_oai22_a1_region_is_dual(self):
        res = _derive("OAI22")
        assert {cs.label for cs in res.sensitizing} == {
            "!A2&!B1&B2", "!A2&B1&!B2", "!A2&B1&B2"}

    def test_sig_present_and_needs_split(self):
        res = _derive("AOI22")
        assert all(len(cs.sig) > 0 for cs in res.sensitizing)
        assert res.needs_split is True


# --------------------------------------------------------------------------
# REDUCED-WHEN credibility pair + OR/AND duality + UNSUPPORTED guard
# --------------------------------------------------------------------------
class TestReducedWhen:
    def test_aoi22_reduced_correct_matches(self):
        res = _derive("AOI22")
        assert _v(res, ["A2&!B1", "A2&!B2"]) is CombStatus.MATCH

    def test_aoi22_reduced_wrong_missing_diverges(self):
        res = _derive("AOI22")
        v = stage2_sensitize.comb_verdict(res, ["A2&!B1"])
        assert v.status is CombStatus.DIVERGENCE
        assert "A2&B1&!B2" in v.missing

    def test_aoi22_overbroad_into_blocked_diverges(self):
        res = _derive("AOI22")
        v = stage2_sensitize.comb_verdict(res, ["A2"])
        assert v.status is CombStatus.DIVERGENCE
        assert "A2&B1&B2" in v.extra          # marks sensitizing where blocked

    def test_oai22_reduced_correct_matches(self):
        res = _derive("OAI22")
        assert _v(res, ["!A2&B1", "!A2&B2"]) is CombStatus.MATCH

    def test_duality_aoi_whens_diverge_on_oai(self):
        # the AOI22-correct reduced whens are WRONG for OAI22 -> must diverge.
        res = _derive("OAI22")
        assert _v(res, ["A2&!B1", "A2&!B2"]) is CombStatus.DIVERGENCE

    def test_or_form_unsupported(self):
        res = _derive("AOI22")
        assert _v(res, ["A2 & (!B1 | !B2)"]) is CombStatus.UNSUPPORTED_WHEN
