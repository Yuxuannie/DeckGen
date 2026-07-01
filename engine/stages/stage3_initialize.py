"""
Stage 3 -- Initialization derivation (drive-and-settle) + P2 inputs (spec SS5, SS9).
  in : DeviceGraph + CCCResult + Arc + SensitizationResult
  out: InitializationResult

DERIVE-ONLY (no simulator yet). What is computed here:
  - captured value of the constraint pin from the arc edge direction (stated
    HOLD CONVENTION: the value held just before the constrained edge -- a `fall`
    means it was 1 going into the capturing clock edge);
  - MASTER required pre-edge values: evaluated with the switch-level model while
    the master is transparent and D = captured value (the written node gets that
    value through the real data path; its cross-coupled complement = its inverse);
  - SLAVE required pre-edge value: by logical argument it holds the PRIOR value
    (complement of the captured value) so the capture produces an observable Q
    transition -- per-node polarity is confirmed later by P2 simulation;
  - a drive-and-settle pre-cycle plan and probe points (real extracted nodes).

A stateless evaluator cannot compute a latch's held value across the opaque
phase; that is exactly what P2's simulation verifies. So slave values are marked
as a derivation to be checked, not an evaluated fact.
"""
from __future__ import annotations

from typing import Dict, List

from engine import switchlevel
from engine.types import (
    Arc,
    CCCResult,
    Derivation,
    DeviceGraph,
    InitializationResult,
    SensitizationResult,
)

STAGE = "S3.init"
RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}


def _transparent_phase(sens: SensitizationResult) -> int:
    # sens.clock_phase looks like "CP=0 (master transparent)"
    try:
        return int(sens.clock_phase.split("=")[1].split()[0])
    except (IndexError, ValueError):
        return 0


def _precycle_from_seq(seq) -> Derivation:
    """Pre-cycle count = how many full clock cycles must precede the capturing
    edge to load the storage pipeline. Derived from the B2 structural class
    (duck-typed: .verdict, .bits[i].ff_depth, .reason). latch=0 (transparent),
    ff_chain=depth, multibit=deepest bit. seq is None (unclassified direct call)
    or an unsupported/combinational structure -> legacy 1, flagged in the reason
    (never silently assumed)."""
    if seq is None:
        return Derivation(1, "no structural class supplied; legacy 1 pre-cycle "
                             "loads the prior known value before capture", STAGE)
    v = seq.verdict
    if v == "latch":
        return Derivation(0, "latch is transparent -- no clocked pre-cycle", STAGE)
    if v in ("ff_chain", "multibit"):
        from engine.stages.stage1b_classify import depth_of
        n = depth_of(seq)
        return Derivation(n, "%s: %d pre-cycle(s) push the datum through %d "
                             "master/slave stage(s) before capture" % (v, n, n),
                          STAGE)
    return Derivation(1, "structure %s (%s); pre-cycle defaulted to 1 -- review"
                         % (v, seq.reason or "no reason"), STAGE)


def _probe_node(graph: DeviceGraph, net: str) -> str:
    """A real extracted node for a logical net, hierarchical. Prefer a net-anchor
    sub-node (`net#k`) over a device-pin node (`Xdev#g`) for readability."""
    raws = sorted(r for r, n in graph.node_to_net.items() if n == net)
    anchor = [r for r in raws if r.split("#")[0] == net]
    hashed = [r for r in raws if "#" in r]
    pick = anchor[0] if anchor else (hashed[0] if hashed else net)
    return f"x1.{pick}"


def derive(graph: DeviceGraph, ccc: CCCResult, arc: Arc,
           sens: SensitizationResult, seq=None) -> InitializationResult:
    rel, constr = arc.rel_pin, arc.constr_pin
    cap = 1 if arc.constr_dir == "fall" else 0       # HOLD CONVENTION (stated)
    conv = (f"hold convention: {constr} holds {cap} into the capturing edge "
            f"(value before the constrained {arc.constr_dir})")
    cp_t = _transparent_phase(sens)
    bias = {p: d.value for p, d in sens.side_biases.items() if d.value is not None}

    core = {sn.net for sn in ccc.state_nodes}
    broken = frozenset(d.name for d in graph.devices
                       if d.terminals["g"] in core and d.terminals["d"] in core)
    v_cap = switchlevel.evaluate(graph, {rel: cp_t, constr: cap, **bias}, broken)

    masters = [sn.net for sn in ccc.state_nodes if sn.role == "master"]
    slaves = [sn.net for sn in ccc.state_nodes
              if sn.role in ("slave", "storage")] or \
             [sn.net for sn in ccc.state_nodes if sn.net not in masters]

    required: Dict[str, Derivation] = {}

    # MASTER: evaluated. The written node has a defined value; its pair complement
    # is undriven once feedback is broken, so set it to the inverse analytically.
    mdef = [n for n in masters if v_cap.get(n) is not None]
    master_bit = None
    if len(mdef) == 1:
        w, b = mdef[0], v_cap[mdef[0]]
        master_bit = b
        required[w] = Derivation(
            b, f"master written node = captured value (switch-level eval, "
               f"{rel}={cp_t} transparent, {constr}={cap}); {conv}", STAGE)
        for n in masters:
            if n != w:
                required[n] = Derivation(
                    1 - b, f"cross-coupled complement of master written node {w}", STAGE)
    else:
        for n in masters:
            required[n] = Derivation(
                v_cap.get(n), f"master node (switch-level eval, {rel}={cp_t}, "
                              f"{constr}={cap}); {conv}", STAGE)

    # SLAVE: logical argument (per-node polarity verified at P2 sim). The pair is
    # complementary; we show a tentative polarity so the display is consistent.
    sbit = (1 - master_bit) if master_bit is not None else None
    for i, n in enumerate(slaves):
        v = sbit if (i == 0 or sbit is None) else 1 - sbit
        required[n] = Derivation(
            v, f"slave pair holds PRIOR value = complement of captured (stored "
               f"bit={sbit}); yields an observable Q transition. Per-node polarity "
               f"TENTATIVE -- confirmed at P2 sim", STAGE)

    prev = 1 - cap
    precycle_count = _precycle_from_seq(seq)
    n = precycle_count.value
    if n == 0:
        precycle_line = "* pre-cycle: none (transparent latch)"
    else:
        precycle_line = (f"* pre-cycle x{n}: {constr}={prev}, clock {rel} {n} full "
                         f"cycle(s) -> pipeline holds prior={prev}")
    stimulus = [
        f"* drive-and-settle (derived; {conv})",
        precycle_line,
        f"* capture : {constr}={cap}, {rel} {arc.rel_dir} edge captures the value",
        f"* hold    : {constr} {arc.constr_dir} after the edge; bisected by the measurement",
    ]
    probes = [_probe_node(graph, sn.net) for sn in ccc.state_nodes]

    return InitializationResult(
        required_state=required, stimulus=stimulus,
        precycle_count=precycle_count, probes=probes,
    )
