"""topo_pundn.py -- extract the pull-up / pull-down network (PUN/PDN) structure of
a CMOS cell from its DeviceGraph, as a series/parallel expression per driven net,
plus the set of conducting transistors under a given input state.

This is the data model behind the audit detail view's topology figure: it answers,
for a chosen side-pin state, *why* an arc sensitizes (a conducting path from the
related pin's network to the output exists) or is blocked (it does not).

Engine-side, stdlib only, ASCII. Reads .subckt-derived structure ONLY (Red Line
A) -- never template.tcl.

Series/parallel model (an `SP` node):
  ('dev', name, gate, kind)          one transistor (kind: 'pmos'|'nmos')
  ('series', [SP, ...])              source-drain chain
  ('parallel', [SP, ...])           same two endpoints
  ('flat', [('dev',...), ...])      non-series-parallel network -> bipartite fallback
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from engine import switchlevel
from engine.types import DeviceGraph

HIGH_RAILS = {"VDD", "VPP"}
LOW_RAILS = {"VSS", "VBB", "0"}
RAILS = HIGH_RAILS | LOW_RAILS


def _classify(graph: DeviceGraph):
    drains = {d.terminals["d"] for d in graph.devices}
    gates = {d.terminals["g"] for d in graph.devices if d.terminals["g"] not in RAILS}
    outputs = [p for p in graph.ports if p in drains and p not in RAILS]
    # a "driven net" is a logic node: the cell output, or an internal net that is
    # both produced (a drain) and consumed (a gate) -- i.e. a gate-output stage.
    driven = [n for n in graph.nets
              if n not in RAILS and (n in outputs or (n in drains and n in gates))]
    return outputs, sorted(set(driven)), gates


def _stage_devices(graph: DeviceGraph, driven: str, kind: str,
                   driven_set: Set[str]) -> List:
    """Devices of `kind` in the source/drain stack of `driven` -- BFS over channel
    (d/s) nets, stopping at rails and at OTHER driven nets so each stage is its own
    network."""
    devs = [d for d in graph.devices if d.kind == kind]
    comp = {driven}
    used = []
    changed = True
    while changed:
        changed = False
        for d in devs:
            if d in used:
                continue
            a, b = d.terminals["d"], d.terminals["s"]
            if a in comp or b in comp:
                used.append(d)
                for nn in (a, b):
                    if (nn not in comp and nn not in RAILS
                            and not (nn in driven_set and nn != driven)):
                        comp.add(nn)
                        changed = True
    return used


def _sp_reduce(devices: List, terminal_a: str, terminal_b: str):
    """Reduce a two-terminal multigraph (edges = transistors) between terminal_a
    (the driven net) and terminal_b (a rail-class label) to a series/parallel
    expression. Returns ('flat', [...]) if the network is not series-parallel."""
    # edges: list of [u, v, sp]; rails collapse to terminal_b's class label.
    def railnorm(n):
        if n in HIGH_RAILS:
            return "VDD"
        if n in LOW_RAILS:
            return "VSS"
        return n
    edges = []
    for d in devices:
        u, v = railnorm(d.terminals["d"]), railnorm(d.terminals["s"])
        edges.append([u, v, ("dev", d.name, d.terminals["g"], d.kind)])
    ta, tb = railnorm(terminal_a), railnorm(terminal_b)
    if not edges:
        return ("flat", [])

    def endpoints():
        from collections import defaultdict
        deg = defaultdict(list)
        for i, e in enumerate(edges):
            deg[e[0]].append(i)
            deg[e[1]].append(i)
        return deg

    changed = True
    while changed and len(edges) > 1:
        changed = False
        # parallel: two edges sharing the same unordered endpoint pair
        seen: Dict[frozenset, int] = {}
        for i, e in enumerate(edges):
            key = frozenset((e[0], e[1]))
            if len(key) == 1:           # self-loop: drop (shorted device)
                continue
            if key in seen:
                j = seen[key]
                a, b = edges[j], edges[i]
                merged = ("parallel", _flatten("parallel", [a[2], b[2]]))
                edges[j] = [a[0], a[1], merged]
                edges.pop(i)
                changed = True
                break
            seen[key] = i
        if changed:
            continue
        # series: an interior node (not a terminal) with exactly two edges
        deg = endpoints()
        for node, eidx in deg.items():
            if node in (ta, tb):
                continue
            if len(eidx) == 2:
                i, j = eidx
                a, b = edges[i], edges[j]
                outer_a = a[1] if a[0] == node else a[0]
                outer_b = b[1] if b[0] == node else b[0]
                merged = ("series", _flatten("series", [a[2], b[2]]))
                new = [outer_a, outer_b, merged]
                for k in sorted((i, j), reverse=True):
                    edges.pop(k)
                edges.append(new)
                changed = True
                break

    if len(edges) == 1 and frozenset((edges[0][0], edges[0][1])) == frozenset((ta, tb)):
        return edges[0][2]
    # not reducible to a single SP edge -> flat fallback (list every device)
    leaves = []
    for d in devices:
        leaves.append(("dev", d.name, d.terminals["g"], d.kind))
    return ("flat", leaves)


def _flatten(kind: str, children: List):
    out = []
    for c in children:
        if isinstance(c, tuple) and c and c[0] == kind:
            out.extend(c[1])
        else:
            out.append(c)
    return out


def pull_networks(graph: DeviceGraph) -> List[dict]:
    """Per driven net: its PUN (PMOS -> high rail) and PDN (NMOS -> low rail) as
    series/parallel expressions. Output stage first."""
    outputs, driven, _ = _classify(graph)
    driven_set = set(driven)
    # order: outputs last so they render at the bottom near the output; internal
    # stages above. (UI can decide; we sort outputs first here, stages after.)
    ordered = outputs + [n for n in driven if n not in outputs]
    nets = []
    for d in ordered:
        pun = _sp_reduce(_stage_devices(graph, d, "pmos", driven_set), d, "VDD")
        pdn = _sp_reduce(_stage_devices(graph, d, "nmos", driven_set), d, "VSS")
        nets.append({"net": d, "is_output": d in outputs, "pun": pun, "pdn": pdn})
    return nets


def conducting(graph: DeviceGraph, assignment: Dict[str, int]) -> Set[str]:
    """Names of transistors that conduct under `assignment` (gate-controlled)."""
    v = switchlevel.evaluate(graph, assignment)
    on = set()
    for d in graph.devices:
        g = v[d.terminals["g"]]
        if (d.kind == "nmos" and g == 1) or (d.kind == "pmos" and g == 0):
            on.add(d.name)
    return on


def sp_to_text(sp) -> str:
    """Readable string for an SP expression (tests + bipartite fallback labels)."""
    if not sp:
        return "(none)"
    tag = sp[0]
    if tag == "dev":
        return sp[2]                       # gate pin name
    if tag == "flat":
        return "flat[" + ", ".join(sp_to_text(c) for c in sp[1]) + "]"
    sep = " - " if tag == "series" else " || "
    inner = sep.join(sp_to_text(c) for c in sp[1])
    return "(" + inner + ")"


def device_names(sp) -> List[str]:
    """All device names referenced in an SP expression."""
    if not sp:
        return []
    if sp[0] == "dev":
        return [sp[1]]
    out = []
    for c in sp[1]:
        out.extend(device_names(c))
    return out
