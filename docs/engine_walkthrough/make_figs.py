#!/usr/bin/env python3
"""
make_figs.py -- generate PPT-ready SVG figures for the engine walkthrough.

Dependency-free (hand-emitted SVG; PowerPoint/Keynote/Google Slides insert SVG
natively and keep it crisp at any size). Re-run after editing:

    python3 docs/engine_walkthrough/make_figs.py

Writes into docs/engine_walkthrough/figs/. ASCII source only.

The S1 figure uses the ACTUAL storage mapping the engine derived for
SDFSYNC4RPQSXGMZD1BWP130HPNPN3P48CPD (corner ssgnp_0p450v_m40c), so the slide is
about the real cell, not a cartoon.
"""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")

# palette (PPT-friendly, high contrast on white)
INK = "#111827"
MUTE = "#6b7280"
RAW = "#9ca3af"
NET = "#10b981"
DATA = "#2563eb"
DATA_BG = "#eff6ff"
CLK = "#d97706"
CLR = "#dc2626"
PASS = "#16a34a"
PANEL = "#f9fafb"
PANEL_BD = "#e5e7eb"
FONT = ("font-family='DejaVu Sans, Arial, Helvetica, sans-serif'")


def _t(x, y, s, size=14, anchor="start", fill=INK, weight="normal", style=""):
    return (f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' "
            f"fill='{fill}' font-weight='{weight}' {FONT} {style}>{s}</text>")


def _rect(x, y, w, h, fill="none", stroke="none", rx=0, sw=1, dash=""):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'{d}/>")


def _line(x1, y1, x2, y2, color=INK, sw=2, dash="", marker=True):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    m = " marker-end='url(#arrow)'" if marker else ""
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' "
            f"stroke-width='{sw}'{d}{m}/>")


def _xcouple(cx, cy, color):
    """Tiny back-to-back inverter glyph = a cross-coupled (bistable) pair."""
    p = []
    p.append(f"<polygon points='{cx-16},{cy-7} {cx-2},{cy} {cx-16},{cy+7}' "
             f"fill='none' stroke='{color}' stroke-width='1.5'/>")
    p.append(f"<polygon points='{cx+16},{cy-7} {cx+2},{cy} {cx+16},{cy+7}' "
             f"fill='none' stroke='{color}' stroke-width='1.5'/>")
    p.append(f"<line x1='{cx-2}' y1='{cy}' x2='{cx+2}' y2='{cy}' "
             f"stroke='{color}' stroke-width='1.5'/>")
    return "".join(p)


def _header(w, h):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' "
            f"viewBox='0 0 {w} {h}'>"
            f"<defs><marker id='arrow' markerWidth='10' markerHeight='10' "
            f"refX='8' refY='3' orient='auto'>"
            f"<path d='M0,0 L8,3 L0,6 Z' fill='{INK}'/></marker></defs>"
            f"<rect width='{w}' height='{h}' fill='white'/>")


