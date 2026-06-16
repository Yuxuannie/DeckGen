#!/usr/bin/env python3
"""
pitch_slides.py -- the charge-resolve + LPE-roadmap pitch slides (after S2).

Slide A1  charge resolve -- the method (cap_network -> Cg/Cc -> contract ->
          matrix A.V=b -> solve -> V; X for a singular island; 3 invariants).
Slide A2  charge resolve -- engine output: the canonical cases, drawn by
          engine.charge_svg.card from real resolve_checked(...) results.
Slide B   from the LPE netlist: capabilities -> applications -> ask, every item
          carrying an honest status tag that matches the repo.

White background, 16:9, purple theme. Slide A numbers come from engine.charge,
never hardcoded. Re-run after editing:  python3 docs/engine_walkthrough/pitch_slides.py
ASCII source only.
"""
import os
import sys

# allow running as a script from anywhere: put the repo root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine.charge import resolve_checked
from engine.charge_svg import card, PURPLE, PURPLE2, LAV, LAV2, INK, BODY, MUTE, \
    RULE, GREEN, AMBER, SANS, MONO

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")
W, H = 1536, 864


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _t(x, y, s, size=14, fill=INK, anchor="start", weight="normal", mono=False):
    f = MONO if mono else SANS
    return (f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' "
            f"fill='{fill}' font-weight='{weight}' {f}>{_esc(s)}</text>")


def _rect(x, y, w, h, fill="none", stroke="none", rx=0, sw=1):
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'/>")


def _arrow(x1, y1, x2, y2, color=PURPLE, sw=2):
    dx, dy = x2 - x1, y2 - y1
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = x2 - ux * 10, y2 - uy * 10
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' "
            f"stroke-width='{sw}'/><polygon points='{x2:.1f},{y2:.1f} "
            f"{bx+px*5:.1f},{by+py*5:.1f} {bx-px*5:.1f},{by-py*5:.1f}' "
            f"fill='{color}'/>")


def _pill(x, y, label, color, w=104):
    return (_rect(x, y, w, 20, "white", color, rx=10)
            + _t(x + w / 2, y + 14, label, 11, color, anchor="middle", weight="bold"))


def _head(title, subtitle):
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
         f"viewBox='0 0 {W} {H}'><rect width='{W}' height='{H}' fill='white'/>"]
    s.append(_t(56, 58, title, 30, INK, weight="bold"))
    s.append(_t(56, 88, subtitle, 16, MUTE))
    s.append(f"<line x1='56' y1='104' x2='{W-56}' y2='104' stroke='{RULE}' "
             f"stroke-width='1.5'/>")
    return s


def _flowbox(x, y, w, h, head, lines, accent):
    s = [_rect(x, y, w, h, LAV2, accent, rx=10),
         _rect(x, y, w, 26, LAV, accent, rx=10),
         _rect(x, y + 16, w, 10, LAV),
         _t(x + w / 2, y + 18, head, 13, accent, anchor="middle", weight="bold")]
    for i, ln in enumerate(lines):
        mono = any(t in ln for t in ("=", "Cg", "Cc", "A.", "V", "Q", "(", "_"))
        s.append(_t(x + w / 2, y + 50 + i * 19, ln, 11.5, BODY, anchor="middle",
                    mono=mono))
    return "".join(s)


def _honesty(s, y):
    s.append(_rect(56, y, W - 112, 44, "#FFF8E8", AMBER, rx=8))
    s.append(_t(72, y + 19, "all voltages are MODEL predictions, UNVERIFIED vs "
               "SPICE.", 13, "#8a6d00", weight="bold"))
    s.append(_t(72, y + 36, "this resolve feeds the eventual P3; a node with no rail "
               "reference resolves to X, not a guessed value.", 12.5, BODY))


def _cite(s, text):
    s.append(_t(56, H - 28, text, 12.5, MUTE, mono=True))


