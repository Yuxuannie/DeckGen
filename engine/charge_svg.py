"""
engine/charge_svg.py -- vector (SVG) view of a Pillar 3 charge resolve.

Same role as engine/charge_viz.py:render (the ASCII audit), but emits a clean,
self-contained SVG card so a charge resolve can be embedded in a slide in the
same house style as engine/draw.py:render_svg. Every number on the card is read
from the ChargeResolve (and the cap-network inputs) -- nothing is hardcoded, so
the figure can never drift from what the engine actually resolved.

Pure function, stdlib only, ASCII source. Theme tokens are the pitch deck's
purple set; geometry/conventions mirror engine/draw.py (viewBox, hairlines,
restrained type, monospace identifiers).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from engine.charge import ChargeResolve

# -- theme (pitch deck purple) --
PURPLE = "#5B3E8E"
PURPLE2 = "#7E5BB5"
LAV = "#E7DEF4"
LAV2 = "#F6F2FB"
INK = "#211C30"
BODY = "#3C3654"
MUTE = "#8A82A0"
RULE = "#D7CFE8"
GREEN = "#2E8B57"
AMBER = "#B8860B"
SANS = ("font-family='Arial, Helvetica, sans-serif'")
MONO = ("font-family='Courier New, monospace'")


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _t(x, y, s, size=13, fill=INK, anchor="start", weight="normal", mono=False):
    f = MONO if mono else SANS
    return (f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' "
            f"fill='{fill}' font-weight='{weight}' {f}>{_esc(s)}</text>")


def _rect(x, y, w, h, fill="none", stroke="none", rx=0, sw=1):
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'/>")


def _vfmt(v: Optional[float]) -> str:
    return "X" if v is None else f"{v:+.5f}"


def _neighbors(net: str, Cc: Dict[Tuple[str, str], float]) -> str:
    out = []
    for (a, b), c in sorted(Cc.items()):
        if a == net:
            out.append(f"{b}:{c:.3g}")
        elif b == net:
            out.append(f"{a}:{c:.3g}")
    return ", ".join(out) if out else "-"


def _method_tag(result: ChargeResolve) -> Tuple[str, str]:
    """One-word method + color for the card, read from the resolve itself."""
    if result.singular:
        return "X (no rail ref)", AMBER
    reasons = " ".join(d.reason for d in result.derivations.values())
    if "matrix solve" in reasons or "coupled charge balance" in reasons:
        return "matrix solve", PURPLE
    return "charge-share", PURPLE2


def card(result: ChargeResolve,
         Cg: Dict[str, float],
         Cc: Dict[Tuple[str, str], float],
         entry_V: Dict[str, float],
         fixed_V: Dict[str, float],
         title: str,
         x: float = 0.0, y: float = 0.0, w: float = 700.0) -> Tuple[str, float]:
    """Positioned <g> for one resolve case; returns (svg, height). Numbers come
    from `result` (resolved V, derivations, checks) and the cap inputs."""
    nodes = sorted(result.voltages)
    rowh = 26
    head_h = 30
    n_fixed = len(fixed_V)
    body_top = y + head_h + 24                      # below header + column row
    table_h = rowh * len(nodes)
    fixed_h = (18 + 18 * n_fixed) if n_fixed else 0
    deriv_h = 40
    h = head_h + 24 + table_h + fixed_h + deriv_h + 30
    s = [_rect(x, y, w, h, LAV2, RULE, rx=10)]
    s.append(_rect(x, y, w, head_h, LAV, RULE, rx=10))
    s.append(_rect(x, y + head_h - 10, w, 10, LAV))   # square off header bottom
    s.append(_t(x + 14, y + 20, title, 14, PURPLE, weight="bold"))
    tag, tagc = _method_tag(result)
    s.append(_rect(x + w - 150, y + 7, 136, 18, "white", tagc, rx=9))
    s.append(_t(x + w - 82, y + 20, tag, 11, tagc, anchor="middle", weight="bold"))

    # column header
    cx = [x + 14, x + 120, x + 220, x + 330, x + 450]
    cy = y + head_h + 18
    for cxi, lab in zip(cx, ["node", "Cg(F)", "entry_V", "resolved_V", "coupling"]):
        s.append(_t(cxi, cy, lab, 11, MUTE, weight="bold"))
    s.append(f"<line x1='{x+12}' y1='{cy+6}' x2='{x+w-12}' y2='{cy+6}' "
             f"stroke='{RULE}' stroke-width='1'/>")
    ry = body_top + 20
    for net in nodes:
        v = result.voltages[net]
        s.append(_t(cx[0], ry, net, 12, INK, mono=True))
        s.append(_t(cx[1], ry, f"{Cg.get(net, 0.0):.3g}", 12, BODY, mono=True))
        ev = entry_V.get(net)
        s.append(_t(cx[2], ry, "-" if ev is None else f"{ev:+.4g}", 12, BODY, mono=True))
        s.append(_t(cx[3], ry, _vfmt(v), 13, (AMBER if v is None else PURPLE),
                    weight="bold", mono=True))
        s.append(_t(cx[4], ry, _neighbors(net, Cc), 11, MUTE, mono=True))
        ry += rowh

    if fixed_V:
        s.append(_t(x + 14, ry + 4, "fixed (held/driven) neighbor:", 11, MUTE,
                    weight="bold"))
        ry += 22
        for net in sorted(fixed_V):
            s.append(_t(x + 26, ry, f"{net} = {fixed_V[net]:+.4g} V   "
                       f"couples: {_neighbors(net, Cc)}", 11, BODY, mono=True))
            ry += 18

    # derivation + verdict
    first = result.derivations[nodes[0]].reason if nodes else ""
    if len(first) > 86:
        first = first[:84] + ".."
    s.append(f"<line x1='{x+12}' y1='{ry+2}' x2='{x+w-12}' y2='{ry+2}' "
             f"stroke='{RULE}' stroke-width='1'/>")
    s.append(_t(x + 14, ry + 22, first, 10.5, BODY, mono=True))
    vstat = "OK" if result.ok else "REVIEW"
    vcol = GREEN if result.ok else AMBER
    s.append(_rect(x + w - 92, ry + 9, 78, 18, "white", vcol, rx=9))
    s.append(_t(x + w - 53, ry + 22, vstat, 11, vcol, anchor="middle", weight="bold"))
    return "".join(s), h


def render_svg(result: ChargeResolve,
               Cg: Dict[str, float],
               Cc: Dict[Tuple[str, str], float],
               entry_V: Dict[str, float],
               fixed_V: Dict[str, float],
               title: str = "") -> str:
    """Standalone SVG for one charge-resolve case (house-style, vector)."""
    pad = 16
    w = 700
    body, h = card(result, Cg, Cc, entry_V, fixed_V, title or "charge resolve",
                   pad, pad, w)
    W, H = w + 2 * pad, h + 2 * pad
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
            f"viewBox='0 0 {W} {H}'><rect width='{W}' height='{H}' fill='white'/>"
            f"{body}</svg>")
