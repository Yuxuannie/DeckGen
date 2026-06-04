"""
engine/topo_viz.py -- readable ASCII view of the PARSED topology.

Real LPE cells contain many anonymous series-stack nodes (named `net_*` by the
parser) from tristate/clocked inverters. Those are noise for human validation,
so by default we show:
  - a FUNCTIONAL summary (clock buffers, select, master/slave storage, output);
  - net drivers for the NAMED signal nets only (the actual logic);
  - CCC components and storage feedback, with series nodes summarized.
Pass full=True to also dump the anonymous series nodes.

ASCII only.
"""
from __future__ import annotations

from typing import List, Optional

from engine.types import Arc, CCCResult, DeviceGraph

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}
W = 80


def _bar(c="="):
    return c * W


def _named(net: str) -> bool:
    return not net.startswith("net_")


def render(graph: DeviceGraph, ccc: CCCResult, arc: Optional[Arc] = None,
           full: bool = False) -> str:
    driven = {d.terminals["d"] for d in graph.devices}
    inputs = {p for p in graph.ports if p not in RAILS and p not in driven}
    core = {sn.net for sn in ccc.state_nodes}
    roles = {}
    for sn in ccc.state_nodes:
        roles.setdefault(sn.role, []).append(sn.net)

    # gate -> drains it controls (for tracing clock/select buffers)
    gate_adj = {}
    for d in graph.devices:
        if d.terminals["d"] not in RAILS:
            gate_adj.setdefault(d.terminals["g"], set()).add(d.terminals["d"])

    def reach(start):
        seen, stack = set(), [start]
        while stack:
            for w in gate_adj.get(stack.pop(), ()):
                if w not in seen and w not in core and w not in inputs and w not in RAILS:
                    seen.add(w)
                    stack.append(w)
        return seen

    L: List[str] = []
    L.append(_bar())
    L.append(f" FUNCTIONAL STRUCTURE (derived)   cell {graph.cell}")
    L.append(_bar("-"))
    L.append(f" {len(graph.devices)} transistors, {len(graph.nets)} nets, bridges="
             f"{sum(1 for c in graph.checks if 'BRIDGE' in c)}")
    clk = arc.rel_pin if arc else None
    for p in sorted(inputs):
        buf = sorted(n for n in reach(p) if _named(n))
        tag = " (clock)" if p == clk else ""
        if buf:
            L.append(f"  {p}{tag} -> drives nets {buf}")
        else:
            L.append(f"  {p}{tag} -> data input (into mux/data path)")
    for role in ("master", "slave", "storage"):
        if role in roles:
            L.append(f"  {role:<6} latch : {{{', '.join(roles[role])}}}  (cross-coupled storage)")
    q_drivers = sorted({d.terminals["g"] for d in graph.devices
                        if d.terminals["d"] in (set(graph.ports) - RAILS - inputs)
                        and d.terminals["g"] in core})
    if q_drivers:
        outs = sorted(set(graph.ports) - RAILS - inputs)
        L.append(f"  output {outs} <- gated by {q_drivers}")
    L.append("")

    # net drivers for named signal nets only
    signal = sorted(n for n in graph.nets if _named(n) and n not in RAILS and n not in inputs)
    L.append(" net drivers (named signal nets; recovered gate-level schematic)")
    L.append(" " + "-" * (W - 1))
    for net in signal:
        pu = [d for d in graph.devices if d.terminals["d"] == net and d.kind == "pmos"]
        pd = [d for d in graph.devices if d.terminals["d"] == net and d.kind == "nmos"]
        fu = " ".join(f"{d.name}(g={d.terminals['g']},s={d.terminals['s']})" for d in pu)
        fd = " ".join(f"{d.name}(g={d.terminals['g']},s={d.terminals['s']})" for d in pd)
        L.append(f"  {net:<8} <= PU[{fu}]")
        L.append(f"  {'':<8}    PD[{fd}]")
    L.append("")

    # CCC components (named nets; count the series nodes)
    L.append(" CCC components (named nets shown; series nodes counted)")
    L.append(" " + "-" * (W - 1))
    for i, comp in enumerate(ccc.components, 1):
        named = [n for n in comp if _named(n) and n not in RAILS and n not in inputs]
        series = [n for n in comp if not _named(n)]
        if named or series:
            extra = f"  (+{len(series)} series nodes)" if series else ""
            L.append(f"  [{i}] {{{', '.join(named) or '-'}}}{extra}")
    L.append("")

    # storage feedback (named targets only)
    L.append(" storage feedback (cross-coupled = holds state)")
    L.append(" " + "-" * (W - 1))
    for role, nodes in sorted(roles.items()):
        L.append(f"  {role}: {{{', '.join(nodes)}}}")
        for net in nodes:
            tgt = sorted({d.terminals["d"] for d in graph.devices
                          if d.terminals["g"] == net and d.terminals["d"] not in RAILS})
            named_t = [t for t in tgt if _named(t)]
            extra = f" (+{len(tgt) - len(named_t)} series)" if len(tgt) > len(named_t) else ""
            L.append(f"     {net} gates -> {named_t}{extra}")

    if full:
        L.append("")
        L.append(" series nodes (anonymous tristate-stack internals)")
        L.append(" " + "-" * (W - 1))
        for net in sorted(n for n in graph.nets if not _named(n)):
            drv = [d.name for d in graph.devices if d.terminals["d"] == net]
            L.append(f"  {net:<16} driven by {drv}")
    else:
        nseries = sum(1 for n in graph.nets if not _named(n))
        L.append("")
        L.append(f" ({nseries} anonymous series nodes hidden; --topo-full to show)")
    L.append(_bar())
    return "\n".join(L)
