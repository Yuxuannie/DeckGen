"""
engine/topo_viz.py -- ASCII view of the PARSED topology, so a reviewer can check
the engine's recovered logic by eye instead of reading an LPE netlist by hand.

Shows three things (all derived from Stage 0/1):
  - net drivers: for each internal net, the pull-up (pmos) and pull-down (nmos)
    transistors that drive it -- this reads like the recovered gate-level schematic;
  - CCC components: nets grouped by source/drain channel connectivity;
  - storage feedback: the cross-coupled loops that hold state.

ASCII only.
"""
from __future__ import annotations

from typing import List

from engine.types import CCCResult, DeviceGraph

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}
W = 80


def _bar(c="="):
    return c * W


def render(graph: DeviceGraph, ccc: CCCResult) -> str:
    driven = {d.terminals["d"] for d in graph.devices}
    inputs = {p for p in graph.ports if p not in RAILS and p not in driven}

    L: List[str] = []
    L.append(_bar())
    L.append(f" PARSED TOPOLOGY (logical, post R-merge)   cell {graph.cell}")
    L.append(_bar("-"))
    L.append(f" {len(graph.devices)} transistors   {len(graph.nets)} logical nets")
    L.append(f" ports : {' '.join(graph.ports)}")
    L.append(f" inputs: {' '.join(sorted(inputs))}   rails: {' '.join(sorted(RAILS & set(graph.nets)))}")
    L.append(f" check : {graph.checks[0] if graph.checks else ''}")
    L.append("")

    # net drivers = recovered gate-level schematic
    L.append(" net drivers (recovered schematic: each net <= the gate that drives it)")
    L.append(" " + "-" * (W - 1))
    for net in sorted(n for n in graph.nets if n not in RAILS and n not in inputs):
        pu = [d for d in graph.devices if d.terminals["d"] == net and d.kind == "pmos"]
        pd = [d for d in graph.devices if d.terminals["d"] == net and d.kind == "nmos"]
        pu_s = " ".join(f"{d.name}(g={d.terminals['g']},s={d.terminals['s']})" for d in pu)
        pd_s = " ".join(f"{d.name}(g={d.terminals['g']},s={d.terminals['s']})" for d in pd)
        L.append(f"  {net:<10} <= PU[{pu_s}]")
        L.append(f"  {'':<10}    PD[{pd_s}]")
    L.append("")

    # CCC components
    L.append(" CCC components (channel-connected; rails+inputs are boundaries)")
    L.append(" " + "-" * (W - 1))
    for i, comp in enumerate(ccc.components, 1):
        internal = [n for n in comp if n not in RAILS and n not in inputs]
        if internal:
            L.append(f"  [{i}] {{{', '.join(internal)}}}")
    L.append("")

    # storage feedback
    L.append(" storage feedback (cross-coupled = holds state)")
    L.append(" " + "-" * (W - 1))
    roles = {}
    for sn in ccc.state_nodes:
        roles.setdefault(sn.role, []).append(sn.net)
    for role, nodes in sorted(roles.items()):
        L.append(f"  {role}: {{{', '.join(nodes)}}}")
        for net in nodes:
            gated = [d for d in graph.devices if d.terminals["g"] == net
                     and d.terminals["d"] not in RAILS]
            tgt = sorted({d.terminals["d"] for d in gated})
            if tgt:
                L.append(f"     {net} gates -> drives {tgt}")
    L.append(_bar())
    return "\n".join(L)
