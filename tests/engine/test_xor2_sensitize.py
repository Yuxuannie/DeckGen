"""GOAL 2 -- engine WHEN-derivation on a BINATE cell (spec SS5/EDIT 4).

AIOI/AOI/OAI are unate in every input; the region method can pass on every unate
anchor and still fail on the first binate cell. XOR2/XNOR2 break two unate
assumptions:
  - "narrower-than-full region <=> conditional arc": FALSE here -- A controls Z in
    EVERY side-state (SENSITIZING == full, BLOCKED == empty -> unconditional).
  - "fixed output direction per input edge": FALSE here -- the output edge depends
    on the side-state (A-rise@B=0 -> Z rise; A-rise@B=1 -> Z fall).
The engine must derive the FULL region (no spurious conditional WHEN) yet still
track output direction per side-state.
"""
import itertools
import os

import pytest

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine import switchlevel
from engine.types import Arc, CombStatus


def _graph(cell):
    with open(os.path.join(ENGINE_DIR, "fixtures", cell + "_RECON.subckt"),
              "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), cell)


def _arc(cell, rel_pin="A"):
    return Arc(cell=cell, arc_type="combinational", rel_pin=rel_pin, rel_dir="rise",
               constr_pin="Z", constr_dir="rise", when="NO_CONDITION",
               measurement="", raw={"probe_pin": "Z"})


def _derive(cell):
    g = _graph(cell)
    ccc = stage1_ccc.decompose(g)
    return g, stage2_sensitize.derive_combinational(g, _arc(cell), ccc)


# --------------------------------------------------------------------------
# VECTOR GATE -- truth table + direction-varies-by-side-state.
# --------------------------------------------------------------------------
class TestVectorGate:
    def test_xor2_truth_and_binate_direction(self):
        g = _graph("XOR2")
        z = lambda a, b: switchlevel.evaluate(g, {"A": a, "B": b}).get("Z")
        for a, b in itertools.product((0, 1), repeat=2):
            assert z(a, b) == (a ^ b)
        # A rise @ B=0 -> Z rise; @ B=1 -> Z fall (direction depends on side-state)
        assert z(0, 0) == 0 and z(1, 0) == 1
        assert z(0, 1) == 1 and z(1, 1) == 0

    def test_xnor2_truth_and_opposite_polarity(self):
        g = _graph("XNOR2")
        z = lambda a, b: switchlevel.evaluate(g, {"A": a, "B": b}).get("Z")
        for a, b in itertools.product((0, 1), repeat=2):
            assert z(a, b) == (1 - (a ^ b))
        assert z(0, 0) == 1 and z(1, 0) == 0      # A rise @ B=0 -> Z fall
        assert z(0, 1) == 0 and z(1, 1) == 1      # A rise @ B=1 -> Z rise


# --------------------------------------------------------------------------
# REGION -- full, unconditional; direction tracked per side-state.
# --------------------------------------------------------------------------
class TestBinateRegion:
    def test_xor2_region_is_full_no_blocked(self):
        _, res = _derive("XOR2")
        sens = {cs.label for cs in res.sensitizing}
        assert sens == {"!B", "B"}             # full side-pin space
        assert res.blocked == []               # nothing blocked -> unconditional

    def test_xor2_output_direction_varies_with_side_state(self):
        _, res = _derive("XOR2")
        d = {cs.label: cs.out_dir for cs in res.sensitizing}
        assert d == {"!B": "R", "B": "F"}      # direction depends on B

    def test_xnor2_region_is_full_opposite_direction(self):
        _, res = _derive("XNOR2")
        d = {cs.label: cs.out_dir for cs in res.sensitizing}
        assert {cs.label for cs in res.sensitizing} == {"!B", "B"}
        assert d == {"!B": "F", "B": "R"}      # opposite polarity vs XOR2


# --------------------------------------------------------------------------
# VERDICT -- unconditional MATCH (no false flag), and a kit that WRONGLY
# conditionalizes a fully-sensitizing binate pin must DIVERGE.
# --------------------------------------------------------------------------
class TestBinateVerdict:
    def test_unconditional_matches_no_spurious_condition(self):
        _, res = _derive("XOR2")
        v = stage2_sensitize.comb_verdict(res, ["NO_CONDITION"])
        assert v.status is CombStatus.MATCH

    def test_wrongly_conditionalized_binate_pin_diverges(self):
        # kit writes -when "B" (only B=1), under-claiming the full region.
        _, res = _derive("XOR2")
        v = stage2_sensitize.comb_verdict(res, ["B"])
        assert v.status is CombStatus.DIVERGENCE
        assert "!B" in v.missing               # topology sensitizes at !B too
