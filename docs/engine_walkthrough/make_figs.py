#!/usr/bin/env python3
"""
make_figs.py -- generate PPT-ready, SELF-CONTAINED SVG figures for the engine
walkthrough. Every figure carries its own method, numbers, and caveats so it can
be dropped into a slide with no surrounding text.

Dependency-free (hand-emitted SVG; PowerPoint/Keynote/Slides insert SVG natively
and keep it crisp). Re-run after editing:

    python3 docs/engine_walkthrough/make_figs.py

ASCII source only. The S1/S2 content uses the engine's ACTUAL output for
SDFSYNC4RPQSXGMZD1BWP130HPNPN3P48CPD (corner ssgnp_0p450v_m40c).
"""
import math
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs")

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
GREEN_BG = "#ecfdf5"
GREEN_BD = "#a7f3d0"
FONT = "font-family='DejaVu Sans, Arial, Helvetica, sans-serif'"


def _t(x, y, s, size=14, anchor="start", fill=INK, weight="normal", italic=False):
    st = " font-style='italic'" if italic else ""
    return (f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' "
            f"fill='{fill}' font-weight='{weight}' {FONT}{st}>{s}</text>")


def _rect(x, y, w, h, fill="none", stroke="none", rx=0, sw=1, dash=""):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'{d}/>")


def _line(x1, y1, x2, y2, color=INK, sw=2, dash="", marker=True):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    out = (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' "
           f"stroke-width='{sw}'{d}/>")
    if marker:                       # explicit arrowhead (raster-safe; no marker-end)
        dx, dy = x2 - x1, y2 - y1
        L = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / L, dy / L
        px, py = -uy, ux
        bx, by = x2 - ux * 10, y2 - uy * 10
        out += (f"<polygon points='{x2:.1f},{y2:.1f} {bx+px*5:.1f},{by+py*5:.1f} "
                f"{bx-px*5:.1f},{by-py*5:.1f}' fill='{color}'/>")
    return out


def _edge(x1, y1, x2, y2, color=INK, r=17, sw=2):
    """Directed edge between two node centers, trimmed by node radius r."""
    dx, dy = x2 - x1, y2 - y1
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    return _line(x1 + ux * r, y1 + uy * r, x2 - ux * r, y2 - uy * r, color, sw)


