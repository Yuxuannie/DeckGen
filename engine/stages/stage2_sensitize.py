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
from engine.types import (Arc, CCCResult, CombSensitizationResult, CombState,
                          CombStatus, CombVerdict, Derivation, DeviceGraph,
                          SensitizationResult)
from engine.whencond import parse_when, parse_when_conjunction

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


# ---------------------------------------------------------------------------
# Combinational sensitization REGION (spec 2026-06-24, AOI/OAI accuracy).
# Boolean difference over the switch-level model: for the toggling pin P and each
# side-pin state s, does toggling P change the output O? -- gives SENSITIZING /
# BLOCKED region + a conduction-path signature SIG(s) per sensitizing state.
# ---------------------------------------------------------------------------
COMB_STAGE = "S2.comb"


def _inputs_outputs(graph: DeviceGraph):
    driven = {d.terminals["d"] for d in graph.devices}
    inputs = [p for p in graph.ports if p not in RAILS and p not in driven]
    outputs = [p for p in graph.ports if p in driven and p not in RAILS]
    return inputs, outputs


def _label(side: List[str], a: Dict[str, int]) -> str:
    return "&".join((p if a[p] else "!" + p) for p in side) or "(uncond)"


def _sig(graph: DeviceGraph, assign: Dict[str, int], out: str) -> frozenset:
    """SIG(s): the set of ON transistors in the output's channel-connected group
    -- the active conducting path to O under `assign`. Distinguishes e.g. a
    parallel-PMOS pull from a single-PMOS pull (the partition datum, SS3.5)."""
    v = switchlevel.evaluate(graph, assign)
    parent = {n: n for n in graph.nets}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    on = []
    for d in graph.devices:
        g = v[d.terminals["g"]]
        if (d.kind == "nmos" and g == 1) or (d.kind == "pmos" and g == 0):
            on.append(d)
            da, db = find(d.terminals["d"]), find(d.terminals["s"])
            if da != db:
                parent[max(da, db)] = min(da, db)
    grp = find(out)
    return frozenset(d.name for d in on
                     if find(d.terminals["d"]) == grp or find(d.terminals["s"]) == grp)


def _arc_ccc_has_state(graph: DeviceGraph, arc: Arc, ccc: CCCResult, out: str) -> bool:
    """True iff the channel-connected component FEEDING THIS ARC's output holds a
    state node. CCC-scoped (not whole-cell) so mixed cells need no rework."""
    comp = next((c for c in ccc.components if out in c), None)
    if comp is None:
        return bool(ccc.state_nodes)        # fall back to cell-level signal
    comp_nets = set(comp)
    return any(sn.net in comp_nets for sn in ccc.state_nodes)


def is_combinational_arc(graph: DeviceGraph, arc: Arc, ccc: CCCResult) -> bool:
    """Dispatch on STRUCTURE, not on arc_type: combinational iff the arc's CCC has
    no storage/feedback node (topology can't lie; the label can)."""
    _, outputs = _inputs_outputs(graph)
    out = _resolve_output(arc, outputs)
    return not _arc_ccc_has_state(graph, arc, ccc, out)


def _resolve_output(arc: Arc, outputs: List[str]) -> str:
    probe = arc.raw.get("probe_pin") or arc.constr_pin
    if probe in outputs:
        return probe
    return outputs[0] if outputs else (probe or "")


