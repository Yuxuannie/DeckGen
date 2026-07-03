"""GOAL 2 -- engine WHEN-derivation accuracy on AIOI21 (the canonical hard
sensitization case). This is the ENGINE-DERIVATION path, complementary to
tests/test_aioi21_ground_truth.py which only exercises the COLLATERAL PARSER
(arc counts/grouping). Here the engine is fed a reconstructed netlist and must
INDEPENDENTLY derive the per-arc sensitization REGION from topology -- with no
read of arc.when for the derivation itself -- then the region-equivalence verdict
cross-checks against collateral -when (MATCH) and catches corruptions (CATCH).

Cell (adjudicated 2026-06-24, PROJECT_NOTES 2.4): ZN = B * !(A1*A2).
  - B -> ZN sensitizes in !(A1*A2) = {!A1&!A2, !A1&A2, A1&!A2}; A1&A2 BLOCKED.
  - A1 -> ZN sensitizes only at {A2&B}; A2 -> ZN only at {A1&B} (one state each
    -> the kit writes them UNCONDITIONAL; Option A: that is NOT "all states").

Vector gate (mandatory, spec SS5.9): before deriving any region, switchlevel on
the reconstructed netlist MUST reproduce the cell's truth table and -vector
transition directions. A netlist that computes the wrong function is rejected
here, closing the "build the netlist to match the answer" loophole.
"""
import itertools
import os

import pytest

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine.types import Arc, CombStatus


CELL = "AIOI21"


