"""Reconciliation lock: the DECK path and the AUDIT path agree on the physics.

Two combinational sensitization implementations coexist (ARCHITECTURE.md SS9):
  - DECK path  -- core/sensitize_bridge.derive_combinational_biases: picks ONE
    concrete side-pin hold vector so core/deck_recipe can write V<pin> holds
    (and verifies a collateral WHEN by passing it as `fixed`).
  - AUDIT path -- engine/stages/stage2_sensitize.derive_combinational +
    comb_verdict: derives the FULL sensitizing region + BLOCKED + SIG + verdict.

They are NOT redundant -- they answer different questions. But Demo 1's deck
byte-diff is only meaningful if they rest on the SAME physics: the side pins the
deck holds must be a state the engine confirms sensitizes the arc. Both use the
SAME parser (stage0_parse) and SAME evaluator (switchlevel.evaluate), so the
equivalence is structural; this test pins it down on every anchor arc and would
break loudly if the two paths ever drift.

Proven here, per (cell, rel_pin) over all synthetic anchors:
  (1) bridge returns a vector  <=>  engine SENSITIZING is non-empty (liveness).
  (2) the bridge's chosen vector is a MEMBER of the engine SENSITIZING region
      (the deck holds side pins at a genuinely-sensitizing state).
  (3) bridge-with-`fixed` agrees with the region: a sensitizing conjunction is
      accepted (non-None), a BLOCKED state is rejected (None).
  (4) pin-set contract: bridge.side_inputs over the real pin strings equals the
      engine's topology-derived side set (Red Line D: when strings match
      topology, the two side sets coincide).
"""
import itertools
import os

import pytest

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine.types import Arc
from core import sensitize_bridge

# cell -> (input pins, output pin)
ANCHORS = {
    "AIOI21": (["A1", "A2", "B"], "ZN"),
    "AOI22":  (["A1", "A2", "B1", "B2"], "ZN"),
    "OAI22":  (["A1", "A2", "B1", "B2"], "ZN"),
    "XOR2":   (["A", "B"], "Z"),
    "AOAI":   (["A1", "A2", "A3", "A4"], "ZN"),
}


def _text(cell):
    with open(os.path.join(ENGINE_DIR, "fixtures", cell + "_RECON.subckt"),
              "r", encoding="ascii") as fh:
        return fh.read()


def _engine_region(text, cell, rel, out):
    g = stage0_parse.parse(text, cell)
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel, rel_dir="rise",
              constr_pin=out, constr_dir="rise", when="NO_CONDITION",
              measurement="", raw={"probe_pin": out})
    res = stage2_sensitize.derive_combinational(g, arc, ccc)
    side = res.side_pins
    sens = {tuple((p, cs.assign[p]) for p in side) for cs in res.sensitizing}
    blocked = {tuple((p, cs.assign[p]) for p in side) for cs in res.blocked}
    return side, sens, blocked


def _arcs():
    for cell, (ins, out) in ANCHORS.items():
        for rel in ins:
            yield cell, ins, out, rel


@pytest.mark.parametrize("cell,ins,out,rel",
                         list(_arcs()),
                         ids=[f"{c}-{r}" for c, _, _, r in _arcs()])
class TestBridgeEngineEquivalence:
    def test_liveness_and_membership(self, cell, ins, out, rel):
        text = _text(cell)
        side, sens, _ = _engine_region(text, cell, rel, out)
        found, reason = sensitize_bridge.derive_combinational_biases(
            text, cell, rel, out, side)
        # (1) liveness: bridge yields a vector iff the engine region is non-empty
        assert (found is not None) == (len(sens) > 0), reason
        # (2) membership: the deck's hold vector is a sensitizing state per engine
        if found is not None:
            key = tuple((p, found[p]) for p in side)
            assert key in sens, (
                f"bridge picked {key} but engine SENSITIZING={sorted(sens)}")

    def test_fixed_when_agrees_with_region(self, cell, ins, out, rel):
        text = _text(cell)
        side, sens, blocked = _engine_region(text, cell, rel, out)
        if not sens:
            pytest.skip("no sensitizing state to fix")
        # a known-sensitizing conjunction -> bridge accepts (non-None)
        good = dict(next(iter(sens)))
        f_good, _ = sensitize_bridge.derive_combinational_biases(
            text, cell, rel, out, side, fixed=good)
        assert f_good is not None
        # a BLOCKED state -> bridge rejects (None): verify agrees with region
        if blocked:
            bad = dict(next(iter(blocked)))
            f_bad, _ = sensitize_bridge.derive_combinational_biases(
                text, cell, rel, out, side, fixed=bad)
            assert f_bad is None, (
                f"bridge accepted blocked state {bad}; engine BLOCKED has it")

    def test_pin_set_contract(self, cell, ins, out, rel):
        # Red Line D: bridge.side_inputs over the real pin strings must equal the
        # engine's topology-derived side set (no drift in who the side pins are).
        text = _text(cell)
        side_engine, _, _ = _engine_region(text, cell, rel, out)
        side_bridge = sensitize_bridge.side_inputs(
            " ".join(ins), rel, out)
        assert sorted(side_bridge) == sorted(side_engine)
