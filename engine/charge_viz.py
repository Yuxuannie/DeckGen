"""
engine/charge_viz.py -- one-screen ASCII view of a Pillar 3 charge resolve.

Renders, from a single screenshot (spec SS7.4 house style), everything a reviewer
needs to audit a floating-node charge resolve WITHOUT running SPICE:
  - per resolved node: grounded cap, entry (trapped) voltage, resolved voltage,
    and its coupling neighbors;
  - the fixed (held/driven) nodes that couple into the set;
  - the SPICE-free invariant checks (residual, hull bound, scalar cross-check)
    each ending PASS/FAIL;
  - a VERDICT line.

ASCII only. Pure function of a ChargeResolve + the cap network + the inputs.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from engine.charge import ChargeResolve

W = 78


def _bar(ch: str = "=") -> str:
    return ch * W


def _fmt(v: Optional[float]) -> str:
    return "   X    " if v is None else f"{v:+.5f}"


def _neighbors(net: str, Cc: Dict[Tuple[str, str], float]) -> str:
    out = []
    for (a, b), c in sorted(Cc.items()):
        if a == net:
            out.append(f"{b}:{c:.3g}")
        elif b == net:
            out.append(f"{a}:{c:.3g}")
    return ", ".join(out) if out else "-"


def render(result: ChargeResolve,
           Cg: Dict[str, float],
           Cc: Dict[Tuple[str, str], float],
           entry_V: Dict[str, float],
           fixed_V: Dict[str, float],
           title: str = "") -> str:
    L = [_bar(), f" CHARGE RESOLVE -- {title}".rstrip(), _bar()]

    L.append(f" {'node':<10}{'Cg(F)':>11}{'entry_V':>11}{'resolved_V':>12}"
             f"  coupling")
    L.append(" " + "-" * (W - 2))
    for net in sorted(result.voltages):
        cg = Cg.get(net, 0.0)
        ev = entry_V.get(net)
        ev_s = "    -   " if ev is None else f"{ev:+.5f}"
        L.append(f" {net:<10}{cg:>11.3g}{ev_s:>11}{_fmt(result.voltages[net]):>12}"
                 f"  {_neighbors(net, Cc)}")

    if fixed_V:
        L.append("")
        L.append(" fixed (held/driven) neighbors:")
        for net in sorted(fixed_V):
            L.append(f"   {net:<10} = {fixed_V[net]:+.5f} V   "
                     f"coupling: {_neighbors(net, Cc)}")

    L.append("")
    L.append(" DERIVATIONS")
    for net in sorted(result.derivations):
        d = result.derivations[net]
        L.append(f"   {net:<10}: {d.reason}")

    L.append("")
    L.append(" INVARIANTS (SPICE-free)")
    for c in result.checks:
        L.append(f"   {c}")

    L.append("")
    L.append(f" VERDICT: {'OK' if result.ok else 'REVIEW (see FAIL/X above)'}")
    L.append(_bar())
    return "\n".join(L) + "\n"


def _demo() -> str:
    """Render the spec SS7 hand-calc cases -- a one-command visual self-check.
    Run: python3 -m engine.charge_viz   (all values are UNVERIFIED vs SPICE)."""
    from engine.charge import resolve_checked
    cases = {
        "scalar share (dyn+tap merge through ON device)": dict(
            free_groups=[["dyn", "tap"]], Cg={"dyn": 1.0e-15, "tap": 0.3e-15},
            Cc={}, entry_V={"dyn": 0.45, "tap": 0.0}, fixed_V={}),
        "coupling divider bump to fixed aggressor": dict(
            free_groups=[["f"]], Cg={"f": 1.0e-15}, Cc={("agg", "f"): 0.5e-15},
            entry_V={"f": 0.0}, fixed_V={"agg": 0.45}),
        "free-free coupling split (not the average)": dict(
            free_groups=[["f1"], ["f2"]], Cg={"f1": 1.0e-15, "f2": 1.0e-15},
            Cc={("f1", "f2"): 0.8e-15}, entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={}),
        "singular isolated coupling island (-> X)": dict(
            free_groups=[["f1"], ["f2"]], Cg={}, Cc={("f1", "f2"): 0.8e-15},
            entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={}),
    }
    out = ["NOTE: all voltages are MODEL predictions, UNVERIFIED vs SPICE.\n"]
    for title, kw in cases.items():
        r = resolve_checked(**kw)
        out.append(render(r, kw["Cg"], kw["Cc"], kw["entry_V"], kw["fixed_V"], title))
    return "\n".join(out)


if __name__ == "__main__":
    print(_demo())