# ---------------------------------------------------------------------------
# Figure S0 -- de-parasitic R-merge
# ---------------------------------------------------------------------------
def fig_s0():
    W, H = 1200, 560
    s = [_header(W, H)]
    s.append(_t(40, 46, "Stage 0 -- recover the logical schematic from the LPE netlist",
                24, weight="bold"))
    s.append(_t(40, 74, "real cells ship as layout-extracted soup; connectivity is "
                "carried by parasitic resistors, not direct wires", 15, fill=MUTE))

    # left panel: LPE soup
    s.append(_rect(40, 100, 440, 360, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 130, "LPE netlist (as delivered)", 16, weight="bold"))
    soup = [("XMSA2#d", 90, 175), ("XMSA2#g", 200, 165), ("XMSA3#s", 330, 185),
            ("ml_a#1", 110, 245), ("ml_a#2", 250, 255), ("XMLA0#d", 360, 245),
            ("clkb#1", 95, 330), ("XCKA1#d", 235, 340), ("mq_a#3", 360, 330),
            ("seb#2", 150, 405), ("XSEA1#d", 300, 410)]
    # a few parasitic-R zigzags between nearby raw nodes
    rpairs = [(0, 1), (1, 2), (3, 4), (4, 5), (6, 7), (7, 8), (9, 10)]
    for a, b in rpairs:
        x1, y1 = soup[a][1], soup[a][2]
        x2, y2 = soup[b][1], soup[b][2]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 10
        s.append(f"<polyline points='{x1},{y1} {mx-8},{my} {mx},{my-12} "
                 f"{mx+8},{my} {x2},{y2}' fill='none' stroke='{RAW}' "
                 f"stroke-width='1.5'/>")
    for name, x, y in soup:
        s.append(f"<circle cx='{x}' cy='{y}' r='5' fill='{RAW}'/>")
        s.append(_t(x + 8, y + 4, name, 11, fill=MUTE))
    s.append(_t(60, 445, "689 raw nodes  *  1033 parasitic R  *  C ignored for DC",
                13, fill=MUTE, style="font-style='italic'"))

    # middle: the operation
    s.append(_line(500, 280, 690, 280, INK, 3))
    s.append(_t(595, 262, "R-merge", 16, anchor="middle", weight="bold"))
    s.append(_t(595, 312, "short every R,", 13, anchor="middle", fill=MUTE))
    s.append(_t(595, 330, "union-find contract", 13, anchor="middle", fill=MUTE))

    # right panel: recovered logical nets
    s.append(_rect(710, 100, 450, 360, DATA_BG, DATA, rx=12))
    s.append(_t(730, 130, "logical schematic (recovered)", 16, weight="bold", fill=DATA))
    blobs = [("CP", 800, 185), ("mq_a", 950, 175), ("mq_b", 1080, 200),
             ("ml_a", 820, 270), ("Q", 1060, 290), ("seb", 900, 355),
             ("clkb", 1050, 370)]
    for name, x, y in blobs:
        s.append(f"<ellipse cx='{x}' cy='{y}' rx='34' ry='20' fill='white' "
                 f"stroke='{NET}' stroke-width='2'/>")
        s.append(_t(x, y + 5, name, 14, anchor="middle", weight="bold", fill=INK))
    s.append(_t(730, 445, "92 logical nets  *  the real circuit nodes",
                13, fill=DATA, style="font-style='italic'"))

    # bottom banner
    s.append(_rect(40, 490, 1120, 50, PANEL, PANEL_BD, rx=10))
    s.append(_t(60, 521,
               "689 raw nodes  ->  92 logical nets  via 1033 R   |   164 transistors   |   ",
               16, weight="bold"))
    s.append(_t(880, 521, "bridges = 0", 16, weight="bold", fill=PASS))
    s.append(_t(995, 521, "(no mis-merge -- PASS)", 14, fill=PASS))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# Figure S1 -- structural storage detection (the real cell's 8 latches)