def _arc(x1, y1, x2, y2, color, bend, sw=2):
    """Curved directed edge (quadratic) with an explicit arrowhead."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + bend
    dx, dy = x2 - mx, y2 - my
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = x2 - ux * 10, y2 - uy * 10
    return (f"<path d='M{x1},{y1} Q{mx},{my} {x2},{y2}' fill='none' stroke='{color}' "
            f"stroke-width='{sw}'/>"
            f"<polygon points='{x2:.1f},{y2:.1f} {bx+px*5:.1f},{by+py*5:.1f} "
            f"{bx-px*5:.1f},{by-py*5:.1f}' fill='{color}'/>")


def _node(x, y, name, color=INK, r=17):
    return (f"<circle cx='{x}' cy='{y}' r='{r}' fill='white' stroke='{color}' "
            f"stroke-width='2'/>"
            + _t(x, y + 5, name, 13, anchor="middle", weight="bold", fill=color))


def _inv(x, y, color=INK, left=False):
    """Inverter triangle + bubble; apex right by default, left if left=True."""
    if left:
        tri = (f"<polygon points='{x},{y-14} {x},{y+14} {x-28},{y}' fill='white' "
               f"stroke='{color}' stroke-width='2'/>")
        bub = (f"<circle cx='{x-33}' cy='{y}' r='5' fill='white' stroke='{color}' "
               f"stroke-width='2'/>")
    else:
        tri = (f"<polygon points='{x},{y-14} {x},{y+14} {x+28},{y}' fill='white' "
               f"stroke='{color}' stroke-width='2'/>")
        bub = (f"<circle cx='{x+33}' cy='{y}' r='5' fill='white' stroke='{color}' "
               f"stroke-width='2'/>")
    return tri + bub


def _passg(x, y, gate, color=INK):
    """Pass-transistor box with its gate label."""
    return (_rect(x, y - 15, 52, 30, "white", color, rx=4, sw=2)
            + _t(x + 26, y + 4, "pass", 10.5, anchor="middle")
            + _t(x + 26, y - 21, "g=" + gate, 11, anchor="middle", fill=color))


def _table(x, y, headers, rows, colw, rowh=24):
    """Simple grid; returns (svg, bottom_y)."""
    out = []
    tw = sum(colw)
    out.append(_rect(x, y, tw, rowh, "#eef2ff", PANEL_BD))
    cx = x
    for h, w in zip(headers, colw):
        out.append(_t(cx + w / 2, y + 16, h, 11.5, anchor="middle", weight="bold"))
        cx += w
    for ri, row in enumerate(rows):
        ry = y + rowh + ri * rowh
        out.append(_rect(x, ry, tw, rowh, "white", PANEL_BD))
        cx = x
        for v, w in zip(row, colw):
            out.append(_t(cx + w / 2, ry + 16, v, 11.5, anchor="middle"))
            cx += w
    return "".join(out), y + rowh + len(rows) * rowh


def _step(x, y, n, lines, color=INK):
    out = [f"<circle cx='{x+11}' cy='{y-4}' r='11' fill='{color}'/>",
           _t(x + 11, y, str(n), 13, anchor="middle", fill="white", weight="bold")]
    for i, ln in enumerate(lines):
        out.append(_t(x + 30, y + i * 17, ln, 12.5, fill=INK))
    return "".join(out)


def _xcouple(cx, cy, color):
    return ("".join([
        f"<polygon points='{cx-16},{cy-7} {cx-2},{cy} {cx-16},{cy+7}' "
        f"fill='none' stroke='{color}' stroke-width='1.5'/>",
        f"<polygon points='{cx+16},{cy-7} {cx+2},{cy} {cx+16},{cy+7}' "
        f"fill='none' stroke='{color}' stroke-width='1.5'/>",
        f"<line x1='{cx-2}' y1='{cy}' x2='{cx+2}' y2='{cy}' stroke='{color}' "
        f"stroke-width='1.5'/>"]))


def _header(w, h):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' "
            f"viewBox='0 0 {w} {h}'>"
            f"<defs><marker id='arrow' markerWidth='10' markerHeight='10' "
            f"refX='8' refY='3' orient='auto'>"
            f"<path d='M0,0 L8,3 L0,6 Z' fill='{INK}'/></marker></defs>"
            f"<rect width='{w}' height='{h}' fill='white'/>")


# ---------------------------------------------------------------------------
# S0 -- de-parasitic R-merge
# ---------------------------------------------------------------------------
def fig_s0():
    W, H = 1340, 616
    s = [_header(W, H)]
    s.append(_t(40, 44, "Stage 0 -- recover the logical schematic from the LPE netlist",
                23, weight="bold"))
    s.append(_t(40, 70, "real cells ship as layout-extracted soup: device terminals are "
                "private nodes, the wiring is parasitic R, and C is to-ground/coupling",
                14, fill=MUTE))

    # left -- LPE soup
    s.append(_rect(40, 96, 360, 364, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 126, "LPE netlist (delivered)", 15, weight="bold"))
    soup = [("XMSA2#d", 80, 165), ("XMSA2#g", 200, 158), ("XMSA3#s", 300, 178),
            ("ml_a#1", 95, 235), ("ml_a#2", 220, 245), ("XMLA0#d", 320, 232),
            ("clkb#1", 85, 315), ("XCKA1#d", 210, 325), ("mq_a#3", 320, 312),
            ("seb#2", 150, 388)]
    for a, b in [(0, 1), (1, 2), (3, 4), (4, 5), (6, 7), (7, 8)]:
        x1, y1 = soup[a][1], soup[a][2]
        x2, y2 = soup[b][1], soup[b][2]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 9
        s.append(f"<polyline points='{x1},{y1} {mx-7},{my} {mx},{my-11} {mx+7},{my} "
                 f"{x2},{y2}' fill='none' stroke='{RAW}' stroke-width='1.4'/>")
    for name, x, y in soup:
        s.append(f"<circle cx='{x}' cy='{y}' r='4.5' fill='{RAW}'/>")
        s.append(_t(x + 8, y + 4, name, 10.5, fill=MUTE))
    s.append(_t(60, 432, "689 raw nodes  *  1033 parasitic R  *  C ignored for DC",
                12, fill=MUTE, italic=True))
    s.append(_t(60, 451, "(zig-zag = a parasitic resistor)", 11, fill=MUTE, italic=True))

    # middle -- the four operations
    s.append(_rect(430, 96, 470, 364, "#f1f5f9", PANEL_BD, rx=12))
    s.append(_t(450, 126, "the four operations", 15, weight="bold"))
    s.append(_step(450, 168, 1, ["classify lines:  X = transistor (d g s b),",
                                  "R = parasitic (a short),  C = ignored for DC"]))
    s.append(_step(450, 232, 2, ["R-merge:  union-find contract every R",
                                 "-> 689 raw nodes collapse to node clusters"]))
    s.append(_step(450, 296, 3, ["name each net:  port > rail > common base",
                                 "of base#k members (ml_a#1,#2 -> ml_a)"]))
    s.append(_step(450, 360, 4, ["self-check:  two signal ports in one",
                                 "cluster => BRIDGE(FAIL) topology error"]))
    s.append(_line(401, 278, 429, 278, INK, 2.5))
    s.append(_line(901, 278, 929, 278, INK, 2.5))

    # right -- recovered logical nets
    s.append(_rect(930, 96, 370, 364, DATA_BG, DATA, rx=12))
    s.append(_t(950, 126, "logical schematic (recovered)", 15, weight="bold", fill=DATA))
    for name, x, y in [("CP", 1010, 175), ("mq_a", 1150, 168), ("mq_b", 1255, 200),
                       ("ml_a", 1030, 258), ("Q", 1240, 290), ("seb", 1110, 350),
                       ("clkb", 1245, 372)]:
        s.append(f"<ellipse cx='{x}' cy='{y}' rx='33' ry='19' fill='white' "
                 f"stroke='{NET}' stroke-width='2'/>")
        s.append(_t(x, y + 5, name, 13.5, anchor="middle", weight="bold"))
    s.append(_t(950, 432, "92 logical nets = the real circuit nodes", 12, fill=DATA,
                italic=True))

    # callout -- names are cosmetic / name-blind proof
    s.append(_rect(40, 478, 1260, 60, GREEN_BG, GREEN_BD, rx=10))
    s.append(_t(58, 502, "Net names (step 3) are cosmetic.", 14, weight="bold",
                fill="#065f46"))
    s.append(_t(58, 524, "Downstream staging and bias are proven NAME-BLIND by the "
               "rename-invariance gate: obfuscate every internal name -> identical "
               "staging and identical P1 bias.", 13))

    # banner -- the numbers + health check
    s.append(_rect(40, 552, 1260, 48, PANEL, PANEL_BD, rx=10))
    s.append(_t(60, 581, "689 raw nodes  ->  92 logical nets  via 1033 R     |     "
               "164 transistors     |  ", 15, weight="bold"))
    s.append(_t(900, 581, "bridges = 0", 15, weight="bold", fill=PASS))
    s.append(_t(1005, 581, "(no mis-merge -- PASS)", 13, fill=PASS))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# S1 -- structural storage detection
# ---------------------------------------------------------------------------
def fig_s1():
    W, H = 1520, 508
    s = [_header(W, H)]
    s.append(_t(40, 44, "Stage 1 -- find the storage latches from STRUCTURE, not names",
                23, weight="bold"))
    s.append(_t(40, 70, "39 channel-connected components; 8 are bistable feedback loops "
                "(cross-coupled SCC) -- a 4-stage synchronizer, 2 latches per stage",
                14, fill=MUTE))

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
    bw, bh, gap, x0, y0 = 158, 142, 14, 64, 96
    centers = []
    for i, (role, prim, mem, half) in enumerate(chain):
        x = x0 + i * (bw + gap)
        centers.append((x + bw / 2, x, x + bw))
        fill = DATA_BG if half == "M" else "#fff7ed"
        bd = DATA if half == "M" else CLK
        s.append(_rect(x, y0, bw, bh, fill, bd, rx=10, sw=2))
        s.append(_t(x + bw / 2, y0 + 24, role, 14, anchor="middle", weight="bold", fill=bd))
        s.append(_t(x + bw / 2, y0 + 48, prim, 21, anchor="middle", weight="bold"))
        s.append(_xcouple(x + bw / 2, y0 + 70, bd))
        s.append(_t(x + bw / 2, y0 + 94,
                    f"{'master' if half=='M' else 'slave'}-latch", 11,
                    anchor="middle", fill=MUTE))
        s.append(_t(x + bw / 2, y0 + 114, ", ".join(mem[:2]), 10.5, anchor="middle",
                    fill=MUTE))
        s.append(_t(x + bw / 2, y0 + 130, mem[2], 10.5, anchor="middle", fill=MUTE))

    midy = y0 + bh / 2
    s.append(_line(22, midy, x0, midy, DATA, 3))
    s.append(_t(20, midy - 10, "D", 17, weight="bold", fill=DATA))
    for i in range(len(chain) - 1):
        s.append(_line(centers[i][2], midy, centers[i + 1][1], midy, DATA, 3))
    xend = centers[-1][2]
    s.append(_line(xend, midy, xend + 38, midy, DATA, 3))
    s.append(_t(xend + 44, midy - 10, "Q", 17, weight="bold", fill=DATA))

    # FF brackets
    yb = y0 + bh + 22
    for k in range(4):
        xl, xr = centers[2 * k][1], centers[2 * k + 1][2]
        s.append(_line(xl, yb, xr, yb, INK, 1.5, marker=False))
        s.append(_line(xl, yb - 7, xl, yb, INK, 1.5, marker=False))
        s.append(_line(xr, yb - 7, xr, yb, INK, 1.5, marker=False))
        s.append(_t((xl + xr) / 2, yb + 17, f"flip-flop {k+1}", 12.5,
                    anchor="middle", weight="bold"))

    # CD clear into the slave latches
    ycd = yb + 44
    s.append(_line(x0, ycd, xend, ycd, CLR, 2.2, marker=False))
    s.append(_t(20, ycd + 5, "CD", 14, weight="bold", fill=CLR))
    for i, (cx, _, _) in enumerate(centers):
        if chain[i][3] == "S":
            s.append(_line(cx, y0 + bh, cx, ycd, CLR, 1.1, dash="3,3", marker=False))
    s.append(_t(xend - 360, ycd + 22, "CD (async clear) couples into the slave latches "
               "-- the '_cx' member node", 12, fill=CLR))
    # CP rail
    yc = ycd + 40
    s.append(_line(x0, yc, xend, yc, CLK, 2.2, marker=False))
    s.append(_t(20, yc + 5, "CP", 14, weight="bold", fill=CLK))
    s.append(_t(x0 + 6, yc - 8, "CP gates all 8 latches", 12, fill=CLK))

    # method strip
    ym = yc + 40
    s.append(_t(40, ym, "method (name-blind):", 13, weight="bold"))
    steps = ["1  channel CCC -> 39 groups",
             "2  influence graph: gate, source -> drain",
             "3  SCC with >= 2 gate members -> 8 latches",
             "4  rank by influence-distance to Q"]
    for j, st in enumerate(steps):
        s.append(_t(40 + j * 360, ym + 22, st, 12.5, fill=INK))

    # labeling callout
    yk = ym + 40
    s.append(_rect(40, yk, 1440, 58, GREEN_BG, GREEN_BD, rx=10))
    s.append(_t(58, yk + 23, "Read it right:", 13.5, weight="bold", fill="#065f46"))
    s.append(_t(165, yk + 23, "8 latches = 4 flip-flops (master + slave each). "
               "'stage1..6' are distance-RANK labels, NOT six synchronizer stages.",
               13))
    s.append(_t(58, yk + 44, "master half carries an _a/_b pair; slave half carries an "
               "_a/_cx pair (the CD clear path). Pairing the 8 into FF1..FF4 is a "
               "planned refinement.", 12.5, fill=MUTE))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# S2 -- sensitization derived per arc
# ---------------------------------------------------------------------------
def fig_s2():
    W, H = 1320, 660
    s = [_header(W, H)]
    s.append(_t(40, 44, "Stage 2 -- Sensitization is DERIVED, per arc "
                "(Boolean difference)", 23, weight="bold"))
    s.append(_t(40, 70, "no reliance on the arc's stated condition: derive the bias "
                "from the transistors, then cross-check the arc definition against it",
                14, fill=MUTE))

    # left -- derivation
    s.append(_rect(40, 92, 600, 478, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 120, "How the bias is derived", 16, weight="bold"))
    s.append(_t(60, 142, "arc measured:  hold(CP, D)   (engine default; sides = "
               "CD, SE, SI)", 13, fill=DATA, weight="bold"))
    s.append(_step(60, 168, 1, ["break the latch feedback so the data path is clean"]))
    s.append(_step(60, 196, 2, ["find clock phase + side hold with d(capture)/d(D) = 1"]))
    s.append(_step(60, 224, 3, ["toggle each side pin -> changes capture ? required : "
                                "masked"]))

    tx, ty, rw = 60, 246, 560
    cols = [tx + 12, tx + 150, tx + 430, tx + 510]
    s.append(_rect(tx, ty, rw, 32, "#eef2ff", PANEL_BD))
    for cx, lab in zip(cols, ["side pin", "toggling it changes capture?", "role", "bias"]):
        s.append(_t(cx, ty + 21, lab, 12, weight="bold"))
    rows = [("CD", "yes -- a clear destroys the captured value", "required", "0", DATA),
            ("SE", "yes -- selects the D path vs the SI path", "required", "0", DATA),
            ("SI", "no  -- capture independent of it at SE=0", "masked", "1", CLK)]
    for i, (pin, eff, role, bias, col) in enumerate(rows):
        ry = ty + 32 + i * 38
        s.append(_rect(tx, ry, rw, 38, "white", PANEL_BD))
        s.append(_t(cols[0], ry + 24, pin, 14, weight="bold"))
        s.append(_t(cols[1], ry + 24, eff, 11.5))
        s.append(_t(cols[2], ry + 24, role, 12, weight="bold", fill=col))
        s.append(_t(cols[3], ry + 24, bias, 14, weight="bold", fill=col))
    s.append(_t(60, ty + 178, "=> D controls capture; SI masked  =>  ", 14, weight="bold"))
    s.append(_t(430, ty + 178, "P1 PASS", 15, weight="bold", fill=PASS))
    s.append(_t(60, ty + 202, "result:  biases {CD=0, SE=0, SI=1}", 13, fill=MUTE))

    # right -- read vs define_arc
    s.append(_rect(670, 92, 610, 478, "#fffbeb", "#fde68a", rx=12))
    s.append(_t(690, 120, "Reading the bias vs template.tcl define_arc (WHEN)",
                16, weight="bold"))
    s.append(_t(690, 148, "the bias is derived from PHYSICS, independent of define_arc;",
                13))
    s.append(_t(690, 166, "the engine then cross-checks it against the arc's WHEN:", 13))
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
    cy = 198
    for col, head, body in cases:
        s.append(f"<circle cx='702' cy='{cy-4}' r='5' fill='{col}'/>")
        s.append(_t(718, cy, head, 13, weight="bold", fill=col))
        s.append(_t(718, cy + 18, body, 12.5))
        cy += 50
    s.append(_rect(690, cy - 6, 570, 70, "white", "#fde68a", rx=8))
    s.append(_t(704, cy + 16, "actionable signal = the set-pin AGREE / DISAGREE.",
                13, weight="bold"))
    s.append(_t(704, cy + 35, "MASKED pins are don't-cares; do not chase them.",
                12.5, fill=MUTE))
    s.append(_t(704, cy + 53, "example:  arc.when {SE:0, SI:1} vs derived {SE=0} -> "
               "AGREE [set pins match]", 11.5, fill=MUTE))

    # banner -- per-arc warning
    s.append(_rect(40, 590, 1240, 50, "#fef2f2", "#fecaca", rx=10))
    s.append(_t(60, 612, "Sensitization is PER ARC.", 15, weight="bold", fill=CLR))
    s.append(_t(258, 612, "the CD min-pulse-width arc (rel=constr=CD, WHEN=CP,D,SE,SI) "
               "has a different side set and a different bias --", 13))
    s.append(_t(60, 631, "specify the arc; do not read this hold(CP,D) bias as the MPW "
               "bias.  (rel==constr MPW is a current engine gap.)", 13))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# S1 PROCESS -- how CCC + SCC actually find a storage node (worked micro-example)
# ---------------------------------------------------------------------------
def fig_s1_process():
    W, H = 1500, 600
    s = [_header(W, H)]
    s.append(_t(40, 44, "Stage 1 -- HOW storage is found: channel graph (CCC) + "
                "feedback loops (SCC)", 23, weight="bold"))
    s.append(_t(40, 70, "worked on one latch core; the identical procedure runs "
                "cell-wide and returns all 8 storage loops", 14, fill=MUTE))

    # ---- panel 1: transistor-level latch core ----
    s.append(_rect(40, 92, 540, 420, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 120, "1) the latch core (transistor level)", 15, weight="bold"))
    # pass-gate loads node A from Din under clock CK
    s.append(_node(120, 215, "Din"))
    s.append(_line(137, 215, 178, 215, INK, 2, marker=False))
    s.append(_passg(178, 215, "CK"))
    s.append(_line(230, 215, 283, 215, INK, 2, marker=False))
    # cross-coupled inverter pair: A --INV1--> B (top),  B --INV2--> A (bottom)
    s.append(_node(300, 215, "A", DATA))
    s.append(_node(470, 215, "B", DATA))
    s.append(_line(317, 215, 332, 215, INK, 2, marker=False))
    s.append(_inv(332, 215))
    s.append(_line(370, 215, 453, 215, INK, 2, marker=False))
    s.append(_line(470, 232, 470, 330, INK, 2, marker=False))      # B down
    s.append(_inv(458, 330, left=True))
    s.append(_line(458, 330, 470, 330, INK, 2, marker=False))      # B into INV2
    s.append(_line(420, 330, 300, 330, INK, 2, marker=False))      # INV2 out left
    s.append(_line(300, 330, 300, 232, INK, 2, marker=False))      # up to A
    s.append(_t(300, 372, "bit a", 11, anchor="middle", fill=MUTE))
    s.append(_t(470, 372, "bit b", 11, anchor="middle", fill=MUTE))
    s.append(_t(60, 432, "two inverters back-to-back = a feedback loop;", 12.5))
    s.append(_t(60, 450, "the pass-gate loads it under clock CK", 12.5))
    s.append(_t(60, 480, "channel graph (source-drain) partitions nets -> 39 CCCs;",
                12, fill=MUTE))
    s.append(_t(60, 497, "rails and primary inputs are boundaries", 12, fill=MUTE))

    # ---- panel 2: influence digraph + the cycle ----
    s.append(_rect(600, 92, 440, 420, "#f1f5f9", PANEL_BD, rx=12))
    s.append(_t(620, 120, "2) influence digraph", 15, weight="bold"))
    s.append(_t(620, 142, "one edge per transistor:  gate -> drain,  source -> drain",
                12.5, fill=MUTE))
    dn = (690, 215)
    ck = (690, 360)
    A = (860, 290)
    B = (985, 290)
    s.append(_edge(dn[0], dn[1], A[0], A[1], INK))
    s.append(_edge(ck[0], ck[1], A[0], A[1], INK))
    # the red feedback cycle A <-> B
    s.append(_arc(877, 283, 968, 283, CLR, -34))     # A -> B (above)
    s.append(_arc(968, 297, 877, 297, CLR, 34))      # B -> A (below)
    s.append(_node(dn[0], dn[1], "Din", MUTE))
    s.append(_node(ck[0], ck[1], "CK", MUTE))
    s.append(_node(A[0], A[1], "A", DATA))
    s.append(_node(B[0], B[1], "B", DATA))
    s.append(_t(620, 415, "red cycle:  A -> B -> A", 13, weight="bold", fill=CLR))
    s.append(_t(620, 435, "(cross-coupled feedback = a bistable)", 12, fill=MUTE))
    s.append(_t(620, 470, "an inverter's input net (a gate) drives its", 12, fill=MUTE))
    s.append(_t(620, 487, "output net (a drain) -> the two arrows close a loop",
                12, fill=MUTE))

    # ---- panel 3: SCC + gate filter -> storage ----
    s.append(_rect(1060, 92, 400, 420, DATA_BG, DATA, rx=12))
    s.append(_t(1080, 120, "3) Tarjan SCC + gate filter", 15, weight="bold", fill=DATA))
    bullets = [
        "strongly-connected component found:",
        "   {A, B},  size 2",
        "keep only loops with >= 2 nets that are",
        "   themselves transistor GATES",
        "A gates INV1, B gates INV2  -> both kept",
        "series-stack drain-only nodes -> dropped",
    ]
    for i, b in enumerate(bullets):
        s.append(_t(1080, 152 + i * 26, b, 12.5))
    s.append(_rect(1080, 322, 360, 96, "white", DATA, rx=8))
    s.append(_t(1100, 352, "=> a BISTABLE storage latch", 15, weight="bold", fill=PASS))
    s.append(_t(1100, 378, "identified from STRUCTURE alone,", 12.5))
    s.append(_t(1100, 397, "real nets here: mq_a / mq_b", 12.5, fill=MUTE))
    s.append(_t(1080, 470, "(roles master/slave then come from", 12, fill=MUTE))
    s.append(_t(1080, 487, "influence-distance to the output Q)", 12, fill=MUTE))

    # bottom strip
    s.append(_rect(40, 528, 1420, 50, GREEN_BG, GREEN_BD, rx=10))
    s.append(_t(58, 558, "Run over the whole cell:", 13.5, weight="bold", fill="#065f46"))
    s.append(_t(245, 558, "8 such feedback loops found = the 8 latches; ranked by "
               "distance to Q they form the master..slave chain (next figure).", 13))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# S2 PROCESS -- the Boolean-difference derivation, step by step
# ---------------------------------------------------------------------------
def fig_s2_booldiff():
    W, H = 1360, 620
    s = [_header(W, H)]
    s.append(_t(40, 44, "Stage 2 -- HOW the bias is derived: switch-level Boolean "
                "difference", 23, weight="bold"))
    s.append(_t(40, 70, "evaluate the captured node M through the transistors as inputs "
                "toggle -- stdlib, no SAT solver", 14, fill=MUTE))

    # ---- panel L: the switch-level data path (feedback cut) ----
    s.append(_rect(40, 92, 470, 496, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 120, "the data path (latch feedback CUT)", 15, weight="bold"))
    s.append(_node(105, 210, "D"))
    s.append(_node(105, 360, "SI"))
    s.append(_passg(190, 210, "SEB"))
    s.append(_passg(190, 360, "SE"))
    s.append(_line(122, 210, 190, 210, INK, 2, marker=False))
    s.append(_line(122, 360, 190, 360, INK, 2, marker=False))
    s.append(_line(242, 210, 330, 268, INK, 2, marker=False))   # mux to M
    s.append(_line(242, 360, 330, 292, INK, 2, marker=False))
    s.append(_node(350, 280, "M", DATA, 20))
    s.append(_t(350, 318, "captured (master) node", 11, anchor="middle", fill=MUTE))
    # latch with a cut
    s.append(_line(370, 280, 410, 280, INK, 2, marker=False))
    s.append(_inv(410, 280))
    s.append(_line(448, 280, 448, 230, INK, 2, dash="4,3", marker=False))
    s.append(_line(448, 230, 350, 230, CLR, 2, dash="4,3", marker=False))
    s.append(_line(350, 230, 350, 260, CLR, 2, dash="4,3", marker=False))
    s.append(_t(360, 222, "feedback CUT", 11, fill=CLR))
    s.append(_t(60, 372, "SE selects D vs SI;  CP gates transparency;", 12.5))
    s.append(_t(60, 390, "the storage feedback is cut so M is a clean", 12.5))
    s.append(_t(60, 408, "function of the inputs -- then we evaluate it.", 12.5))
    s.append(_t(60, 446, "Boolean difference d(M)/d(x) = does toggling", 12, fill=MUTE))
    s.append(_t(60, 463, "input x change the evaluated node M?", 12, fill=MUTE))

    # ---- panel R: the derivation (three evaluated tests) ----
    s.append(_rect(540, 92, 780, 496, "#f1f5f9", PANEL_BD, rx=12))
    s.append(_t(560, 120, "the derivation = evaluate M as inputs toggle", 15,
                weight="bold"))

    s.append(_t(560, 152, "(1) does M follow D?   [CP transparent, SE=0]", 13,
                weight="bold"))
    t1, y1 = _table(560, 162, ["D", "M"], [["0", "0"], ["1", "1"]], [70, 70])
    s.append(t1)
    s.append(_t(710, 186, "M follows D  =>  ", 13))
    s.append(_t(835, 186, "D CONTROLS capture", 13, weight="bold", fill=DATA))

    s.append(_t(560, y1 + 26, "(2) toggle side pin SI -- does M change?", 13,
                weight="bold"))
    t2, y2 = _table(560, y1 + 36, ["D", "SI", "M"],
                    [["0", "0", "0"], ["0", "1", "0"], ["1", "0", "1"],
                     ["1", "1", "1"]], [60, 60, 60])
    s.append(t2)
    s.append(_t(750, y1 + 70, "M independent of SI  =>", 13))
    s.append(_t(750, y1 + 90, "SI MASKED  (hold 1, non-critical)", 13, weight="bold",
                fill=CLK))

    s.append(_t(560, y2 + 26, "(3) toggle side pin SE -- does M change?", 13,
                weight="bold"))
    t3, y3 = _table(560, y2 + 36, ["SE", "M"], [["0", "M = D"], ["1", "M = SI"]],
                    [70, 110])
    s.append(t3)
    s.append(_t(760, y2 + 62, "M changes  =>", 13))
    s.append(_t(760, y2 + 82, "SE REQUIRED;  SE=0 selects D", 13, weight="bold",
                fill=DATA))

    s.append(_t(560, y3 + 28, "(4) clear:  CD=1 forces M cleared  =>  CD REQUIRED = 0",
                13, weight="bold"))
    s.append(_rect(560, y3 + 40, 740, 40, "white", PASS, rx=8))
    s.append(_t(576, y3 + 65, "=> biases {CD=0, SE=0, SI=1}", 15, weight="bold"))
    s.append(_t(900, y3 + 65, "P1 PASS", 15, weight="bold", fill=PASS))
    s.append("</svg>")
    return "".join(s)


def _mos(x, y, color=INK, hl=False):
    """Tiny MOS glyph: vertical channel (source bottom / drain top), gate to left."""
    cc = PASS if hl else color
    return "".join([
        f"<line x1='{x-5}' y1='{y-16}' x2='{x-5}' y2='{y+16}' stroke='{color}' stroke-width='3'/>",
        f"<line x1='{x-24}' y1='{y}' x2='{x-5}' y2='{y}' stroke='{color}' stroke-width='2'/>",
        f"<line x1='{x+3}' y1='{y-16}' x2='{x+3}' y2='{y+16}' stroke='{cc}' stroke-width='3'/>",
        f"<line x1='{x+3}' y1='{y-16}' x2='{x+3}' y2='{y-32}' stroke='{cc}' stroke-width='2'/>",
        f"<line x1='{x+3}' y1='{y+16}' x2='{x+3}' y2='{y+32}' stroke='{cc}' stroke-width='2'/>",
    ])


# ---------------------------------------------------------------------------
# UNION-FIND -- how raw nodes merge into logical nets (S0 detail)
# ---------------------------------------------------------------------------
def fig_union_find():
    W, H = 1400, 600
    s = [_header(W, H)]
    s.append(_t(40, 44, "Union-find: how raw nodes merge into logical nets (S0)",
                23, weight="bold"))
    s.append(_t(40, 70, "a disjoint-set structure with two ops -- find(x) = which "
                "group is x in;  union(a, b) = merge two groups", 14, fill=MUTE))

    # panel 1 -- singletons
    s.append(_rect(40, 92, 380, 430, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 120, "1) start: each raw node = its own set", 14.5, weight="bold"))
    raws = ["ml_a#1", "XMSA4#d", "XMSA5#d", "XMLA0#g", "XMLA1#g", "XMFA1#d"]
    for i, r in enumerate(raws):
        cx, cy = 110 + (i % 2) * 180, 180 + (i // 2) * 90
        s.append(f"<circle cx='{cx}' cy='{cy}' r='28' fill='white' stroke='{RAW}' "
                 f"stroke-width='2'/>")
        s.append(_t(cx, cy + 4, r, 10.5, anchor="middle"))
    s.append(_t(60, 500, "689 singletons;  find(x) = x", 12.5, fill=MUTE))

    # panel 2 -- process resistors, build the tree
    s.append(_rect(440, 92, 470, 430, "#f1f5f9", PANEL_BD, rx=12))
    s.append(_t(460, 120, "2) for each resistor R(a, b):  union(a, b)", 14.5,
                weight="bold"))
    rlines = ["R41:  ml_a#1  --  XMSA4#d", "R42:  XMSA4#d  --  XMSA5#d",
              "R43:  XMSA5#d  --  XMLA0#g", "R44:  XMLA0#g  --  XMLA1#g",
              "R47:  XMFA1#d  --  ml_a#1"]
    for i, ln in enumerate(rlines):
        s.append(_t(462, 150 + i * 19, ln, 12, fill=MUTE))
    # the resulting tree: root (smallest name) with members pointing up
    root = (675, 300)
    kids = [(520, 400), (600, 430), (680, 410), (760, 430), (840, 400)]
    s.append(_node(root[0], root[1], "root", DATA, 26))
    for kx, ky in kids:
        s.append(_edge(kx, ky, root[0], root[1], INK, 24))
        s.append(f"<circle cx='{kx}' cy='{ky}' r='20' fill='white' stroke='{INK}' "
                 f"stroke-width='1.5'/>")
    s.append(_t(460, 470, "child -> parent edges; root = the set's representative",
                12, fill=MUTE))
    s.append(_t(460, 490, "(deterministic: the smaller raw-node name becomes root)",
                12, fill=MUTE))
    s.append(_t(460, 510, "find(x): walk to root, then re-point x straight at it "
               "(path compression)", 12, fill=MUTE))

    # panel 3 -- result = one logical net
    s.append(_rect(930, 92, 430, 430, DATA_BG, DATA, rx=12))
    s.append(_t(950, 120, "3) one set = one logical net", 14.5, weight="bold",
                fill=DATA))
    rc = (1145, 250)
    s.append(_node(rc[0], rc[1], "rep", DATA, 28))
    for ang in range(0, 360, 60):
        rx = rc[0] + int(120 * math.cos(math.radians(ang)))
        ry = rc[1] + int(95 * math.sin(math.radians(ang)))
        s.append(_edge(rx, ry, rc[0], rc[1], "#93c5fd", 28))
        s.append(f"<circle cx='{rx}' cy='{ry}' r='16' fill='white' stroke='{DATA}' "
                 f"stroke-width='1.5'/>")
    s.append(_t(rc[0], 410, "this set = logical net  ml_a", 14, anchor="middle",
                weight="bold"))
    s.append(_t(950, 445, "after path compression every member points straight at the",
                12, fill=MUTE))
    s.append(_t(950, 463, "representative -> find is near O(1)", 12, fill=MUTE))
    s.append(_t(950, 488, "the NAME 'ml_a' = the most common base#k among members",
                12, fill=MUTE))
    s.append(_t(950, 506, "(cosmetic; the representative is just an internal id)",
                12, fill=MUTE))

    # banner
    s.append(_rect(40, 538, 1320, 48, GREEN_BG, GREEN_BD, rx=10))
    s.append(_t(58, 567, "689 raw nodes  --[1033 unions over resistors]->  92 logical "
               "nets.", 14, weight="bold", fill="#065f46"))
    s.append(_t(720, 567, "The SAME union-find runs again in S1 over transistor "
               "channels -> 39 CCCs.", 13))
    s.append("</svg>")
    return "".join(s)


# ---------------------------------------------------------------------------
# CCC -- channel-connected components from the 92 logical nets (S1)
# ---------------------------------------------------------------------------
def fig_ccc():
    W, H = 1440, 620
    s = [_header(W, H)]
    s.append(_t(40, 44, "Channel-Connected Components (CCC): group the 92 nets by "
                "transistor channels", 22, weight="bold"))
    s.append(_t(40, 70, "input = S0's output: 92 logical nets (82 internal + 10 "
                "ports/rails). A transistor's source-drain channel links two nets; "
                "the gate does not.", 13.5, fill=MUTE))

    # panel 1 -- the linking rule
    s.append(_rect(40, 92, 410, 446, PANEL, PANEL_BD, rx=12))
    s.append(_t(60, 120, "1) the linking rule", 14.5, weight="bold"))
    s.append(_mos(180, 220, INK, hl=True))
    s.append(_t(188, 180, "d (drain)", 11, fill=PASS))
    s.append(_t(188, 270, "s (source)", 11, fill=PASS))
    s.append(_t(110, 224, "g", 11, anchor="end", fill=MUTE))
    s.append(_t(60, 320, "edge = source-drain channel (green)", 12.5, fill=PASS))
    s.append(_t(60, 340, "between the drain net and the source net", 12, fill=MUTE))
    s.append(_t(60, 372, "gate is EXCLUDED -- it controls, it is not", 12.5))
    s.append(_t(60, 390, "part of the conduction path here", 12, fill=MUTE))
    s.append(_t(60, 424, "BOUNDARIES (grouping stops):", 12.5, weight="bold", fill=CLR))
    s.append(_t(60, 444, "rails VDD/VSS/VPP/VBB and primary", 12))
    s.append(_t(60, 462, "inputs CD/CP/D/SE/SI -> only the 82", 12))
    s.append(_t(60, 480, "internal nets get grouped", 12))

    # panel 2 -- channel graph + union-find -> components
    s.append(_rect(470, 92, 560, 446, "#f1f5f9", PANEL_BD, rx=12))
    s.append(_t(490, 120, "2) channel graph -> union-find -> components", 14.5,
                weight="bold"))
    # three illustrative components, colored
    comp1 = {"mq": (640, 200), "mq_a": (760, 175), "mq_b": (780, 250),
             "mq_x": (660, 270)}
    e1 = [("mq", "mq_a"), ("mq_a", "mq_b"), ("mq_b", "mq_x"), ("mq_x", "mq")]
    comp2 = {"mi": (640, 360), "seb": (760, 360)}
    e2 = [("mi", "seb")]
    comp3 = {"clkb": (910, 200), "ckx": (980, 260)}
    e3 = [("clkb", "ckx")]
    for net, edges, col in [(comp1, e1, DATA), (comp2, e2, NET), (comp3, e3, CLK)]:
        for a, b in edges:
            ax, ay = net[a]; bx, by = net[b]
            s.append(_line(ax, ay, bx, by, col, 2, marker=False))
        for nm, (nx, ny) in net.items():
            s.append(f"<circle cx='{nx}' cy='{ny}' r='20' fill='white' stroke='{col}' "
                     f"stroke-width='2'/>")
            s.append(_t(nx, ny + 4, nm, 10, anchor="middle"))
    # rails as boundary boxes that edges touch but do not cross
    s.append(_rect(890, 350, 64, 30, "#e5e7eb", MUTE, rx=4))
    s.append(_t(922, 370, "VSS", 11, anchor="middle", fill=MUTE))
    s.append(_t(922, 405, "(rail = boundary;", 10.5, anchor="middle", fill=MUTE))
    s.append(_t(922, 420, "stops the group)", 10.5, anchor="middle", fill=MUTE))
    s.append(_t(490, 470, "the SAME union-find as S0, now over source-drain edges",
                12.5, fill=MUTE))
    s.append(_t(490, 492, "82 internal nets  ->  ", 13))
    s.append(_t(620, 492, "39 channel-connected components", 13, weight="bold",
                fill=DATA))
    s.append(_t(490, 514, "(each color above = one CCC)", 12, fill=MUTE))

    # panel 3 -- what a CCC is
    s.append(_rect(1050, 92, 350, 446, DATA_BG, DATA, rx=12))
    s.append(_t(1070, 120, "3) what one CCC is", 14.5, weight="bold", fill=DATA))
    c = {"mq": (1170, 200), "mq_a": (1270, 185), "mq_b": (1285, 260),
         "mq_x": (1185, 270)}
    for a, b in [("mq", "mq_a"), ("mq_a", "mq_b"), ("mq_b", "mq_x"), ("mq_x", "mq")]:
        ax, ay = c[a]; bx, by = c[b]
        s.append(_line(ax, ay, bx, by, DATA, 2, marker=False))
    for nm, (nx, ny) in c.items():
        s.append(f"<circle cx='{nx}' cy='{ny}' r='21' fill='white' stroke='{DATA}' "
                 f"stroke-width='2'/>")
        s.append(_t(nx, ny + 4, nm, 10.5, anchor="middle"))
    s.append(_t(1070, 330, "a CCC = nets that share charge", 12.5))
    s.append(_t(1070, 348, "through channels (a switch-level", 12, fill=MUTE))
    s.append(_t(1070, 366, "node group)", 12, fill=MUTE))
    s.append(_t(1070, 398, "39 CCCs total;  8 of them contain", 12.5, weight="bold"))
    s.append(_t(1070, 416, "a cross-coupled feedback loop", 12.5, weight="bold"))
    s.append(_t(1070, 434, "= the 8 latches", 12.5, weight="bold", fill=PASS))
    s.append(_t(1070, 462, "(the loop is found by SCC inside", 12, fill=MUTE))
    s.append(_t(1070, 480, "the CCC -- the S1 process figure)", 12, fill=MUTE))

    # banner -- CCC vs SCC
    s.append(_rect(40, 554, 1360, 48, GREEN_BG, GREEN_BD, rx=10))
    s.append(_t(58, 583, "CCC (undirected, source-drain) = the partition.", 13.5,
               weight="bold", fill="#065f46"))
    s.append(_t(530, 583, "SCC (directed influence graph) = finds the bistable loop "
               "inside a CCC.   39 groups, 8 with storage.", 13))
    s.append("</svg>")
    return "".join(s)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("s0_rmerge.svg", fig_s0),
                     ("union_find.svg", fig_union_find), ("ccc.svg", fig_ccc),
                     ("s1_process.svg", fig_s1_process), ("s1_storage.svg", fig_s1),
                     ("s2_booldiff.svg", fig_s2_booldiff), ("s2_sensitize.svg", fig_s2)):
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="ascii") as fh:
            fh.write(fn())
        print("wrote", path)


if __name__ == "__main__":
    main()
