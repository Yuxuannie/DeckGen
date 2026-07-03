"""
sensitize_bridge.py -- derive combinational side-pin biases from the LPE netlist
(the engine's Boolean-difference, scoped to a combinational arc), so the deck
recipe can DERIVE the WHEN side-pin holds from structure instead of copying
template.tcl -- and flag where the two disagree.

Combinational sensitization (no clock, no latch feedback): find a static
assignment of the side inputs under which toggling the measured input changes the
measured output (d(out)/d(in) = 1). A side pin that never changes the output is
masked (its hold value is non-critical).

Engine imports are LAZY and failures degrade to (None, reason) -- the caller then
keeps the collateral WHEN. Never raises. Stdlib only, ASCII.
"""
from __future__ import annotations

from itertools import product
from typing import Dict, List, Optional, Tuple

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}


def side_inputs(netlist_pins: str, rel_pin: str, output_pins: str) -> List[str]:
    """The candidate held inputs: ports minus rails, the toggling pin, outputs."""
    outs = set((output_pins or "").split())
    return [p for p in (netlist_pins or "").split()
            if p not in RAILS and p != rel_pin and p not in outs]


def derive_combinational_biases(
        netlist_text: str, cell: str, rel_pin: str, probe_pin: str,
        side_pins: List[str],
        fixed: Optional[Dict[str, int]] = None,
        ) -> Tuple[Optional[Dict[str, int]], str]:
    """Return ({side_pin: 0|1}, reason) for a sensitizing hold, or (None, reason).

    The returned bias holds every side pin at a value under which toggling
    rel_pin flips probe_pin. Pins whose value never matters are still given a
    concrete (valid) hold; the reason notes which were masked.

    `fixed` constrains specific side pins (e.g. a collateral WHEN): the search
    ranges only over the remaining free pins, so a non-None result means the
    fixed assignment CAN sensitize the arc and None means it cannot. This is how
    a collateral WHEN is verified -- two equally valid sensitizing vectors (or a
    held don't-care) are not a contradiction; only a WHEN that fails to
    sensitize is.
    """
    fixed = dict(fixed or {})
    free = [p for p in side_pins if p not in fixed]
    if len(free) > 16:                          # guard the 2^n search
        return None, "too many free side inputs (%d) for exhaustive search" % len(free)
    try:
        from engine.stages import stage0_parse
        from engine import switchlevel
    except Exception as e:                      # engine not importable
        return None, "engine unavailable: %s" % e
    try:
        graph = stage0_parse.parse(netlist_text, cell)
    except Exception as e:
        return None, "netlist parse failed: %s" % e
    if not graph.devices:
        return None, "no transistors in netlist (placeholder?) -- cannot derive"
    if probe_pin not in graph.nets:
        return None, "output pin %r not a net in the parsed netlist" % probe_pin

    def out(assign: Dict[str, int]) -> Optional[int]:
        return switchlevel.evaluate(graph, assign).get(probe_pin)

    found = None
    for vals in product((0, 1), repeat=len(free)):
        a = {**fixed, **dict(zip(free, vals))}
        v0, v1 = out({rel_pin: 0, **a}), out({rel_pin: 1, **a})
        if v0 is not None and v1 is not None and v0 != v1:
            found = a
            break
    if found is None:
        constr = (" with %s fixed" % fixed) if fixed else ""
        return None, ("no static side bias makes %s control %s%s (searched %s)"
                      % (rel_pin, probe_pin, constr, free))

    masked = []
    for s in side_pins:
        change = False
        for rv in (0, 1):
            base = {rel_pin: rv, **found}
            if out({**base, s: 0}) != out({**base, s: 1}):
                change = True
                break
        if not change:
            masked.append(s)
    reason = ("derived: toggling %s flips %s under %s%s"
              % (rel_pin, probe_pin, found,
                 ("; masked=%s" % masked) if masked else ""))
    return found, reason


def collateral_biases(when: str, rel_pin: str, constr_pin: str) -> Dict[str, int]:
    """The {side_pin: 0|1} the collateral WHEN asserts (skips rel/constr pins)."""
    out: Dict[str, int] = {}
    if when and when != "NO_CONDITION":
        for cond in when.split("&"):
            cond = cond.strip()
            if not cond:
                continue
            pin = cond.lstrip("!")
            if pin in (rel_pin, constr_pin):
                continue
            out[pin] = 0 if cond.startswith("!") else 1
    return out