# ---------------------------------------------------------------------------
# Slide A1 -- the method
# ---------------------------------------------------------------------------
def slide_a1():
    s = _head("Charge-conservation resolve (Pillar 3) -- the method",
              "floating internal-node voltage by charge conservation; SPICE-free, "
              "every step auditable")
    y = 150
    boxes = [
        ("1  cap_network", ["graph.caps (LPE) ->", "Cg grounded, Cc coupling",
                            "intra-net vanish"], PURPLE),
        ("2  contract", ["ON-connected nets ->", "one super-node carrying",
                         "Q = SUM Cg * Ventry"], PURPLE),
        ("3  coupling matrix", ["Cc stamps A.V = b ;", "fixed (held) nodes",
                                "inject into the RHS"], PURPLE),
        ("4  solve", ["dense Gaussian solve", "-> V (model voltage)", ""], PURPLE2),
    ]
    bw, gap = 320, 40
    x = 56
    for i, (head, lines, acc) in enumerate(boxes):
        s.append(_flowbox(x, y, bw, 108, head, lines, acc))
        if i < len(boxes) - 1:
            s.append(_arrow(x + bw, y + 54, x + bw + gap, y + 54))
        x += bw + gap
    # singular branch
    sx = 56 + 3 * (bw + gap)
    s.append(_arrow(sx + bw / 2, y + 108, sx + bw / 2, y + 150))
    s.append(_rect(sx, y + 150, bw, 40, "#FFF8E8", AMBER, rx=8))
    s.append(_t(sx + bw / 2, y + 168, "singular: no rail reference", 12, "#8a6d00",
                anchor="middle", weight="bold"))
    s.append(_t(sx + bw / 2, y + 184, "-> X (not a fabricated value)", 11.5, BODY,
                anchor="middle", mono=True))

    # invariants panel
    iy = 400
    s.append(_t(56, iy, "Three SPICE-free invariants (each ends PASS / FAIL)", 18,
                INK, weight="bold"))
    inv = [
        ("residual", "the solver solved its own system: ||A.V - b|| ~ 0"),
        ("convex-hull bound", "every resolved V lies within the boundary "
         "potentials (a cap M-matrix average) -- outside = a bug"),
        ("scalar cross-check", "an uncoupled super-node equals the closed-form "
         "charge-share V"),
    ]
    yy = iy + 30
    for name, body in inv:
        s.append(_rect(56, yy, W - 112, 56, LAV2, RULE, rx=8))
        s.append(_pill(72, yy + 18, "PASS", GREEN, 64))
        s.append(_t(150, yy + 24, name, 14, PURPLE, weight="bold"))
        s.append(_t(150, yy + 44, body, 12.5, BODY))
        yy += 66

    _honesty(s, 700)
    _cite(s, "source: engine/charge.py (Pillar 3) -- resolve_checked(); render "
             "engine/charge_svg.py")
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# Slide A2 -- engine output (the canonical cases, real numbers)
# ---------------------------------------------------------------------------
def slide_a2():
    s = _head("Charge-conservation resolve -- engine output (canonical cases)",
              "every number below is produced by resolve_checked(...), drawn by "
              "engine.charge_svg -- not hand-entered")
    cases = [
        ("scalar share: two nets merge through an ON device",
         dict(free_groups=[["dyn", "tap"]], Cg={"dyn": 1.0e-15, "tap": 0.3e-15},
              Cc={}, entry_V={"dyn": 0.45, "tap": 0.0}, fixed_V={})),
        ("coupling divider to a FIXED aggressor",
         dict(free_groups=[["f"]], Cg={"f": 1.0e-15}, Cc={("agg", "f"): 0.5e-15},
              entry_V={"f": 0.0}, fixed_V={"agg": 0.45})),
        ("free-free coupling split (NOT the average)",
         dict(free_groups=[["f1"], ["f2"]], Cg={"f1": 1.0e-15, "f2": 1.0e-15},
              Cc={("f1", "f2"): 0.8e-15}, entry_V={"f1": 0.45, "f2": 0.0},
              fixed_V={})),
        ("singular isolated island -> X (no rail reference)",
         dict(free_groups=[["f1"], ["f2"]], Cg={}, Cc={("f1", "f2"): 0.8e-15},
              entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={})),
    ]
    cw = 700
    xs = [56, 56 + cw + 24]
    ys = [128, 128]
    rowmax = [128, 128]
    for i, (title, kw) in enumerate(cases):
        r = resolve_checked(**kw)
        col = i % 2
        g, h = card(r, kw["Cg"], kw["Cc"], kw["entry_V"], kw["fixed_V"], title,
                    xs[col], ys[col], cw)
        s.append(g)
        ys[col] += h + 22
    _cite(s, "source: engine/charge.py resolve_checked(); engine/charge_svg.py "
             "render -- model predictions, UNVERIFIED vs SPICE")
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# Slide B -- from the LPE netlist: capabilities -> applications -> ask
# ---------------------------------------------------------------------------
def _item(x, y, w, title, pill_label, pill_color, body, cite):
    s = [_rect(x, y, w, 92, LAV2, RULE, rx=10)]
    s.append(_t(x + 16, y + 28, title, 15, INK, weight="bold"))
    s.append(_pill(x + w - 120, y + 14, pill_label, pill_color))
    s.append(_t(x + 16, y + 52, body, 12.5, BODY))
    if cite:
        s.append(_t(x + 16, y + 76, cite, 11.5, MUTE, mono=True))
    return "".join(s), 92


