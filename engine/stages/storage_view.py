"""storage_view.py -- shared structural storage-core extraction for B2.

Lifts the influence-graph + cross-coupled-SCC + per-core cone/distance logic
(currently inline in stage1_ccc.decompose and re-implemented in
tools/seq_probe.py) into ONE reusable function. Consumes a DeviceGraph
(stage0 output); returns a StorageView. stdlib only, ASCII only,
simulator-free. stage1_ccc.py is intentionally left unchanged -- this ~15-line
duplication is noted for a later unification.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.types import DeviceGraph
from engine.stages.stage1_ccc import _sccs, _min_dist, RAILS


@dataclass(frozen=True)
class StorageCore:
    nets: frozenset      # cross-coupled gate-controlling nets (the SCC core)
    dist_to_out: int     # min BFS influence-hops to any output port
    cone: frozenset      # output ports forward-reachable in the influence graph


@dataclass(frozen=True)
class StorageView:
    cores: tuple         # StorageCore list, sorted by (dist_to_out, sorted nets)
    outputs: tuple       # output ports (driven, non-rail), sorted
    notes: tuple         # provenance strings


def _cone(influence, core, outputs):
    """Output ports forward-reachable from a core in the influence graph."""
    seen = set(core)
    stack = list(core)
    hit = set()
    while stack:
        n = stack.pop()
        if n in outputs:
            hit.add(n)
        for w in influence.get(n, ()):
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return frozenset(hit)


def build_storage_view(graph: DeviceGraph) -> StorageView:
    devs = graph.devices
    driven = {d.terminals["d"] for d in devs}
    input_ports = {p for p in graph.ports if p not in RAILS and p not in driven}
    output_ports = {p for p in graph.ports if p in driven and p not in RAILS}
    boundaries = RAILS | input_ports

    # influence graph: gate->drain and source->drain over non-rail nets
    # (mirrors stage1_ccc.decompose exactly).
    influence = {}
    for d in devs:
        dd, g, s = d.terminals["d"], d.terminals["g"], d.terminals["s"]
        for src in (g, s):
            if src not in RAILS and dd not in RAILS:
                influence.setdefault(src, set()).add(dd)

    internal_adj = {u: {w for w in vs if w not in boundaries}
                    for u, vs in influence.items() if u not in boundaries}
    gate_nets = {d.terminals["g"] for d in devs if d.terminals["g"] not in RAILS}

    cores = []
    for scc in _sccs(internal_adj):
        if len(scc) < 2:
            continue
        core = frozenset(n for n in scc if n in gate_nets)
        if len(core) >= 2:                      # cross-couple has >= 2 controllers
            dist = _min_dist(influence, set(core), output_ports)
            cone = _cone(influence, core, output_ports)
            cores.append(StorageCore(nets=core, dist_to_out=dist, cone=cone))

    cores.sort(key=lambda c: (c.dist_to_out, sorted(c.nets)))
    notes = (
        "storage_view: %d cross-coupled core(s) over influence graph" % len(cores),
        "outputs=%s" % sorted(output_ports),
    )
    return StorageView(cores=tuple(cores), outputs=tuple(sorted(output_ports)),
                       notes=notes)
