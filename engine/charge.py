"""
engine/charge.py -- Layer-B cap-graph aggregation (Pillar 3 step 2; spec SS2.2/SS3).

Reduces the retained parasitic C network (DeviceGraph.caps, already logical-net
keyed by stage0) into the two objects the charge resolve (step 3) consumes:

  Cg[net]        -- grounded capacitance (farads): node-to-rail / AC ground.
                    Summed across all rail-terminated caps regardless of which
                    rail (VDD/VSS/...) -- at AC every rail is ground (spec SS2.2).
  Cc[(lo, hi)]   -- coupling capacitance (farads) between two signal nets, keyed
                    by the sorted net pair so (a,b) and (b,a) accumulate together.

Caps whose endpoints land on the SAME logical net (intra-net) vanish -- their
charge is internal to one conductor and does not affect its rail-referenced
potential (see docs/research/findings.md 3.1). Rail-to-rail caps are dropped
(not a signal-node cap).

Pure function, no PDK, stdlib only.
"""
from __future__ import annotations

from typing import Dict, Tuple

from engine.types import DeviceGraph

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}   # "0" = SPICE global ground


def cap_network(graph: DeviceGraph) -> Tuple[Dict[str, float], Dict[Tuple[str, str], float]]:
    """Aggregate graph.caps -> (Cg grounded farads, Cc coupling farads)."""
    Cg: Dict[str, float] = {}
    Cc: Dict[Tuple[str, str], float] = {}
    for c in graph.caps:
        a, b = c.a, c.b
        if a == b:
            continue                                   # intra-net -> vanishes
        a_rail, b_rail = a in RAILS, b in RAILS
        if a_rail and b_rail:
            continue                                   # rail-to-rail -> not a signal cap
        if a_rail or b_rail:
            sig = b if a_rail else a
            Cg[sig] = Cg.get(sig, 0.0) + c.farads
        else:
            key = (a, b) if a < b else (b, a)
            Cc[key] = Cc.get(key, 0.0) + c.farads
    return Cg, Cc