def slide_b():
    s = _head("From the LPE netlist: capabilities -> applications -> ask",
              "honest status -- BUILT today / NEXT / forward-looking; every BUILT "
              "claim is true in the repo")
    colw = 700
    lx, rx = 56, 56 + colw + 24
    s.append(_t(lx, 138, "What the engine can do from the LPE netlist", 17, PURPLE,
                weight="bold"))
    s.append(_t(rx, 138, "Applications these outputs grow into", 17, PURPLE,
                weight="bold"))

    left = [
        ("Charge resolve", "BUILT", GREEN,
         "floating internal-node voltage by charge conservation (Cg/Cc), "
         "invariant-checked", "engine/charge.py"),
        ("Coupling in the resolve", "BUILT", GREEN,
         "a fixed aggressor's coupling already enters the resolve (the divider "
         "case)", "engine/charge.py : resolve()"),
        ("Aggressor / victim impact", "NEXT", PURPLE,
         "the coupling data (Cc) is in hand; a dedicated impact-analysis layer is "
         "the next step", "(layer not built)"),
        ("Cell fingerprint from LPE", "ROADMAP", AMBER,
         "today's fingerprint is TEMPLATE-level (22 fingerprints -> 5 families / "
         "63 templates); cell-level LPE fingerprint is ahead",
         "docs/foundation/D_template_calibration.md"),
    ]
    right = [
        ("Worst-case initialization", "HYPOTHESIS", AMBER,
         "the resolved internal voltage is what a correct worst-case init must "
         "reflect (S3 sync init is still a {None} placeholder)", "forward-looking"),
        ("AIQC feature", "DIRECTION", AMBER,
         "topology + charge as features for topology-aware sampling, upgrading "
         "MLQC", "forward-looking"),
        ("Reverse-engineering", "DIRECTION", AMBER,
         "CCC + charge recover cell behaviour from LPE structure, "
         "naming-independent", "forward-looking"),
    ]
    y = 156
    for title, pl, pc, body, cite in left:
        g, h = _item(lx, y, colw, title, pl, pc, body, cite)
        s.append(g)
        y += h + 16
    y = 156
    for title, pl, pc, body, cite in right:
        g, h = _item(rx, y, colw, title, pl, pc, body, cite)
        s.append(g)
        y += h + 16

    # ask bar
    ay = 640
    s.append(_rect(56, ay, W - 112, 96, LAV, PURPLE, rx=12))
    s.append(_t(76, ay + 32, "The engine has the capability base. Which application "
               "we build next -- and how -- depends on the problems your team most "
               "wants solved.", 15, INK, weight="bold"))
    s.append(_t(76, ay + 60, "The flows are co-built, with your team as the owner of "
               "what matters; that is the conversation we want to have.", 14, BODY))
    _cite(s, "Built today: engine/charge.py (Pillar 3), P1/P2/P3 --verify sidecar "
             "(core/verify_sidecar.py).")
    s.append("</svg>")
    return "".join(s)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("pitch_a1_charge_method.svg", slide_a1),
                     ("pitch_a2_charge_cases.svg", slide_a2),
                     ("pitch_b_lpe_roadmap.svg", slide_b)):
        with open(os.path.join(OUT, name), "w", encoding="ascii") as fh:
            fh.write(fn())
        print("wrote", os.path.join(OUT, name))


if __name__ == "__main__":
    main()
