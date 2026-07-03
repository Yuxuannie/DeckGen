"""
engine/switchlevel.py -- a tiny stdlib switch-level Boolean evaluator.

Given a Boolean assignment to the primary inputs, compute each net's logic value
(0 / 1 / None=X) by conduction: a net takes the value of any STRONG driver (a
power rail or a primary input) reachable through channels of currently-ON
transistors. Iterate to a fixed point so gate values that depend on other nets
(inverters, buffers) settle.

This is the classic switch-level model (Bryant) minus transistor strengths. To
analyze a latch's data path we BREAK its cross-coupled feedback devices (passed
in `broken`) so the input driver isn't fought by the keeper -- which models "the
write path overpowers the feedback while the latch is transparent".

No PDK, no external deps. Used by Stage 2 (sensitization / P1) and later P2.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Optional

from engine.types import DeviceGraph

RAILS_HI = {"VDD", "VPP"}
RAILS_LO = {"VSS", "VBB", "0"}


def evaluate(graph: DeviceGraph, assignment: Dict[str, int],
             broken: FrozenSet[str] = frozenset()) -> Dict[str, Optional[int]]:
    """Return {net: 0|1|None} for a primary-input `assignment` (net -> 0/1)."""
    val: Dict[str, Optional[int]] = {}
    strong = set(RAILS_HI) | set(RAILS_LO)
    for n in graph.nets:
        if n in RAILS_HI:
            val[n] = 1
        elif n in RAILS_LO:
            val[n] = 0
        elif n in assignment:
            val[n] = assignment[n]
            strong.add(n)
        else:
            val[n] = None
    devices = [d for d in graph.devices if d.name not in broken]

    for _ in range(len(graph.nets) + 5):
        # 1. which transistors conduct under the current gate values
        parent: Dict[str, str] = {n: n for n in graph.nets}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for d in devices:
            g = val[d.terminals["g"]]
            on = (d.kind == "nmos" and g == 1) or (d.kind == "pmos" and g == 0)
            if on:
                a, b = find(d.terminals["d"]), find(d.terminals["s"])
                if a != b:
                    parent[max(a, b)] = min(a, b)

        # 2. each channel-connected group takes its unique strong-driver value
        groups: Dict[str, list] = {}
        for n in graph.nets:
            groups.setdefault(find(n), []).append(n)
        new = dict(val)
        for members in groups.values():
            drivers = {val[m] for m in members if m in strong and val[m] is not None}
            if len(drivers) == 1:
                v = next(iter(drivers))
            elif len(drivers) > 1:
                v = None                       # conflicting strong drivers -> X
            else:
                continue                       # undriven -> leave as-is (X)
            for m in members:
                if m not in strong:
                    new[m] = v

        if new == val:
            break
        val = new
    return val
