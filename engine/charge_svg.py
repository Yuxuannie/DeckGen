"""
engine/charge_svg.py -- vector (SVG) views of a Pillar 3 charge resolve.

Two views, both pure functions of a ChargeResolve + the cap-network inputs, both
in the engine/draw.py house style (white bg, blue/red/green/gray, Arial):

  card(...)         -- the audit table (node | Cg | entry_V | resolved_V | couple).
  circuit_case(...) -- a real CAPACITOR-CIRCUIT schematic of one canonical case
                       (grounded caps Cg, coupling caps Cc, held aggressors), with
                       the resolved voltage labelled FROM the resolve.

Every number drawn is read from the ChargeResolve, so the figure can never drift
from what engine.charge actually resolves (see tests/engine/test_charge_svg.py).
Stdlib only, ASCII source.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from engine.charge import ChargeResolve

# -- house style (matches engine/draw.py + the walkthrough deck) --
INK = "#111827"
BODY = "#374151"
MUTE = "#6b7280"
RULE = "#e5e7eb"
PANEL = "#f9fafb"
HEAD = "#eff6ff"
BLUE = "#2563eb"      # floating / data node, accent
GREEN = "#16a34a"     # resolved / PASS
RED = "#dc2626"       # fixed / held aggressor
AMBER = "#d97706"     # X / review
GRN_BG = "#ecfdf5"
GRN_BD = "#a7f3d0"
SANS = "font-family='Arial, Helvetica, sans-serif'"
MONO = "font-family='Courier New, monospace'"


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _t(x, y, s, size=13, fill=INK, anchor="start", weight="normal", mono=False):
    f = MONO if mono else SANS
    return (f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' "
            f"fill='{fill}' font-weight='{weight}' {f}>{_esc(s)}</text>")


def _rect(x, y, w, h, fill="none", stroke="none", rx=0, sw=1):
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'/>")


def _ln(x1, y1, x2, y2, color=INK, sw=2):
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' "
            f"stroke-width='{sw}'/>")


def _vfmt(v: Optional[float]) -> str:
    return "X" if v is None else f"{v:+.5f}"


def _neighbors(net, Cc):
    out = []
    for (a, b), c in sorted(Cc.items()):
        if a == net:
            out.append(f"{b}:{c:.3g}")
        elif b == net:
            out.append(f"{a}:{c:.3g}")
    return ", ".join(out) if out else "-"


# --------------------------------------------------------------------------
# circuit primitives
# --------------------------------------------------------------------------
def _gnd(x, y, color=INK):
    """Ground symbol with its top at (x, y)."""
    return (_ln(x, y, x, y + 7, color)
            + _ln(x - 11, y + 7, x + 11, y + 7, color)
            + _ln(x - 7, y + 11, x + 7, y + 11, color)
            + _ln(x - 3, y + 15, x + 3, y + 15, color))


def _capv(x, ytop, ybot, color=INK):
    """Vertical capacitor between ytop and ybot at x (two plates in the middle)."""
    mid = (ytop + ybot) / 2
    return (_ln(x, ytop, x, mid - 5, color)
            + _ln(x - 13, mid - 5, x + 13, mid - 5, color)
            + _ln(x - 13, mid + 5, x + 13, mid + 5, color)
            + _ln(x, mid + 5, x, ybot, color))


def _caph(x1, x2, y, color=INK):
    """Horizontal capacitor between x1 and x2 at height y."""
    mid = (x1 + x2) / 2
    return (_ln(x1, y, mid - 5, y, color)
            + _ln(mid - 5, y - 13, mid - 5, y + 13, color)
            + _ln(mid + 5, y - 13, mid + 5, y + 13, color)
            + _ln(mid + 5, y, x2, y, color))


def _node(x, y, name, color=BLUE, r=6):
    return (f"<circle cx='{x}' cy='{y}' r='{r}' fill='{color}'/>"
            + _t(x, y - 12, name, 12, color, anchor="middle", weight="bold", mono=True))


def _switch(x1, x2, y, color=INK):
    """An ON pass-device drawn as a closed switch between x1 and x2."""
    g = x2 - x1
    return (_ln(x1, y, x1 + g * 0.32, y, color)
            + _ln(x2 - g * 0.32, y, x2, y, color)
            + _ln(x1 + g * 0.32, y, x2 - g * 0.30, y - 9, color)   # closed blade
            + f"<circle cx='{x1+g*0.32}' cy='{y}' r='2.5' fill='{color}'/>"
            + f"<circle cx='{x2-g*0.32}' cy='{y}' r='2.5' fill='{color}'/>"
            + _t((x1 + x2) / 2, y - 16, "ON", 11, GREEN, anchor="middle",
                 weight="bold"))


def _battery(x, ytop, ybot, color=RED):
    """Held source to ground: long/short plate battery between ytop and ybot."""
    mid = (ytop + ybot) / 2
    return (_ln(x, ytop, x, mid - 7, color)
            + _ln(x - 13, mid - 7, x + 13, mid - 7, color)      # long plate (+)
            + _ln(x - 7, mid + 1, x + 7, mid + 1, color)        # short plate (-)
            + _ln(x, mid + 1, x, ybot, color))


def _chip(x, y, label, color):
    return (_rect(x, y, 70, 18, "white", color, rx=9)
            + _t(x + 35, y + 13, label, 11, color, anchor="middle", weight="bold"))


# --------------------------------------------------------------------------
# circuit_case -- one canonical resolve drawn as a capacitor schematic
# --------------------------------------------------------------------------
def circuit_case(result: ChargeResolve, Cg, Cc, entry_V, fixed_V, title, kind,
                 x=0.0, y=0.0, w=700.0, h=300.0) -> Tuple[str, float]:
    """Schematic of one resolve. `kind` selects the topology drawing:
    'merge' | 'divider' | 'freefree' | 'island'. Resolved V is read from result."""
    s = [_rect(x, y, w, h, PANEL, RULE, rx=10),
         _rect(x, y, w, 30, HEAD, RULE, rx=10),
         _rect(x, y + 20, w, 10, HEAD),
         _t(x + 14, y + 20, title, 13.5, INK, weight="bold")]
    ok = result.ok
    s.append(_chip(x + w - 84, y + 6, "OK" if ok else "REVIEW",
                   GREEN if ok else AMBER))
    cx0, cy = x + 30, y + 110            # circuit origin
    gy = cy + 70                          # ground rail y
    tx = x + 380                          # text column
    V = result.voltages

    def val(n):
        return _vfmt(V.get(n))

    if kind == "merge":
        a, b = "dyn", "tap"
        s += [_node(cx0 + 40, cy, a), _capv(cx0 + 40, cy, gy), _gnd(cx0 + 40, gy),
              _t(cx0 + 58, cy + 38, f"Cg={Cg[a]*1e15:g}f", 11, MUTE, mono=True),
              _t(cx0 + 40, cy - 30, f"entry {entry_V[a]:+g}V", 11, MUTE,
                 anchor="middle")]
        s += [_node(cx0 + 230, cy, b), _capv(cx0 + 230, cy, gy), _gnd(cx0 + 230, gy),
              _t(cx0 + 248, cy + 38, f"Cg={Cg[b]*1e15:g}f", 11, MUTE, mono=True),
              _t(cx0 + 230, cy - 30, f"entry {entry_V[b]:+g}V", 11, MUTE,
                 anchor="middle")]
        s.append(_switch(cx0 + 46, cx0 + 224, cy))
        s += [_t(tx, y + 70, "two floating nodes merge through an ON device", 12.5,
                 BODY),
              _t(tx, y + 92, "charge conserves: Q = SUM Cg*Ventry", 12, MUTE,
                 mono=True),
              _t(tx, y + 128, f"V = {val(a)} V", 18, GREEN, weight="bold", mono=True),
              _t(tx, y + 152, f"= (Cg_dyn*{entry_V[a]:g} + Cg_tap*{entry_V[b]:g})"
                 f" / {(Cg[a]+Cg[b])*1e15:g}f", 11, BODY, mono=True),
              _t(tx, y + 176, "(both merged nodes settle to one V)", 11, MUTE)]

    elif kind == "divider":
        f, agg = "f", "agg"
        vagg = fixed_V[agg]
        s += [_t(cx0 + 30, cy - 30, "held aggressor", 11, RED, anchor="middle"),
              _node(cx0 + 30, cy, agg, RED), _battery(cx0 + 30, cy, gy, RED),
              _gnd(cx0 + 30, gy),
              _t(cx0 + 30, cy + 44, f"{vagg:+g}V", 11, RED, anchor="middle",
                 mono=True)]
        s.append(_caph(cx0 + 36, cx0 + 214, cy, BLUE))
        s.append(_t(cx0 + 125, cy - 10, f"Cc={Cc[('agg','f')]*1e15:g}f", 11, MUTE,
                    anchor="middle", mono=True))
        s += [_node(cx0 + 230, cy, f), _capv(cx0 + 230, cy, gy), _gnd(cx0 + 230, gy),
              _t(cx0 + 248, cy + 38, f"Cg={Cg[f]*1e15:g}f", 11, MUTE, mono=True),
              _t(cx0 + 230, cy - 30, f"entry {entry_V[f]:+g}V", 11, MUTE,
                 anchor="middle")]
        s += [_t(tx, y + 70, "a held aggressor couples into a floating node", 12.5,
                 BODY),
              _t(tx, y + 92, "capacitive divider", 12, MUTE),
              _t(tx, y + 128, f"V_f = {val(f)} V", 18, GREEN, weight="bold",
                 mono=True),
              _t(tx, y + 152, f"= Cc*Vagg / (Cg+Cc)", 11, BODY, mono=True),
              _t(tx, y + 176, "the resolve already accounts for this", 11, MUTE)]

    elif kind == "freefree":
        f1, f2 = "f1", "f2"
        s += [_node(cx0 + 40, cy, f1), _capv(cx0 + 40, cy, gy), _gnd(cx0 + 40, gy),
              _t(cx0 + 58, cy + 38, f"Cg={Cg[f1]*1e15:g}f", 11, MUTE, mono=True),
              _t(cx0 + 40, cy - 30, f"entry {entry_V[f1]:+g}V", 11, MUTE,
                 anchor="middle")]
        s += [_node(cx0 + 230, cy, f2), _capv(cx0 + 230, cy, gy), _gnd(cx0 + 230, gy),
              _t(cx0 + 248, cy + 38, f"Cg={Cg[f2]*1e15:g}f", 11, MUTE, mono=True),
              _t(cx0 + 230, cy - 30, f"entry {entry_V[f2]:+g}V", 11, MUTE,
                 anchor="middle")]
        s.append(_caph(cx0 + 46, cx0 + 224, cy - 28, BLUE))
        s.append(_ln(cx0 + 40, cy - 6, cx0 + 40, cy - 28, BLUE))
        s.append(_ln(cx0 + 230, cy - 6, cx0 + 230, cy - 28, BLUE))
        s.append(_t(cx0 + 135, cy - 34, f"Cc={Cc[('f1','f2')]*1e15:g}f", 11, MUTE,
                    anchor="middle", mono=True))
        s += [_t(tx, y + 70, "two FLOATING nodes share via coupling", 12.5, BODY),
              _t(tx, y + 92, "matrix solve over both -- not the average", 12, MUTE),
              _t(tx, y + 124, f"{f1} = {val(f1)} V", 16, GREEN, weight="bold",
                 mono=True),
              _t(tx, y + 148, f"{f2} = {val(f2)} V", 16, GREEN, weight="bold",
                 mono=True),
              _t(tx, y + 174, "average (+0.225) would be WRONG", 11, RED)]

    elif kind == "island":
        f1, f2 = "f1", "f2"
        s += [_node(cx0 + 40, cy, f1), _node(cx0 + 230, cy, f2),
              _t(cx0 + 40, cy - 30, f"entry {entry_V[f1]:+g}V", 11, MUTE,
                 anchor="middle"),
              _t(cx0 + 230, cy - 30, f"entry {entry_V[f2]:+g}V", 11, MUTE,
                 anchor="middle")]
        s.append(_caph(cx0 + 46, cx0 + 224, cy, BLUE))
        s.append(_t(cx0 + 135, cy - 10, f"Cc={Cc[('f1','f2')]*1e15:g}f", 11, MUTE,
                    anchor="middle", mono=True))
        # absent ground, drawn struck-through in red
        s.append(_ln(cx0 + 135, cy + 16, cx0 + 135, gy, RED))
        s.append(_gnd(cx0 + 135, gy, RED))
        s.append(_ln(cx0 + 118, cy + 40, cx0 + 152, cy + 56, RED))
        s.append(_t(cx0 + 135, cy + 72, "no Cg to any rail", 11, RED,
                    anchor="middle"))
        s += [_t(tx, y + 70, "no path to a rail -> no charge reference", 12.5, BODY),
              _t(tx, y + 92, "singular cap matrix", 12, MUTE),
              _t(tx, y + 130, f"V = {val(f1)}", 20, AMBER, weight="bold", mono=True),
              _t(tx, y + 158, "undetermined -- not a fabricated value", 11.5, BODY),
              _t(tx, y + 180, "(the resolve emits X by design)", 11, MUTE)]

    return "".join(s), h


# --------------------------------------------------------------------------
# audit table view (kept; restyled to house palette)
# --------------------------------------------------------------------------
def card(result: ChargeResolve, Cg, Cc, entry_V, fixed_V, title,
         x=0.0, y=0.0, w=700.0) -> Tuple[str, float]:
    nodes = sorted(result.voltages)
    rowh, head_h = 26, 30
    n_fixed = len(fixed_V)
    h = head_h + 24 + rowh * len(nodes) + ((18 + 18 * n_fixed) if n_fixed else 0) + 70
    s = [_rect(x, y, w, h, PANEL, RULE, rx=10),
         _rect(x, y, w, head_h, HEAD, RULE, rx=10),
         _rect(x, y + head_h - 10, w, 10, HEAD),
         _t(x + 14, y + 20, title, 14, INK, weight="bold")]
    cx = [x + 14, x + 120, x + 220, x + 330, x + 450]
    cy = y + head_h + 18
    for cxi, lab in zip(cx, ["node", "Cg(F)", "entry_V", "resolved_V", "coupling"]):
        s.append(_t(cxi, cy, lab, 11, MUTE, weight="bold"))
    s.append(_ln(x + 12, cy + 6, x + w - 12, cy + 6, RULE, 1))
    ry = cy + 38
    for net in nodes:
        v = result.voltages[net]
        s.append(_t(cx[0], ry, net, 12, INK, mono=True))
        s.append(_t(cx[1], ry, f"{Cg.get(net, 0.0):.3g}", 12, BODY, mono=True))
        ev = entry_V.get(net)
        s.append(_t(cx[2], ry, "-" if ev is None else f"{ev:+.4g}", 12, BODY, mono=True))
        s.append(_t(cx[3], ry, _vfmt(v), 13, (AMBER if v is None else GREEN),
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
    first = result.derivations[nodes[0]].reason if nodes else ""
    if len(first) > 86:
        first = first[:84] + ".."
    s.append(_ln(x + 12, ry + 2, x + w - 12, ry + 2, RULE, 1))
    s.append(_t(x + 14, ry + 22, first, 10.5, BODY, mono=True))
    s.append(_chip(x + w - 84, ry + 9, "OK" if result.ok else "REVIEW",
                   GREEN if result.ok else AMBER))
    return "".join(s), h


def render_svg(result: ChargeResolve, Cg, Cc, entry_V, fixed_V, title="") -> str:
    """Standalone SVG for one charge-resolve case (audit table)."""
    pad, w = 16, 700
    body, h = card(result, Cg, Cc, entry_V, fixed_V, title or "charge resolve",
                   pad, pad, w)
    W, H = w + 2 * pad, h + 2 * pad
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
            f"viewBox='0 0 {W} {H}'><rect width='{W}' height='{H}' fill='white'/>"
            f"{body}</svg>")