# ---------------------------------------------------------------------------
def fig_s1():
    W, H = 1500, 640
    s = [_header(W, H)]
    s.append(_t(40, 46, "Stage 1 -- find the storage latches from STRUCTURE, not names",
                24, weight="bold"))
    s.append(_t(40, 74, "39 channel-connected components; 8 are bistable feedback loops "
                "(cross-coupled SCC in the influence graph) -- a 4-stage synchronizer, "
                "2 latches per stage", 15, fill=MUTE))

    # 8 latch boxes in signal order D -> Q (= farthest-to-Q first)
    # (role, primary, [member nets], half)  half: M=master-latch, S=slave-latch
    chain = [
        ("master", "mq", ["mq_a", "mq_b", "mq_x"], "M"),
        ("stage1", "qf", ["qf_a", "qf_cx", "qf_x"], "S"),
        ("stage2", "mq2", ["mq2_a", "mq2_b", "mq2_x"], "M"),
        ("stage3", "qf2", ["qf2_a", "qf2_cx", "qf2_x"], "S"),
        ("stage4", "mq3", ["mq3_a", "mq3_b", "mq3_x"], "M"),
        ("stage5", "qf3", ["qf3_a", "qf3_cx", "qf3_x"], "S"),
        ("stage6", "mq4", ["mq4_a", "mq4_b", "mq4_x"], "M"),
        ("slave", "qf4", ["qf4_a", "qf4_cx", "qf4_x"], "S"),
    ]
    bw, bh, gap, x0, y0 = 158, 150, 14, 60, 150
    centers = []
    for i, (role, prim, mem, half) in enumerate(chain):
        x = x0 + i * (bw + gap)
        centers.append((x + bw / 2, x, x + bw))
        fill = DATA_BG if half == "M" else "#fff7ed"
        bd = DATA if half == "M" else CLK
        s.append(_rect(x, y0, bw, bh, fill, bd, rx=10, sw=2))
        s.append(_t(x + bw / 2, y0 + 26, role, 15, anchor="middle",
                    weight="bold", fill=bd))
        s.append(_t(x + bw / 2, y0 + 50, prim, 22, anchor="middle", weight="bold"))
        s.append(_xcouple(x + bw / 2, y0 + 74, bd))
        s.append(_t(x + bw / 2, y0 + 100,
                    f"{half}-latch ({'master' if half=='M' else 'slave'})",
                    11, anchor="middle", fill=MUTE))
        s.append(_t(x + bw / 2, y0 + 122, ", ".join(mem[:2]), 11, anchor="middle",
                    fill=MUTE))
        s.append(_t(x + bw / 2, y0 + 138, mem[2], 11, anchor="middle", fill=MUTE))

    # data path arrows through the chain
    s.append(_line(20, y0 + bh / 2, x0, y0 + bh / 2, DATA, 3))
    s.append(_t(18, y0 + bh / 2 - 10, "D", 18, weight="bold", fill=DATA))
    for i in range(len(chain) - 1):
        xr = centers[i][2]
        xl = centers[i + 1][1]
        s.append(_line(xr, y0 + bh / 2, xl, y0 + bh / 2, DATA, 3))
    xend = centers[-1][2]
    s.append(_line(xend, y0 + bh / 2, xend + 40, y0 + bh / 2, DATA, 3))
    s.append(_t(xend + 46, y0 + bh / 2 - 10, "Q", 18, weight="bold", fill=DATA))

    # stage-pair brackets (FF1..FF4) under each (M,S) pair
    yb = y0 + bh + 30
    for k in range(4):
        xl = centers[2 * k][1]
        xr = centers[2 * k + 1][2]
        s.append(_line(xl, yb, xr, yb, INK, 1.5, marker=False))
        s.append(_line(xl, yb - 8, xl, yb, INK, 1.5, marker=False))
        s.append(_line(xr, yb - 8, xr, yb, INK, 1.5, marker=False))
        s.append(_t((xl + xr) / 2, yb + 20, f"flip-flop {k+1}", 13,
                    anchor="middle", weight="bold"))

    # clock rail (amber) feeding all boxes
    yc = yb + 56
    s.append(_line(x0, yc, xend, yc, CLK, 2.5, marker=False))
    s.append(_t(20, yc + 5, "CP", 15, weight="bold", fill=CLK))
    for cx, _, _ in centers:
        s.append(_line(cx, yc, cx, y0 + bh, CLK, 1.2, dash="3,3", marker=False))

    # CD clear (red) feeding the slave latches (qf*, the _cx nodes)
    ycd = yc + 40
    s.append(_line(x0, ycd, xend, ycd, CLR, 2.5, marker=False))
    s.append(_t(20, ycd + 5, "CD", 15, weight="bold", fill=CLR))
    for i, (cx, _, _) in enumerate(centers):
        if chain[i][3] == "S":
            s.append(_line(cx, y0 + bh, cx, ycd, CLR, 1.2, dash="3,3", marker=False))
    s.append(_t(x0, ycd + 26,
               "CD (async clear) couples into the slave latches -- the '_cx' member "
               "node; this is why the CD min-pulse-width arc depends on the chain's "
               "prior state", 13, fill=CLR))

    # method note
    s.append(_t(40, H - 18,
               "found name-blind: a >=2-node strongly-connected loop in the "
               "gate+source -> drain influence graph = a bistable; roles ranked by "
               "influence-distance to Q (slave nearest, master farthest)",
               13, fill=MUTE))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# Figure S2 -- sensitization is derived PER ARC (Boolean difference)
