"""
Stage 2 -- Sensitization derivation + P1 (spec SS5, SS9; SEGMENT 2).
  in : DeviceGraph + Arc + CCCResult        out: SensitizationResult

Method (Boolean difference over a switch-level model, stdlib -- no SAT solver):
  The measured arc captures the constraint pin (D) through the cell. Sensitization
  holds the non-measured inputs static so the D path is the only live capture
  path. We derive AND prove the bias purely FUNCTIONALLY (no reliance on whether a
  pin drives a gate vs a source, so it generalizes across mux styles):
    - break the latch feedback (Stage 1 storage cores) so the data path is clean;
    - find the transparent clock phase + a static assignment of the side pins under
      which toggling D changes the captured (master) node: d(capture)/d(D)=1;
    - then classify each side pin under that bias:
        * SET (a select, e.g. SE): toggling it changes capture -> its value is required;
        * MASKED (scan/data, e.g. SI): toggling it never changes capture -> the
          competing path is off; its static value is non-critical.
  P1 PASS iff D controls capture and the masked set is identified; else FAIL with
  what was tried.

`arc.raw["force_bias"]` ({pin: 0|1}, from --force-bias) constrains the side-pin
enumeration to the forced value(s) -- a FIXED assignment inside the search space,
never a post-hoc edit -- so a wrong forced bias yields a genuinely derived P1 FAIL
that names the competing capture path left unmasked.
"""
from __future__ import annotations

from itertools import product
from typing import Dict, List, Optional, Tuple

from engine import switchlevel
from engine.types import Arc, CCCResult, Derivation, DeviceGraph, SensitizationResult
from engine.whencond import parse_when

STAGE = "S2.sens"
RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}
# Default static hold for a masked side pin when the arc's when-string is silent.
MASKED_HOLD = 1


def derive(graph: DeviceGraph, arc: Arc, ccc: CCCResult) -> SensitizationResult:
    driven = {d.terminals["d"] for d in graph.devices}
    inputs = [p for p in graph.ports if p not in RAILS and p not in driven]
    constr, rel = arc.constr_pin, arc.rel_pin
    sides = [i for i in inputs if i not in (constr, rel)]

    forced = {p: int(v) for p, v in (arc.raw.get("force_bias") or {}).items()}
    bad = [p for p in forced if p not in sides]
    if bad:
        raise ValueError(
            f"--force-bias pin(s) {bad} are not side inputs of this arc "
            f"(rel={rel}, constr={constr}, valid sides={sides})")

    core = {sn.net for sn in ccc.state_nodes}
    broken = frozenset(d.name for d in graph.devices
                       if d.terminals["g"] in core and d.terminals["d"] in core)
    targets = [sn.net for sn in ccc.state_nodes if sn.role == "master"] \
        or [sn.net for sn in ccc.state_nodes]

    def tvals(assign: Dict[str, int]) -> Tuple[Optional[int], ...]:
        v = switchlevel.evaluate(graph, assign, broken)
        return tuple(v[t] for t in targets)

    def controls(cp: int, a: Dict[str, int], pin: str) -> bool:
        base = {rel: cp, **a}
        t0, t1 = tvals({**base, pin: 0}), tvals({**base, pin: 1})
        return any(x is not None and y is not None and x != y for x, y in zip(t0, t1))

    def pin_masked(cp: int, a: Dict[str, int], s: str) -> bool:
        for dval in (0, 1):
            base = {rel: cp, **a, constr: dval}
            if tvals({**base, s: 0}) != tvals({**base, s: 1}):
                return False
        return True

    found = None
    # force_bias pins enumerate only their forced value: a FIXED assignment
    # inside the search space, so the outcome is derived, not edited.
    choices = [(forced[s],) if s in forced else (0, 1) for s in sides]
    for cp in (0, 1):
        for vals in product(*choices):
            a = dict(zip(sides, vals))
            if controls(cp, a, constr):
                masked = [s for s in sides if pin_masked(cp, a, s)]
                setpins = [s for s in sides if s not in masked]
                found = (cp, a, setpins, masked)
                break
        if found:
            break

    when_bias = parse_when(arc.when)        # what the arc ASSERTS (for cross-check)
    side_biases: Dict[str, Derivation] = {}
    set_pins: List[str] = []
    masked_pins: List[str] = []
    if found:
        cp, a, setpins, masked = found
        set_pins, masked_pins = setpins, masked
        for s in setpins:
            side_biases[s] = Derivation(
                a[s], f"required select: {constr} is the live capture path only at "
                      f"{s}={a[s]} (toggling it changes capture)", STAGE)
        for s in masked:
            hold = when_bias.get(s, MASKED_HOLD)   # respect arc's value if given
            side_biases[s] = Derivation(
                hold, f"scan/side input masked: capture is independent of {s} under "
                      f"the select bias (path off); static hold {hold} "
                      f"(value non-critical)", STAGE)
        for s, v in forced.items():
            side_biases[s] = Derivation(
                v, "FORCED by user, overriding derivation", STAGE)
        proven = True
        clock_phase = f"{rel}={cp} (master transparent)"
        set_str = "{" + ", ".join(f"{s}={a[s]}" for s in setpins) + "}"
        obligation = (f"d({targets})/d({constr})=1 under {set_str}; "
                      f"capture independent of masked {masked or '(none)'}")
        masked_paths = [f"path via {s}: capture independent of it under {set_str}"
                        for s in masked]
        # cross-check derived-vs-arc.when (set pins must match; masked = non-critical)
        if when_bias:
            mism = [f"{s}: arc={when_bias[s]} derived={a[s]}"
                    for s in setpins if s in when_bias and when_bias[s] != a[s]]
            arc_check = (f"arc.when {dict(when_bias)} vs derived {set_str}: "
                         + ("AGREE [set pins match]" if not mism
                            else "DISAGREE " + "; ".join(mism)))
        else:
            arc_check = "arc.when: (none supplied) -- derived independently"
    else:
        proven = False
        clock_phase = ""
        obligation = (f"no static side-pin bias makes {constr} control capture "
                      + (f"under FORCED {forced} " if forced else "")
                      + f"(searched sides={sides}, both clock phases)")
        if forced:
            # Diagnostic (same Boolean-difference test, pointed at the other
            # pins): which capture path is LIVE instead of the constraint pin?
            competing = set()
            for cp in (0, 1):
                for vals in product(*choices):
                    a = dict(zip(sides, vals))
                    for s in sides:
                        if s in forced:
                            continue
                        if any(controls(cp, {**a, constr: dv}, s) for dv in (0, 1)):
                            competing.add(s)
            if competing:
                obligation += (f"; competing path LIVE: {sorted(competing)} "
                               f"control capture instead")
        masked_paths = []
        arc_check = "arc.when: not checked (P1 not proven)"
        for s in sides:
            if s in forced:
                side_biases[s] = Derivation(
                    forced[s], "FORCED by user, overriding derivation", STAGE)
            else:
                side_biases[s] = Derivation(
                    None, "PLACEHOLDER: P1 could not be proven", STAGE)

    return SensitizationResult(
        side_biases=side_biases, masked_paths=masked_paths,
        p1_obligation=obligation, proven=proven, clock_phase=clock_phase,
        set_pins=set_pins, masked_pins=masked_pins, arc_check=arc_check,
    )
