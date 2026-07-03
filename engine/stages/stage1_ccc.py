"""
Stage 1 -- CCC decomposition + structural storage-node id (spec SS5, SS9; SEGMENT 2).
  in : DeviceGraph (logical-net transistors)
  out: CCCResult (channel-connected components + cross-coupled storage nodes)

Method (technique survey, Layer B -- Bryant switch-level):
  - CCC: partition non-boundary nets by source/drain channel connectivity
    (gates excluded; power rails + primary inputs are boundaries).
  - Storage nodes: a cell holds state in cross-coupled feedback. Build a directed
    "influence" graph (gate->drain AND source->drain) over non-rail nets; a
    strongly-connected component of size >= 2 is a bistable storage element
    (e.g. ml_a<->ml_b). This is found STRUCTURALLY -- no match on `ml_*`/`sl_*`.
  - Label master/slave by influence-distance from the data inputs: the storage
    element closer to the inputs is the master, the one closer to Q the slave.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Set

from engine.types import CCCResult, DeviceGraph, Derivation, StateNode

STAGE = "S1.ccc"
RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}   # "0" = SPICE global ground


def _components(nets: List[str], edges: List[tuple], boundaries: Set[str]) -> List[List[str]]:
    """Union-find connected components over non-boundary nets."""
    parent = {n: n for n in nets if n not in boundaries}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    groups: Dict[str, List[str]] = {}
    for n in parent:
        groups.setdefault(find(n), []).append(n)
    return [sorted(v) for v in groups.values()]


def _sccs(adj: Dict[str, Set[str]]) -> List[List[str]]:
    """Tarjan strongly-connected components (deterministic order)."""
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    onstack: Set[str] = set()
    stack: List[str] = []
    out: List[List[str]] = []
    counter = [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack.add(v)
        for w in sorted(adj.get(v, ())):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(sorted(comp))

    for v in sorted(adj):
        if v not in index:
            strong(v)
    return out


def _min_dist(adj: Dict[str, Set[str]], sources: Set[str], targets: Set[str]) -> int:
    """BFS shortest hop-count from any source to any target over `adj`."""
    seen = set(sources)
    q = deque((s, 0) for s in sources)
    while q:
        node, d = q.popleft()
        if node in targets:
            return d
        for w in sorted(adj.get(node, ())):
            if w not in seen:
                seen.add(w)
                q.append((w, d + 1))
    return 10 ** 9


def decompose(graph: DeviceGraph) -> CCCResult:
    nets = graph.nets
    driven = {dev.terminals["d"] for dev in graph.devices}
    input_ports = {p for p in graph.ports if p not in RAILS and p not in driven}
    boundaries = RAILS | input_ports

    # CCC: source-drain channel edges between non-rail nets
    chan_edges = []
    influence: Dict[str, Set[str]] = {}
    for dev in graph.devices:
        d, g, s = dev.terminals["d"], dev.terminals["g"], dev.terminals["s"]
        if d not in RAILS and s not in RAILS:
            chan_edges.append((d, s))
        # influence graph (for storage SCCs + master/slave ordering)
        for src in (g, s):
            if src not in RAILS and d not in RAILS:
                influence.setdefault(src, set()).add(d)

    components = _components(nets, chan_edges, boundaries)

    # Cross-coupled feedback = SCC of size >= 2 in the influence graph. The cycle
    # may pass through series-stack internal nodes of tristate/clocked inverters,
    # so we let the SCC form over (gate+source)->drain edges...
    internal_adj = {u: {w for w in vs if w not in boundaries}
                    for u, vs in influence.items() if u not in boundaries}
    # ...then keep only the real STORAGE nodes: a stored value both is driven (a
    # drain) AND controls (a gate). Series-stack internal nodes are drains/sources
    # only -- never gates -- so intersecting the SCC with gate-nets drops them.
    gate_nets = {d.terminals["g"] for d in graph.devices
                 if d.terminals["g"] not in RAILS}
    storage_cores: List[List[str]] = []
    for scc in _sccs(internal_adj):
        if len(scc) < 2:
            continue
        core = sorted(n for n in scc if n in gate_nets)
        if len(core) >= 2:                 # a cross-couple has >= 2 controlling nodes
            storage_cores.append(core)

    # Label by influence-distance to the OUTPUT: the slave drives Q directly, so
    # it is closest to the output; the master is one stage further back. (Distance
    # from inputs fails here because the clock gates BOTH latch pass-gates equally.)
    output_ports = {p for p in graph.ports if p in driven and p not in RAILS}

    def dist_to_out(core: List[str]) -> int:
        return _min_dist(influence, set(core), output_ports)

    ranked = sorted(storage_cores, key=dist_to_out)   # closest to output first
    labels = {}
    if len(ranked) == 1:
        labels[id(ranked[0])] = "storage"
    else:
        last = len(ranked) - 1
        for i, core in enumerate(ranked):
            labels[id(core)] = "slave" if i == 0 else (
                "master" if i == last else f"stage{last - i}")

    state_nodes: List[StateNode] = []
    notes: List[str] = [
        f"CCC: {len(components)} channel-connected component(s) over "
        f"{len([n for n in nets if n not in boundaries])} internal nets "
        f"(rails+inputs {sorted(boundaries)} are boundaries)",
        f"storage: {len(storage_cores)} cross-coupled element(s); storage nodes = "
        f"feedback-SCC members that are also gates (series-stack nodes excluded)",
    ]
    for core in ranked:
        role = labels[id(core)]
        dist = dist_to_out(core)
        reason = (f"cross-coupled feedback loop; storage core {core} "
                  f"(gate-controlling members); labeled {role}: "
                  f"{dist} influence-hops to output {sorted(output_ports)}")
        for net in core:
            state_nodes.append(StateNode(net=net, role=role,
                                        derivation=Derivation(net, reason, STAGE)))

    return CCCResult(components=components, state_nodes=state_nodes, notes=notes)