# ---------------------------------------------------------------------------
def fig_s2():
    W, H = 1320, 660
    s = [_header(W, H)]
    s.append(_t(40, 46, "Stage 2 -- Sensitization is DERIVED, per arc "
                "(Boolean difference)", 24, weight="bold"))
    s.append(_t(40, 74, "hold side pins static, toggle the measured pin, require the "
                "captured node to follow it; then classify each side pin by toggling it",
                15, fill=MUTE))

    # left panel: the derivation (worked on the arc this run actually measured)
    s.append(_rect(40, 100, 600, 470, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 132, "How the bias is derived", 17, weight="bold"))
    s.append(_t(60, 158, "arc this run measured:  hold(CP, D)", 14, fill=DATA,
                weight="bold"))
    s.append(_t(60, 178, "(the engine's default in --netlist mode; sides = CD, SE, SI)",
                12, fill=MUTE))
    s.append(_t(60, 206, "test:  d(capture)/d(D) = 1  under a static side-pin hold,",
                13))
    s.append(_t(60, 224, "then toggle each side pin 0/1 and watch capture:", 13))

    # derivation table
    tx, ty, rw = 60, 250, 560
    cols = [tx + 12, tx + 150, tx + 430, tx + 510]
    s.append(_rect(tx, ty, rw, 34, "#eef2ff", PANEL_BD))
    for cx, lab in zip(cols, ["side pin", "toggling it changes capture?",
                              "role", "bias"]):
        s.append(_t(cx, ty + 22, lab, 12, weight="bold"))
    rows = [("CD", "yes -- a clear destroys the captured value", "required", "0", DATA),
            ("SE", "yes -- selects the D path vs the SI path", "required", "0", DATA),
            ("SI", "no  -- capture independent of it at SE=0", "masked", "1", CLK)]
    for i, (pin, eff, role, bias, col) in enumerate(rows):
        ry = ty + 34 + i * 40
        s.append(_rect(tx, ry, rw, 40, "white", PANEL_BD))
        s.append(_t(cols[0], ry + 25, pin, 14, weight="bold"))
        s.append(_t(cols[1], ry + 25, eff, 12, fill=INK))
        s.append(_t(cols[2], ry + 25, role, 12, weight="bold", fill=col))
        s.append(_t(cols[3], ry + 25, bias, 14, weight="bold", fill=col))
    s.append(_t(60, ty + 200, "=> D controls capture; SI masked  =>  ", 14,
                weight="bold"))
    s.append(_t(430, ty + 200, "P1 PASS", 15, weight="bold", fill=PASS))
    s.append(_t(60, ty + 226, "result:  biases {CD=0, SE=0, SI=1}", 13, fill=MUTE))

    # right panel: reading bias vs template.tcl define_arc (WHEN)
    s.append(_rect(670, 100, 610, 470, "#fffbeb", "#fde68a", rx=12))
    s.append(_t(690, 132, "Reading the bias vs template.tcl define_arc (WHEN)",
                16, weight="bold"))
    s.append(_t(690, 160, "the bias above is derived from PHYSICS, independent of "
                "define_arc;", 13))
    s.append(_t(690, 178, "the engine then cross-checks it against the arc's WHEN:",
                13))
    cases = [
        (DATA, "REQUIRED pin agrees with WHEN",
         "AGREE -- the arc as written sensitizes the path"),
        (CLR, "REQUIRED pin conflicts with WHEN",
         "DISAGREE (named) -- arc would mis-sensitize: investigate"),
        (MUTE, "REQUIRED pin missing from WHEN",
         "engine supplies it; WHEN is incomplete -- add it"),
        (CLK, "MASKED pin (any value in WHEN)",
         "non-critical hold; mismatch is harmless"),
    ]
    cy = 210
    for col, head, body in cases:
        s.append(f"<circle cx='702' cy='{cy-4}' r='5' fill='{col}'/>")
        s.append(_t(718, cy, head, 13, weight="bold", fill=col))
        s.append(_t(718, cy + 19, body, 12.5, fill=INK))
        cy += 52
    s.append(_rect(690, cy - 8, 570, 70, "white", "#fde68a", rx=8))
    s.append(_t(704, cy + 14, "actionable signal = the set-pin AGREE / DISAGREE.",
                13, weight="bold"))
    s.append(_t(704, cy + 34, "MASKED pins are don't-cares; do not chase them.",
                12.5, fill=MUTE))
    s.append(_t(704, cy + 52, "example:  arc.when {SE:0, SI:1} vs derived {SE=0} -> "
               "AGREE [set pins match]", 11.5, fill=MUTE))

    # bottom banner: per-arc warning
    s.append(_rect(40, 590, 1240, 50, "#fef2f2", "#fecaca", rx=10))
    s.append(_t(60, 612, "Sensitization is PER ARC.", 15, weight="bold", fill=CLR))
    s.append(_t(255, 612, "the CD min-pulse-width arc (rel=constr=CD, "
               "WHEN=CP,D,SE,SI) has a different side set and a different bias --",
               13.5))
    s.append(_t(60, 631, "specify the arc; do not read this hold(CP,D) bias as the "
               "MPW bias. (rel==constr MPW is a current engine gap.)", 13.5))
    s.append("</svg>")
    return "".join(s)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("s0_rmerge.svg", fig_s0), ("s1_storage.svg", fig_s1),
                     ("s2_sensitize.svg", fig_s2)):
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="ascii") as fh:
            fh.write(fn())
        print("wrote", path)


if __name__ == "__main__":
    main()
