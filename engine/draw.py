"""
engine/draw.py -- graphical topology/CCC views (Graphviz .dot and self-contained SVG).

Both are dependency-free to GENERATE (plain text). Viewing:
  - .dot: `dot -Tpng cell.dot -o cell.png` (if graphviz is installed) -- best layout.
  - .svg: open directly in a browser (Firefox) -- zero dependencies.

The drawing collapses anonymous series nodes (tristate-stack internals) so edges
run net-to-net, colors nodes by CCC, and highlights the sensitized path:
  green = measured data path, red dashed = masked scan input, blue = clock.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from engine.types import Arc, CCCResult, DeviceGraph, SensitizationResult

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}
PALETTE = ["#cde7ff", "#d6f5d6", "#ffe6cc", "#f0d6ff", "#fff5cc",
           "#d6f0f0", "#ffd6e0", "#e0e0e0"]


def _signal(n: str) -> bool:
    return not n.startswith("net_") and n not in RAILS


def _collapse(graph: DeviceGraph) -> Set[Tuple[str, str]]:
    """Influence edges (gate/source -> drain), collapsed through series nodes so
    both endpoints are named signal nets."""
    infl: Dict[str, Set[str]] = {}
    for d in graph.devices:
        dr = d.terminals["d"]
        if dr in RAILS:
            continue
        for s in (d.terminals["g"], d.terminals["s"]):
            if s not in RAILS:
                infl.setdefault(s, set()).add(dr)
    edges: Set[Tuple[str, str]] = set()
    for a in infl:
        if not _signal(a):
            continue
        seen, stack = set(), list(infl[a])
        while stack:
            t = stack.pop()
            if t in seen:
                continue
            seen.add(t)
            if _signal(t):
                if t != a:
                    edges.add((a, t))
            else:
                stack.extend(infl.get(t, ()))
    return edges


def _classify(graph: DeviceGraph, ccc: CCCResult, arc: Optional[Arc]):
    driven = {d.terminals["d"] for d in graph.devices}
    inputs = {p for p in graph.ports if p not in RAILS and p not in driven}
    core = {sn.net for sn in ccc.state_nodes}
    role = {sn.net: sn.role for sn in ccc.state_nodes}
    clk = arc.rel_pin if arc else None
    constr = arc.constr_pin if arc else None

    gate_adj: Dict[str, Set[str]] = {}
    for d in graph.devices:
        if d.terminals["d"] not in RAILS:
            gate_adj.setdefault(d.terminals["g"], set()).add(d.terminals["d"])

    def reach(start):
        seen, stack = set(), [start]
        while stack:
            for w in gate_adj.get(stack.pop(), ()):
                if w not in seen and w not in core and w not in inputs and w not in RAILS:
                    seen.add(w)
                    stack.append(w)
        return seen

    clock_nets = reach(clk) | ({clk} if clk else set())
    ccc_idx = {}
    for i, comp in enumerate(ccc.components):
        for n in comp:
            ccc_idx[n] = i
    return inputs, core, role, clk, constr, clock_nets, ccc_idx


def _edge_color(src, constr, clock_nets, core):
    if src in clock_nets:
        return "blue"
    if src == "SI":
        return "red"
    if src == constr or src in core:
        return "green"
    return "gray"


def render_dot(graph, ccc, sens=None, arc=None) -> str:
    inputs, core, role, clk, constr, clock_nets, ccc_idx = _classify(graph, ccc, arc)
    edges = _collapse(graph)
    title = f"{graph.cell}"
    if arc:
        title += f"  {arc.label()}"
    if sens:
        title += f"  P1={'PASS' if sens.proven else 'FAIL'}"

    L = ["digraph topo {", "  rankdir=LR;", '  labelloc="t";',
         f'  label="{title}";', "  node [shape=box, style=filled, fontname=monospace];"]
    masters = [n for n, r in role.items() if r == "master"]
    slaves = [n for n, r in role.items() if r == "slave" or r == "storage"]
    if masters:
        L.append('  subgraph cluster_m { label="master latch"; color="#888"; '
                 + " ".join(f'"{n}"' for n in masters) + " }")
    if slaves:
        L.append('  subgraph cluster_s { label="slave latch"; color="#888"; '
                 + " ".join(f'"{n}"' for n in slaves) + " }")
    for n in sorted(n for n in graph.nets if _signal(n)):
        fill = PALETTE[ccc_idx[n] % len(PALETTE)] if n in ccc_idx else "white"
        shape = "ellipse" if n in inputs else "box"
        L.append(f'  "{n}" [fillcolor="{fill}", shape={shape}];')
    for a, b in sorted(edges):
        c = _edge_color(a, constr, clock_nets, core)
        style = ',style=dashed' if c == "red" else ''
        L.append(f'  "{a}" -> "{b}" [color={c}{style}];')
    L.append("}")
    return "\n".join(L) + "\n"


def render_svg(graph, ccc, sens=None, arc=None) -> str:
    inputs, core, role, clk, constr, clock_nets, ccc_idx = _classify(graph, ccc, arc)
    edges = _collapse(graph)

    # assign each signal net to a functional column
    def col_of(n):
        if n in inputs:
            return 0
        if role.get(n) == "master":
            return 2
        if role.get(n) in ("slave", "storage"):
            return 3
        if n in (set(graph.ports) - RAILS - inputs):
            return 4                       # outputs
        return 1                           # buffers / mux

    cols: Dict[int, List[str]] = {}
    for n in sorted(n for n in graph.nets if _signal(n)):
        cols.setdefault(col_of(n), []).append(n)

    BW, BH, CW, RH, PAD = 130, 28, 200, 46, 30
    pos: Dict[str, Tuple[int, int]] = {}
    for c, nets in cols.items():
        for r, n in enumerate(nets):
            pos[n] = (PAD + c * CW, PAD + 40 + r * RH)
    width = PAD + (max(cols) + 1) * CW
    height = PAD + 60 + max((len(v) for v in cols.values()), default=1) * RH

    S = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
         f'font-family="monospace" font-size="12">']
    S.append(f'<text x="10" y="20" font-size="14">{graph.cell}  '
             f'{arc.label() if arc else ""}  '
             f'{"P1=" + ("PASS" if sens and sens.proven else "") if sens else ""}</text>')
    # edges first (under boxes)
    for a, b in sorted(edges):
        if a not in pos or b not in pos:
            continue
        x1, y1 = pos[a][0] + BW, pos[a][1] + BH // 2
        x2, y2 = pos[b][0], pos[b][1] + BH // 2
        c = _edge_color(a, constr, clock_nets, core)
        dash = 'stroke-dasharray="5,3"' if c == "red" else ""
        S.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" '
                 f'stroke-width="1.5" {dash} marker-end="url(#a)"/>')
    # boxes
    for n, (x, y) in pos.items():
        fill = PALETTE[ccc_idx[n] % len(PALETTE)] if n in ccc_idx else "#ffffff"
        rx = 14 if n in inputs else 3
        S.append(f'<rect x="{x}" y="{y}" width="{BW}" height="{BH}" rx="{rx}" '
                 f'fill="{fill}" stroke="#333"/>')
        S.append(f'<text x="{x + BW // 2}" y="{y + 18}" text-anchor="middle">{n}</text>')
    S.append('<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="3" '
             'orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#333"/></marker></defs>')
    S.append("</svg>")
    return "\n".join(S) + "\n"
