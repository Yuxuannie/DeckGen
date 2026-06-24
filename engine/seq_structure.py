"""
engine/seq_structure.py -- Layer 1 sequential STRUCTURE extraction (Demo 3).

RESEARCH-LANE MODULE. Lives on branch research/seq-fingerprint. It READS the
engine core (stage0 parse, stage1 ccc) and does NOT modify it (ARCHITECTURE.md
red-line: research agent reads L0-L2, extends on its own branch).

What this adds on top of stage1_ccc.decompose():
  - A clean public "extract sequential structure" entry point that groups the
    flat StateNode list into discrete STORAGE LOOPS (one per cross-coupled SCC),
    each with its member nets and master/slave role.
  - CLOCK-PATH identification: the primary input whose influence fans out to the
    most storage loops is the clock; its buffered phase nets (e.g. clkb) are the
    nets it reaches before any storage loop.
  - A STRUCTURAL combinational-vs-sequential discriminator at two scopes:
      * cell-level: does the cell contain ANY storage SCC?  (the ARCHITECTURE.md
        sec 8 thesis: combinational CCC has no SCC; sequential has one).
      * arc-level: does the influence path from rel_pin to the output TRAVERSE a
        storage loop?  This is the refinement of Red Line D for whole arcs --
        stage2_sensitize.is_combinational_arc scopes the no-state check to the
        OUTPUT's own CCC, which (correctly for its scope) calls a DFF's CP->Q arc
        combinational because Q's immediate inverter has no feedback. The arc is
        nonetheless sequential because its logical path runs THROUGH the latches.
        We expose both and document the relationship (see check_discriminator).

Thesis under test (ARCHITECTURE.md sec 8):
  combinational CCC  <=>  no SCC in the influence graph
  sequential   CCC  <=>  a size>=2 SCC = the cross-coupled storage loop = state.

No PDK, stdlib only, name-blind (nothing keys off ml_*/sl_*/clk*).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from engine.stages.stage1_ccc import decompose
from engine.types import CCCResult, Derivation, DeviceGraph

STAGE = "S1.seq"
RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}


# ---------------------------------------------------------------------------
# Structured result types (research-lane; do not touch engine/types.py contract)
# ---------------------------------------------------------------------------
@dataclass
class StorageLoop:
    """One cross-coupled feedback loop = one bit of state.

    nets   : the gate-controlling members of the SCC (the stored value + its
             complement), as found by stage1_ccc.
    role   : "master" | "slave" | "storage" | "stageK" -- copied from the
             stage1 labeling (influence-distance to output).
    """
    nets: List[str]
    role: str
    derivation: Derivation


@dataclass
class SeqStructure:
    cell: str
    is_sequential: bool                 # cell has >= 1 storage loop (SCC)
    storage_loops: List[StorageLoop]    # one per cross-coupled SCC, master..slave
    clock_pin: Optional[str]            # primary input identified as the clock
    clock_path: List[str]               # buffered clock nets between clock_pin and first loop
    ccc: CCCResult                      # the underlying stage1 result (provenance)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Influence graph (same construction as stage1_ccc.decompose: (gate,source)->drain)
# ---------------------------------------------------------------------------
def _influence(graph: DeviceGraph) -> Dict[str, Set[str]]:
    inf: Dict[str, Set[str]] = {}
    for dev in graph.devices:
        d, g, s = dev.terminals["d"], dev.terminals["g"], dev.terminals["s"]
        for src in (g, s):
            if src not in RAILS and d not in RAILS:
                inf.setdefault(src, set()).add(d)
    return inf


def _primary_inputs(graph: DeviceGraph) -> List[str]:
    driven = {d.terminals["d"] for d in graph.devices}
    return [p for p in graph.ports if p not in RAILS and p not in driven]


def _outputs(graph: DeviceGraph) -> List[str]:
    driven = {d.terminals["d"] for d in graph.devices}
    return [p for p in graph.ports if p in driven and p not in RAILS]


def _reach(adj: Dict[str, Set[str]], start: str, stop: Set[str]) -> Set[str]:
    """Nets reachable from `start`, NOT expanding past any net in `stop`
    (stop nets are included but their successors are not explored)."""
    seen = {start}
    q = deque([start])
    while q:
        x = q.popleft()
        if x in stop and x != start:
            continue
        for w in sorted(adj.get(x, ())):
            if w not in seen:
                seen.add(w)
                q.append(w)
    return seen


def _reach_all(adj: Dict[str, Set[str]], start: str) -> Set[str]:
    seen = {start}
    q = deque([start])
    while q:
        x = q.popleft()
        for w in sorted(adj.get(x, ())):
            if w not in seen:
                seen.add(w)
                q.append(w)
    return seen


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def extract(graph: DeviceGraph, ccc: Optional[CCCResult] = None) -> SeqStructure:
    """Extract sequential structure from a cell's DeviceGraph alone.

    Builds on stage1_ccc.decompose() (the engine core's CCC+SCC pass); groups its
    flat StateNode list into discrete storage loops, finds the clock pin and its
    buffered phase path, and reports the cell-level sequential discriminator.
    """
    if ccc is None:
        ccc = decompose(graph)
    inf = _influence(graph)

    # 1. Group StateNodes into loops by role (stage1 emits one role per SCC; the
    #    two nets of a cross-couple share a role).
    by_role: Dict[str, List[str]] = {}
    deriv_of: Dict[str, Derivation] = {}
    for sn in ccc.state_nodes:
        by_role.setdefault(sn.role, []).append(sn.net)
        deriv_of[sn.role] = sn.derivation
    role_order = sorted(by_role, key=_role_rank)   # input-side -> output-side
    loops = [StorageLoop(nets=sorted(by_role[r]), role=r, derivation=deriv_of[r])
             for r in role_order]

    is_seq = len(loops) > 0
    loop_net_sets = [set(l.nets) for l in loops]

    # 2. Clock pin: the primary input whose influence reaches the MOST storage
    #    loops (a clock gates every latch pass-gate; data feeds one). Tie-break by
    #    name for determinism.
    clock_pin: Optional[str] = None
    clock_path: List[str] = []
    if is_seq:
        pis = _primary_inputs(graph)
        reach_cache = {pi: _reach_all(inf, pi) for pi in pis}
        scored = sorted(
            ((sum(1 for s in loop_net_sets if reach_cache[pi] & s), pi) for pi in pis),
            key=lambda t: (-t[0], t[1]))
        if scored and scored[0][0] > 0:
            clock_pin = scored[0][1]
            all_loop_nets: Set[str] = set().union(*loop_net_sets)
            reached = _reach(inf, clock_pin, all_loop_nets)
            clock_path = sorted(n for n in reached
                                if n != clock_pin and n not in all_loop_nets
                                and n not in _outputs(graph))

    notes = [
        f"sequential discriminator (cell-level): "
        f"{'SEQUENTIAL' if is_seq else 'COMBINATIONAL'} -- {len(loops)} storage "
        f"loop(s) = cross-coupled SCC(s) in the influence graph (ARCHITECTURE.md "
        f"sec 8: comb CCC has no SCC, seq CCC has one)",
    ]
    for l in loops:
        notes.append(f"storage loop [{l.role}]: nets {l.nets}")
    if clock_pin:
        notes.append(f"clock pin: {clock_pin} (reaches all {len(loops)} storage "
                     f"loop(s)); buffered clock-path nets: "
                     f"{clock_path or '(none -- direct)'}")
    elif is_seq:
        notes.append("clock pin: UNRESOLVED (no single input reaches the loops)")

    return SeqStructure(
        cell=graph.cell, is_sequential=is_seq, storage_loops=loops,
        clock_pin=clock_pin, clock_path=clock_path, ccc=ccc, notes=notes)


def _role_rank(role: str) -> tuple:
    """Order roles input-side -> output-side: master, stage(high..low), slave,
    storage. (stage1 labels by influence-distance to output: master is farthest.)"""
    if role == "master":
        return (0, 0)
    if role.startswith("stage"):
        try:
            return (1, -int(role[5:]))
        except ValueError:
            return (1, 0)
    if role == "slave":
        return (2, 0)
    return (3, 0)   # "storage" (single-loop cell) or unknown


# ---------------------------------------------------------------------------
# Arc-level sequential discriminator + agreement check with the engine core.
# ---------------------------------------------------------------------------
def arc_traverses_storage(graph: DeviceGraph, rel_pin: str, output: str,
                          struct: Optional[SeqStructure] = None) -> bool:
    """True iff the influence path from rel_pin to `output` runs THROUGH a storage
    loop. The whole-arc sequential signal: a DFF's CP->Q arc is sequential even
    though Q's own CCC is a plain inverter, because the path traverses the latches.
    (Refines stage2_sensitize.is_combinational_arc, which is CCC-LOCAL to the
    output and so calls that same arc combinational -- see check_discriminator.)
    """
    if struct is None:
        struct = extract(graph)
    if not struct.is_sequential:
        return False
    inf = _influence(graph)
    reach = _reach_all(inf, rel_pin)
    if output not in reach:
        return False
    loop_nets: Set[str] = set().union(*(set(l.nets) for l in struct.storage_loops))
    if not (reach & loop_nets):
        return False
    for ln in (reach & loop_nets):
        if output in _reach_all(inf, ln):
            return True
    return False


def check_discriminator(graph: DeviceGraph, rel_pin: str, output: str,
                        is_comb_local: bool,
                        struct: Optional[SeqStructure] = None) -> str:
    """Reconcile the two discriminators and return a one-line provenance string.

    is_comb_local : result of stage2_sensitize.is_combinational_arc (CCC-local).
    They AGREE on whether the OUTPUT's local CCC is stateful; they may differ on
    whole-arc sequentiality, and that difference is expected and meaningful
    (documented in docs/research/sequential_fingerprint.md).
    """
    if struct is None:
        struct = extract(graph)
    arc_seq = arc_traverses_storage(graph, rel_pin, output, struct)
    local_seq = not is_comb_local
    if arc_seq == local_seq:
        return (f"discriminator AGREE: arc-traversal seq={arc_seq}, "
                f"CCC-local seq={local_seq}")
    return (f"discriminator REFINE: arc {rel_pin}->{output} traverses storage "
            f"(whole-arc sequential) but the output's own CCC is combinational "
            f"(CCC-local seq={local_seq}); both are correct at their scope")
