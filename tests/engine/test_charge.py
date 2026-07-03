"""
Pillar 3 step 2: cap-graph aggregation (engine/charge.cap_network) -- grounded
(Cg) vs coupling (Cc), with intra-net caps vanishing and same-net caps summed.
Main case is the synthetic LPE fixture whose cap ground truth is known from the
generator; degenerate cases use small inline netlists.
"""
import os

import pytest

from engine.charge import cap_network
from engine.config import ENGINE_DIR
from engine.stages import stage0_parse

FIXTURE = os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")


def _fixture_graph():
    with open(FIXTURE, "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")


def test_fixture_grounded_and_coupling_split():
    Cg, Cc = cap_network(_fixture_graph())
    assert Cg == {"ml_a": 1.2e-18, "sl_a": 1.1e-18, "Q": 2.0e-18}
    assert Cc == {("ml_a", "sl_a"): 3.4e-19}


def test_coupling_key_is_sorted_pair():
    Cg, Cc = cap_network(_fixture_graph())
    # canonical key regardless of how the C line ordered its endpoints
    assert all(lo < hi for (lo, hi) in Cc)


def test_intra_net_cap_vanishes():
    # A cap between two device pins that R-merge onto the SAME logical net (A).
    src = (".subckt T A VSS\n"
           "XA A#d A#g A#s VSS nch_svt_mac\n"
           "XB A#d2 A#g2 A#s2 VSS nch_svt_mac\n"
           "R1 A A#d\n"
           "R2 A#d A#d2\n"
           "C1 A#d A#d2 5.0e-18\n"     # both ends -> net A => intra-net
           ".ends T\n")
    g = stage0_parse.parse(src, "T")
    Cg, Cc = cap_network(g)
    assert Cg == {}                     # the intra-net cap contributes nothing
    assert Cc == {}


def test_same_net_grounded_caps_summed():
    src = (".subckt T A VSS\n"
           "XA A A A VSS nch_svt_mac\n"
           "C1 A VSS 1.0e-18\n"
           "C2 A VSS 2.0e-18\n"        # two grounded caps on A -> summed
           ".ends T\n")
    g = stage0_parse.parse(src, "T")
    Cg, Cc = cap_network(g)
    assert Cg["A"] == pytest.approx(3.0e-18)   # float sum: 1e-18 + 2e-18
    assert set(Cg) == {"A"}
    assert Cc == {}


def test_same_pair_coupling_caps_summed():
    src = (".subckt T A B VSS\n"
           "XA A A A VSS nch_svt_mac\n"
           "XB B B B VSS nch_svt_mac\n"
           "C1 A B 1.0e-18\n"
           "C2 B A 2.0e-18\n"          # reversed order -> same canonical key, summed
           ".ends T\n")
    g = stage0_parse.parse(src, "T")
    Cg, Cc = cap_network(g)
    assert Cc[("A", "B")] == pytest.approx(3.0e-18)   # float sum, reversed key merged
    assert set(Cc) == {("A", "B")}
    assert Cg == {}


def test_rail_to_rail_cap_dropped():
    src = (".subckt T A VDD VSS\n"
           "XA A A A VSS nch_svt_mac\n"
           "C1 VDD VSS 9.0e-18\n"       # rail-rail -> not a signal cap
           "C2 A VSS 1.0e-18\n"
           ".ends T\n")
    g = stage0_parse.parse(src, "T")
    Cg, Cc = cap_network(g)
    assert Cg == {"A": 1.0e-18}
    assert Cc == {}


def test_deterministic():
    g = _fixture_graph()
    assert cap_network(g) == cap_network(g)
