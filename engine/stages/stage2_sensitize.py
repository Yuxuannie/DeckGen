"""
Stage 2 -- Sensitization derivation + P1 (spec SS5, SS9; SEGMENT 2).
  in : DeviceGraph + Arc + CCCResult        out: SensitizationResult

Method (technique survey Layer B / Boolean difference, stdlib -- no SAT solver):
  The measured arc captures the constraint pin (D) through the cell. Sensitization
  must make that the ONLY live capture path and mask the scan path. We derive and
  PROVE the side-pin bias structurally:
    - classify primary inputs: the constraint pin (D), the related/clock pin (CP),
      "select" side pins (appear as gates: e.g. SE) and "scan/data" side pins
      (appear as source/drain: e.g. SI);
    - break the latch feedback (Stage 1 storage cores) so the data path is clean;
    - via the switch-level evaluator, search the select-pin bias + transparent
      clock phase where toggling D changes the captured (master) node AND toggling
      the scan pin does not (Boolean difference: d(target)/d(D)=1, d(target)/d(SI)=0).
  The found bias is the P1 witness; if none exists, P1 FAILs with what was tried.
"""
from __future__ import annotations

from itertools import product
from typing import Dict, List

from engine import switchlevel
from engine.types import Arc, CCCResult, Derivation, DeviceGraph, SensitizationResult

STAGE = "S2.sens"
RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}


def derive(graph: DeviceGraph, arc: Arc, ccc: CCCResult) -> SensitizationResult:
    driven = {d.terminals["d"] for d in graph.devices}
    inputs = [p for p in graph.ports if p not in RAILS and p not in driven]
    constr, rel = arc.constr_pin, arc.rel_pin

    gate_pins = {d.terminals["g"] for d in graph.devices}
    sd_pins = set()
    for d in graph.devices:
        sd_pins |= {d.terminals["d"], d.terminals["s"]}

    sides = [i for i in inputs if i not in (constr, rel)]
    selects = [s for s in sides if s in gate_pins and s not in sd_pins]   # e.g. SE
    scans = [s for s in sides if s in sd_pins]                            # e.g. SI

    core = {sn.net for sn in ccc.state_nodes}
    broken = frozenset(d.name for d in graph.devices
                       if d.terminals["g"] in core and d.terminals["d"] in core)
    targets = [sn.net for sn in ccc.state_nodes if sn.role == "master"] \
        or [sn.net for sn in ccc.state_nodes]

    def tvals(assign: Dict[str, int]):
        v = switchlevel.evaluate(graph, assign, broken)
        return tuple(v[t] for t in targets)

    def d_controls(cp: int, sel: Dict[str, int]) -> bool:
        for sc in product((0, 1), repeat=len(scans)):
            base = {rel: cp, **sel, **dict(zip(scans, sc))}
            t0, t1 = tvals({**base, constr: 0}), tvals({**base, constr: 1})
            if any(a is not None and b is not None and a != b for a, b in zip(t0, t1)):
                return True
        return False

    def scan_masked(cp: int, sel: Dict[str, int]) -> bool:
        for dval in (0, 1):
            seen = {tvals({rel: cp, **sel, **dict(zip(scans, sc)), constr: dval})
                    for sc in product((0, 1), repeat=len(scans))}
            if len(seen) != 1:
                return False
        return True

    found = None
    for cp in (0, 1):
        for sel_vals in product((0, 1), repeat=len(selects)):
            sel = dict(zip(selects, sel_vals))
            if d_controls(cp, sel) and scan_masked(cp, sel):
                found = (cp, sel)
                break
        if found:
            break

    side_biases: Dict[str, Derivation] = {}
    if found:
        cp, sel = found
        for pin, v in sel.items():
            side_biases[pin] = Derivation(
                v, f"select bias: makes {constr} the live capture path and masks "
                   f"the scan path (proven by Boolean difference)", STAGE)
        for sp in scans:
            side_biases[sp] = Derivation(
                1, f"scan input masked under {sel}; held to a static non-interfering "
                   f"value (path off, polarity non-critical)", STAGE)
        proven = True
        clock_phase = f"{rel}={cp} (master transparent)"
        obligation = (f"d({targets})/d({constr})=1 and d/d({scans})=0 under "
                      f"{sel}, {clock_phase}")
        masked_paths = [f"scan path via {','.join(scans) or '(none)'}: capture "
                        f"independent of it under {sel}"]
    else:
        proven = False
        clock_phase = ""
        obligation = (f"no side-pin bias sensitizes {constr} while masking "
                      f"{scans} (searched selects={selects}, both clock phases)")
        masked_paths = []
        for s in selects + scans:
            side_biases[s] = Derivation(None, "PLACEHOLDER: P1 could not be proven", STAGE)

    return SensitizationResult(
        side_biases=side_biases, masked_paths=masked_paths,
        p1_obligation=obligation, proven=proven, clock_phase=clock_phase,
    )