def _graph():
    with open(os.path.join(ENGINE_DIR, "fixtures", "AIOI21_RECON.subckt"),
              "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), CELL)


def _arc(rel_pin, when="NO_CONDITION"):
    return Arc(cell=CELL, arc_type="combinational", rel_pin=rel_pin, rel_dir="rise",
               constr_pin="ZN", constr_dir="rise", when=when, measurement="",
               raw={"probe_pin": "ZN"})


def _zn(g, a1, a2, b):
    from engine import switchlevel
    return switchlevel.evaluate(g, {"A1": a1, "A2": a2, "B": b}).get("ZN")


# --------------------------------------------------------------------------
# VECTOR GATE (spec SS5.9) -- must pass before any region is trusted.
# --------------------------------------------------------------------------
class TestVectorGate:
    def test_truth_table_is_B_and_not_A1A2(self):
        g = _graph()
        for a1, a2, b in itertools.product((0, 1), repeat=3):
            want = int(b and not (a1 and a2))      # ZN = B * !(A1*A2)
            assert _zn(g, a1, a2, b) == want, f"{a1}{a2}{b}"
        # the row that refutes the wrong reconstruction ZN=B+A1*A2:
        assert _zn(g, 1, 1, 0) == 0

    def test_vector_directions(self):
        g = _graph()
        # A1 rise @ sensitizing (A2=1,B=1) -> ZN fall  (negative-unate {RxxF})
        assert _zn(g, 0, 1, 1) == 1 and _zn(g, 1, 1, 1) == 0
        # A2 rise @ (A1=1,B=1) -> ZN fall  ({xRxF})
        assert _zn(g, 1, 0, 1) == 1 and _zn(g, 1, 1, 1) == 0
        # B rise @ (A1=0,A2=0) -> ZN rise  (positive-unate {xxRR})
        assert _zn(g, 0, 0, 0) == 0 and _zn(g, 0, 0, 1) == 1


# --------------------------------------------------------------------------
# REGION DERIVATION (engine derives from topology, not from arc.when)
# --------------------------------------------------------------------------
def _regions(rel_pin):
    g = _graph()
    ccc = stage1_ccc.decompose(g)
    res = stage2_sensitize.derive_combinational(g, _arc(rel_pin), ccc)
    sens = {cs.label for cs in res.sensitizing}
    blocked = {cs.label for cs in res.blocked}
    return res, sens, blocked


class TestRegionDerivation:
    def test_dispatch_is_combinational(self):
        g = _graph()
        ccc = stage1_ccc.decompose(g)
        assert stage2_sensitize.is_combinational_arc(g, _arc("B"), ccc) is True

    def test_B_region_is_not_A1A2_with_A1A2_blocked(self):
        res, sens, blocked = _regions("B")
        assert sens == {"!A1&!A2", "!A1&A2", "A1&!A2"}
        assert blocked == {"A1&A2"}

    def test_A1_region_is_A2_and_B(self):
        _, sens, _ = _regions("A1")
        assert sens == {"A2&B"}

    def test_A2_region_is_A1_and_B(self):
        _, sens, _ = _regions("A2")
        assert sens == {"A1&B"}

    def test_output_direction_tracks_unateness(self):
        res, _, _ = _regions("B")          # B positive-unate: P rise -> O rise
        assert all(cs.out_dir == "R" for cs in res.sensitizing)
        resa, _, _ = _regions("A1")        # A1 negative-unate: P rise -> O fall
        assert all(cs.out_dir == "F" for cs in resa.sensitizing)


# --------------------------------------------------------------------------
# SIG (partition hook, SS3.5) -- computed + surfaced, distinguishes parallel
# PMOS (!A1&!A2) from single PMOS (single-side). Computed, NOT gated.
# --------------------------------------------------------------------------
class TestSigPartitionHook:
    def test_sig_present_for_every_sensitizing_state(self):
        res, _, _ = _regions("B")
        assert all(len(cs.sig) > 0 for cs in res.sensitizing)

    def test_sig_distinguishes_parallel_from_single_pmos(self):
        res, _, _ = _regions("B")
        sig = {cs.label: cs.sig for cs in res.sensitizing}
        # parallel-PMOS state has a different conducting path than the singles
        assert sig["!A1&!A2"] != sig["!A1&A2"]
        assert sig["!A1&!A2"] != sig["A1&!A2"]
        # and B's region spans >1 SIG group -> needs_split (kit DID split into 3)
        assert res.needs_split is True


# --------------------------------------------------------------------------
# VERDICT: MATCH on correct collateral, CATCH on corruption (bidirectional).
# --------------------------------------------------------------------------
class TestVerdictMatchAndCatch:
    def test_B_correct_collateral_matches(self):
        res, _, _ = _regions("B")
        v = stage2_sensitize.comb_verdict(res, ["A1&!A2", "!A1&A2", "!A1&!A2"])
        assert v.status is CombStatus.MATCH

    def test_B_corrupted_minterm_into_blocked_diverges(self):
        # kit asserts timing on the BLOCKED state A1&A2 (and drops !A1&!A2)
        res, _, _ = _regions("B")
        v = stage2_sensitize.comb_verdict(res, ["A1&!A2", "!A1&A2", "A1&A2"])
        assert v.status is CombStatus.DIVERGENCE
        assert "A1&A2" in v.extra            # marked sensitizing where blocked
        assert "!A1&!A2" in v.missing        # true sensitizing state omitted

    def test_B_dropped_minterm_diverges(self):
        res, _, _ = _regions("B")
        v = stage2_sensitize.comb_verdict(res, ["A1&!A2", "!A1&A2"])
        assert v.status is CombStatus.DIVERGENCE
        assert "!A1&!A2" in v.missing

    def test_A1_unconditional_does_not_false_flag(self):
        # CREDIBILITY TEST (reduced-correct): a complex-gate input the kit leaves
        # unconditional must NOT flag, even though it sensitizes in only 1 state.
        res, _, _ = _regions("A1")
        v = stage2_sensitize.comb_verdict(res, ["NO_CONDITION"])
        assert v.status is CombStatus.MATCH

    def test_A1_reduced_wrong_when_flags(self):
        # reduced-but-WRONG: kit writes A2&!B (a state that is BLOCKED for A1).
        res, _, _ = _regions("A1")
        v = stage2_sensitize.comb_verdict(res, ["A2&!B"])
        assert v.status is CombStatus.DIVERGENCE
        assert "A2&B" in v.missing            # true region omitted
        assert "A2&!B" in v.extra             # wrong state asserted

    def test_B_or_form_is_unsupported_not_divergence(self):
        # B's true region !(A1*A2) reduces to the OR "!A1 | !A2"; the guard must
        # say UNSUPPORTED-WHEN, never DIVERGENCE (SCLD realism).
        res, _, _ = _regions("B")
        v = stage2_sensitize.comb_verdict(res, ["!A1 | !A2"])
        assert v.status is CombStatus.UNSUPPORTED_WHEN


class TestOutOfScopeGuard:
    """Empty SENSITIZING -> OUT-OF-SCOPE (sequential/clock pin), never DIVERGENCE.
    This is the guard that stopped the real run flooding the report with 79 false
    divergences on CK (clock-gating latch) cells: combinational Boolean difference
    sees no state where toggling the pin changes the output, because the output
    depends on stored state."""

    def test_empty_sensitizing_not_divergence(self):
        from engine.types import (CombSensitizationResult, Derivation,
                                   CombStatus)
        res = CombSensitizationResult(
            rel_pin="CP", output="Q", side_pins=["TE", "E"],
            sensitizing=[], blocked=[], needs_split=False,
            derivation=Derivation([], "none", "test"))
        # kit asserts timing in several states; engine found no comb. sensitization
        v = stage2_sensitize.comb_verdict(res, ["TE&E", "!TE&E", "TE&!E"])
        assert v.status is CombStatus.OUT_OF_SCOPE
        assert "sequential" in v.detail.lower()
