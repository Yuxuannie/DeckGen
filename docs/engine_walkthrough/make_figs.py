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
    m = " marker-end='url(#arrow)'" if marker else ""
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' "
            f"stroke-width='{sw}'{d}{m}/>")


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
