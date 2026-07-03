#!/usr/bin/env python3
"""
pitch_slides.py -- charge-resolve (on circuits) + LPE-roadmap pitch slides.

House style (white bg, blue/red/green/gray, Arial) -- same visual language as the
engine walkthrough deck; NO purple. The charge principle is explained with real
CAPACITOR-CIRCUIT schematics drawn by engine.charge_svg.circuit_case, with every
voltage read from resolve_checked(...).

Slide A1  charge resolve -- the principle, on circuits (4 canonical cases).
Slide A2  charge resolve -- the method + 3 SPICE-free invariants.
Slide B   from the LPE netlist: capabilities -> applications -> ask (honest tags).

Re-run:  python3 docs/engine_walkthrough/pitch_slides.py   (ASCII source only)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine.charge import resolve_checked
from engine.charge_svg import (circuit_case, _gnd, _capv, _caph, _node, _switch,
                               INK, BODY, MUTE, RULE, PANEL, HEAD, BLUE, GREEN,
                               RED, AMBER, GRN_BG, GRN_BD, SANS, MONO)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
W, H = 1536, 864


def _t(x, y, s, size=14, fill=INK, anchor="start", weight="normal", mono=False):
    f = MONO if mono else SANS
    return (f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' "
            f"fill='{fill}' font-weight='{weight}' {f}>"
            f"{str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}"
            f"</text>")


def _rect(x, y, w, h, fill="none", stroke="none", rx=0, sw=1):
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'/>")


def _ln(x1, y1, x2, y2, color=INK, sw=2):
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' "
            f"stroke-width='{sw}'/>")


def _arrow(x1, y1, x2, y2, color=INK, sw=2):
    dx, dy = x2 - x1, y2 - y1
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = x2 - ux * 10, y2 - uy * 10
    return (_ln(x1, y1, x2, y2, color, sw)
            + f"<polygon points='{x2:.1f},{y2:.1f} {bx+px*5:.1f},{by+py*5:.1f} "
              f"{bx-px*5:.1f},{by-py*5:.1f}' fill='{color}'/>")


def _pill(x, y, label, color, w=104):
    return (_rect(x, y, w, 20, "white", color, rx=10)
            + _t(x + w / 2, y + 14, label, 11, color, anchor="middle", weight="bold"))


def _head(title, subtitle):
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
         f"viewBox='0 0 {W} {H}'><rect width='{W}' height='{H}' fill='white'/>"]
    s.append(_t(56, 56, title, 28, INK, weight="bold"))
    s.append(_t(56, 86, subtitle, 15, MUTE))
    s.append(_ln(56, 102, W - 56, 102, RULE, 1.5))
    return s


def _honesty(s, y):
    s.append(_rect(56, y, W - 112, 44, "#FFF8E8", AMBER, rx=8))
    s.append(_t(72, y + 19, "all voltages are MODEL predictions, UNVERIFIED vs "
               "SPICE.", 13, "#8a6d00", weight="bold"))
    s.append(_t(72, y + 36, "this resolve feeds the eventual P3; a node with no rail "
               "reference resolves to X, not a guessed value.", 12.5, BODY))


def _cite(s, text):
    s.append(_t(56, H - 26, text, 12, MUTE, mono=True))


CASES = [
    ("scalar share: two nets merge through an ON device", "merge",
     dict(free_groups=[["dyn", "tap"]], Cg={"dyn": 1.0e-15, "tap": 0.3e-15},
          Cc={}, entry_V={"dyn": 0.45, "tap": 0.0}, fixed_V={})),
    ("coupling divider to a held aggressor", "divider",
     dict(free_groups=[["f"]], Cg={"f": 1.0e-15}, Cc={("agg", "f"): 0.5e-15},
          entry_V={"f": 0.0}, fixed_V={"agg": 0.45})),
    ("free-free coupling split (not the average)", "freefree",
     dict(free_groups=[["f1"], ["f2"]], Cg={"f1": 1.0e-15, "f2": 1.0e-15},
          Cc={("f1", "f2"): 0.8e-15}, entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={})),
    ("singular isolated island -> X (no rail reference)", "island",
     dict(free_groups=[["f1"], ["f2"]], Cg={}, Cc={("f1", "f2"): 0.8e-15},
          entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={})),
]


# ---------------------------------------------------------------------------
# Slide A1 -- the principle, on circuits
# ---------------------------------------------------------------------------
def slide_a1():
    s = _head("Charge-conservation resolve -- the principle, on circuits",
              "a floating internal node holds trapped charge Q = Cg * Ventry; the "
              "settled voltage is read off the capacitor network")
    cw, ch = 700, 224
    xs = [56, 56 + cw + 24]
    ys = [128, 128 + ch + 20]
    for i, (title, kind, kw) in enumerate(CASES):
        r = resolve_checked(**kw)
        col, row = i % 2, i // 2
        g, h = circuit_case(r, kw["Cg"], kw["Cc"], kw["entry_V"], kw["fixed_V"],
                            title, kind, xs[col], ys[row], cw, ch)
        s.append(g)
    _cite(s, "source: engine/charge.py resolve_checked(); drawn by "
             "engine/charge_svg.py circuit_case() -- model predictions, "
             "UNVERIFIED vs SPICE")
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# Slide A2 -- the method + invariants
# ---------------------------------------------------------------------------
def _flowbox(x, y, w, h, head, lines, accent):
    s = [_rect(x, y, w, h, PANEL, accent, rx=10),
         _rect(x, y, w, 26, HEAD, accent, rx=10), _rect(x, y + 16, w, 10, HEAD),
         _t(x + w / 2, y + 18, head, 13, accent, anchor="middle", weight="bold")]
    for i, ln in enumerate(lines):
        mono = any(t in ln for t in ("=", "Cg", "Cc", "A.", "Q", "_", "("))
        s.append(_t(x + w / 2, y + 50 + i * 19, ln, 11.5, BODY, anchor="middle",
                    mono=mono))
    return "".join(s)


def slide_a2():
    s = _head("Charge-conservation resolve -- the method",
              "SPICE-free: contract, stamp a capacitance matrix, solve; a singular "
              "island resolves to X")
    y = 142
    boxes = [
        ("1  cap_network", ["graph.caps (LPE) ->", "Cg grounded, Cc coupling",
                            "intra-net vanish"], BLUE),
        ("2  contract", ["ON-connected nets ->", "one super-node carrying",
                         "Q = SUM Cg * Ventry"], BLUE),
        ("3  coupling matrix", ["Cc stamps A.V = b ;", "held nodes inject",
                                "into the RHS b"], BLUE),
        ("4  solve", ["dense Gaussian solve", "-> V (model voltage)",
                      "singular -> X"], GREEN),
    ]
    bw, gap, x = 320, 40, 56
    for i, (hd, lines, acc) in enumerate(boxes):
        s.append(_flowbox(x, y, bw, 104, hd, lines, acc))
        if i < 3:
            s.append(_arrow(x + bw, y + 52, x + bw + gap, y + 52, INK))
        x += bw + gap

    iy = 326
    s.append(_t(56, iy, "Three SPICE-free invariants (each ends PASS / FAIL)", 18,
                INK, weight="bold"))
    inv = [
        ("residual", "the solver solved its own system:  ||A.V - b|| ~ 0"),
        ("convex-hull bound", "every resolved V lies within the boundary "
         "potentials (a cap M-matrix average) -- outside the hull = a bug"),
        ("scalar cross-check", "an uncoupled super-node equals the closed-form "
         "charge-share V"),
    ]
    yy = iy + 28
    for name, body in inv:
        s.append(_rect(56, yy, W - 112, 58, GRN_BG, GRN_BD, rx=8))
        s.append(_pill(72, yy + 19, "PASS", GREEN, 64))
        s.append(_t(150, yy + 25, name, 14, BLUE, weight="bold"))
        s.append(_t(150, yy + 46, body, 12.5, BODY))
        yy += 68

    _honesty(s, 712)
    _cite(s, "source: engine/charge.py resolve_checked() -- voltages, derivations, "
             "and these invariants all from one call")
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# Slide B1 -- what the engine can do FROM THE LPE NETLIST (capabilities)
# Slide B2 -- applications these outputs grow into (roadmap) + the ask
# ---------------------------------------------------------------------------
def _cap(x, y, w, title, pill_label, pill_color, body, cite, h=96):
    s = [_rect(x, y, w, h, PANEL, RULE, rx=10),
         _rect(x, y, 5, h, pill_color),                         # status accent rail
         _t(x + 20, y + 30, title, 16, INK, weight="bold"),
         _pill(x + w - 130, y + 15, pill_label, pill_color, 116),
         _t(x + 20, y + 56, body, 13, BODY)]
    if cite:
        s.append(_t(x + 20, y + 80, cite, 11.5, MUTE, mono=True))
    return "".join(s), h


def slide_b1():
    s = _head("What the engine can do FROM the LPE netlist",
              "structural + charge capabilities -- honest status: BUILT today / "
              "NEXT; every BUILT claim is true in the repo")
    s.append(_rect(56, 120, W - 112, 30, HEAD, BLUE, rx=8))
    s.append(_t(72, 140, "all of these read only the extracted LPE netlist -- no "
               "PDK, no cell documentation, no node naming", 13, INK, weight="bold"))
    items = [
        ("Structure from LPE", "BUILT", GREEN,
         "logical schematic (R-merge), CCC, the storage latches, and P1 "
         "sensitization -- all name-blind (S0-S2)",
         "engine/stages/  +  rename-invariance gate"),
        ("Charge resolve", "BUILT", GREEN,
         "floating internal-node voltage by charge conservation (Cg/Cc), checked "
         "by 3 SPICE-free invariants",
         "engine/charge.py (Pillar 3)  +  tests"),
        ("Coupling in the resolve", "BUILT", GREEN,
         "a held aggressor's coupling already enters the resolve -- the divider "
         "case, no separate layer needed", "engine/charge.py : resolve()"),
        ("Aggressor / victim impact", "NEXT", BLUE,
         "the coupling data (Cc) is already in hand; a dedicated impact-analysis "
         "layer is the next step (not built)", "(layer not built)"),
        ("Cell fingerprint from LPE", "ROADMAP", AMBER,
         "today's fingerprint is TEMPLATE-level (22 fingerprints -> 5 families / "
         "63 templates); a cell-level LPE fingerprint is ahead",
         "docs/foundation/D_template_calibration.md"),
    ]
    y = 168
    for it in items:
        g, h = _cap(56, y, W - 112, *it)
        s.append(g)
        y += h + 14
    _cite(s, "Built today: structure S0-S2, engine/charge.py (Pillar 3), "
             "P1/P2/P3 --verify sidecar (core/verify_sidecar.py).")
    s.append("</svg>")
    return "".join(s)


def slide_b2():
    s = _head("Applications these outputs grow into -- the roadmap",
              "all forward-looking; the engine has the capability base, the "
              "applications are co-built with your team")
    items = [
        ("Worst-case initialization", "HYPOTHESIS", AMBER,
         "the resolved internal voltage is exactly what a correct worst-case "
         "initialization must reflect; feeding the charge resolve into a "
         "worst-case-init query is the bridge",
         "today: S3 sync init is still a {None} placeholder -- not done"),
        ("AIQC feature", "DIRECTION", AMBER,
         "topology + charge as features for topology-aware sampling -- a "
         "structural upgrade to MLQC's sampling",
         "direction, not built"),
        ("Reverse-engineering from LPE", "DIRECTION", AMBER,
         "CCC + charge recover a cell's behaviour from its LPE structure alone, "
         "naming-independent -- a cell the team did not document becomes legible",
         "direction, not built"),
    ]
    y = 150
    for it in items:
        g, h = _cap(56, y, W - 112, *it, h=104)
        s.append(g)
        y += h + 18
    # the ask
    ay = 560
    s.append(_rect(56, ay, W - 112, 150, HEAD, BLUE, rx=12))
    s.append(_t(80, ay + 40, "The ask", 16, BLUE, weight="bold"))
    s.append(_t(80, ay + 74, "The engine has the capability base. Which application "
               "we build next -- and how -- depends on the problems your team most "
               "wants solved.", 16, INK, weight="bold"))
    s.append(_t(80, ay + 104, "The flows are co-built, with your team as the owner "
               "of what matters; that is the conversation we want to have.", 15,
               BODY))
    _cite(s, "capability base today: engine/charge.py (Pillar 3) + structure S0-S2; "
             "applications above are forward-looking.")
    s.append("</svg>")
    return "".join(s)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("pitch_a1_charge_circuits.svg", slide_a1),
                     ("pitch_a2_charge_method.svg", slide_a2),
                     ("pitch_b1_lpe_capabilities.svg", slide_b1),
                     ("pitch_b2_app_roadmap.svg", slide_b2)):
        with open(os.path.join(OUT, name), "w", encoding="ascii") as fh:
            fh.write(fn())
        print("wrote", os.path.join(OUT, name))


if __name__ == "__main__":
    main()