def derive_combinational(graph: DeviceGraph, arc: Arc,
                         ccc: CCCResult) -> CombSensitizationResult:
    """Derive the sensitization REGION of arc (rel_pin P -> output O) from topology
    alone (no read of arc.when). For each side-pin state, Boolean difference over
    the switch-level model decides SENSITIZING vs BLOCKED; SIG(s) is recorded per
    sensitizing state (partition hook)."""
    inputs, outputs = _inputs_outputs(graph)
    P = arc.rel_pin
    O = _resolve_output(arc, outputs)
    side = [i for i in inputs if i != P]

    sensitizing: List[CombState] = []
    blocked: List[CombState] = []
    for combo in product((0, 1), repeat=len(side)):
        s = dict(zip(side, combo))
        o0 = switchlevel.evaluate(graph, {**s, P: 0}).get(O)
        o1 = switchlevel.evaluate(graph, {**s, P: 1}).get(O)
        lbl = _label(side, s)
        if o0 is not None and o1 is not None and o0 != o1:
            out_dir = "R" if o1 > o0 else "F"          # output edge when P rises
            sig = _sig(graph, {**s, P: 1}, O)
            sensitizing.append(CombState(lbl, dict(s), out_dir, sig))
        else:
            blocked.append(CombState(lbl, dict(s), None, frozenset()))

    sig_groups = {cs.sig for cs in sensitizing}
    needs_split = len(sig_groups) > 1
    deriv = Derivation(
        [cs.label for cs in sensitizing],
        f"d(O={O})/d(P={P}) over switch-level model: {len(sensitizing)} sensitizing "
        f"state(s), {len(blocked)} blocked; {len(sig_groups)} SIG group(s)",
        COMB_STAGE)
    notes = [
        f"SENSITIZING({len(sensitizing)}/{2 ** len(side)}): "
        f"{[cs.label for cs in sensitizing]}",
        f"BLOCKED: {[cs.label for cs in blocked]}",
        f"SIG groups among sensitizing: {len(sig_groups)} "
        f"(needs_split={needs_split})",
    ]
    return CombSensitizationResult(
        rel_pin=P, output=O, side_pins=side, sensitizing=sensitizing,
        blocked=blocked, needs_split=needs_split, derivation=deriv, notes=notes)


def comb_verdict(result: CombSensitizationResult,
                 when_strings: List[str]) -> CombVerdict:
    """Region-equivalence verdict (spec SS3). cover(W_coll) vs SENSITIZING:
      MATCH iff cover == SENSITIZING and cover disjoint from BLOCKED.
    Unconditional arc (no -when): Option A -- cover := SENSITIZING, MATCH iff
      SENSITIZING != empty (a pin that can control O). Full-S is NOT assumed.
    Non-conjunction -when (OR): UNSUPPORTED-WHEN, never DIVERGENCE (SCLD guard)."""
    side = result.side_pins
    sens_keys = {_key(side, cs.assign) for cs in result.sensitizing}
    blocked_keys = {_key(side, cs.assign) for cs in result.blocked}
    all_states = [dict(zip(side, c)) for c in product((0, 1), repeat=len(side))]

    parsed = []
    for w in when_strings:
        c = parse_when_conjunction(w)
        if c is None:
            return CombVerdict(CombStatus.UNSUPPORTED_WHEN, [], [], [],
                               f"kit -when {w!r} is not a pure conjunction "
                               f"(OR/contradiction) -- cannot compute cover")
        parsed.append(c)

    unconditional = (not parsed) or any(len(c) == 0 for c in parsed)
    if unconditional:
        cover_keys = set(sens_keys)        # Option A: delegated to characterizer
    else:
        cover_keys = set()
        for c in parsed:
            for st in all_states:
                if all(st.get(p) == v for p, v in c.items()):
                    cover_keys.add(_key(side, st))

    def lbls(keys):
        return sorted(_label(side, dict(k)) for k in keys)

    missing = sens_keys - cover_keys       # topology sensitizes, kit omits
    extra = cover_keys - sens_keys         # kit marks sensitizing where blocked
    if unconditional:
        ok = len(sens_keys) > 0
        detail = (f"unconditional arc: SENSITIZING={lbls(sens_keys)} "
                  f"(non-empty={ok}); cover:=SENSITIZING per Option A")
    else:
        ok = (cover_keys == sens_keys) and not (cover_keys & blocked_keys)
        detail = (f"cover={lbls(cover_keys)} vs SENSITIZING={lbls(sens_keys)}; "
                  f"missing={lbls(missing)} extra={lbls(extra)}")
    status = CombStatus.MATCH if ok else CombStatus.DIVERGENCE
    return CombVerdict(status, lbls(cover_keys), lbls(missing), lbls(extra), detail)


def _key(side: List[str], a: Dict[str, int]):
    return tuple((p, a[p]) for p in side)
