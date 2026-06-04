"""
engine/viz.py -- one-screen ASCII visualization of sensitization + initialization.

Renders, side by side, what the engine DERIVED so a reviewer can validate it
against their knowledge of the cell from a single screenshot (spec SS7.4):
  - SENSITIZATION (P1): the live capture path vs the masked scan path, the derived
    side-pin bias, and arc.when-vs-derived agreement.
  - INITIALIZATION (P2): the structural master/slave storage nodes, their required
    pre-edge values, and the drive-and-settle plan (filled as Stage 3 lands).

ASCII only (no non-ASCII bytes). Built from the PipelineResult.
"""
from __future__ import annotations

from engine.types import PipelineResult, PStatus

W = 80


def _bar(ch="="):
    return ch * W


def render(r: PipelineResult) -> str:
    arc, sens, ccc, init = r.arc, r.sens, r.ccc, r.init
    roles = {}
    for sn in ccc.state_nodes:
        roles.setdefault(sn.role, []).append(sn.net)
    master = roles.get("master", [])
    slave = roles.get("slave", roles.get("storage", []))

    constr, rel = arc.constr_pin, arc.rel_pin
    set_str = ", ".join(f"{p}={sens.side_biases[p].value}" for p in sens.set_pins) or "(none)"
    mask_str = ", ".join(f"{p}={sens.side_biases[p].value}" for p in sens.masked_pins) or "(none)"
    p1 = r.verdict.p1.status.value

    L = []
    L.append(_bar())
    L.append(f" SENSITIZATION (P1: {p1})    arc: {arc.label()}")
    L.append(_bar("-"))
    L.append(f"  measured input : {constr} (toggles)        clock: {rel}")
    L.append(f"  required select: {set_str}        masked: {mask_str}")
    L.append(f"  arc-check      : {sens.arc_check}")
    L.append("")
    sel_label = sens.set_pins[0] + "=" + str(sens.side_biases[sens.set_pins[0]].value) \
        if sens.set_pins else "select"
    L.append(f"   {constr:<3} ==[ {sel_label} selects {constr} ]==> (mux) --> "
             f"[master {','.join(master)}]")
    L.append(f"                                              ==({rel})==> "
             f"[slave {','.join(slave)}] --> Q")
    for mp in sens.masked_pins:
        L.append(f"   {mp:<3} --[ masked ]--> X   (scan path off, cannot inject)")
    L.append("")
    L.append(_bar())
    p2 = r.verdict.p2.status.value
    L.append(f" INITIALIZATION (P2: {p2})")
    L.append(_bar("-"))
    for sn in ccc.state_nodes:
        d = init.required_state.get(sn.net)
        val = d.value if d else "?"
        probe = "yes" if sn.net in init.probes else "no"
        L.append(f"  [{sn.role:<6} {sn.net:<14}] required pre-edge: {val!s:<6} probe: {probe}")
    L.append(f"  pre-cycle (drive-and-settle): {init.precycle_count.value}  "
             f"then capturing {rel} edge, then {constr} change (hold bisect)")
    L.append(_bar())
    return "\n".join(L)
