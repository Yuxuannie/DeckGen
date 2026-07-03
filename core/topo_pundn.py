"""topo_pundn.py -- extract the pull-up / pull-down network (PUN/PDN) structure of
a CMOS cell from its DeviceGraph, as a series/parallel expression per driven net,
plus the set of conducting transistors under a given input state.

This is the data model behind the audit detail view's topology figure: it answers,
for a chosen side-pin state, *why* an arc sensitizes (a conducting path from the
related pin's network to the output exists) or is blocked (it does not).

Engine-side, stdlib only, ASCII. Reads .subckt-derived structure ONLY (Red Line
A) -- never template.tcl.

Series/parallel model (an `SP` node):
  ('dev', name, gate, kind)          one transistor (kind: 'pmos'|'nmos')
  ('series', [SP, ...])              source-drain chain
  ('parallel', [SP, ...])           same two endpoints
  ('flat', [('dev',...), ...])      non-series-parallel network -> bipartite fallback
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from engine import switchlevel
from engine.types import DeviceGraph

HIGH_RAILS = {"VDD", "VPP"}
LOW_RAILS = {"VSS", "VBB", "0"}
RAILS = HIGH_RAILS | LOW_RAILS


def _classify(graph: DeviceGraph):
    drains = {d.terminals["d"] for d in graph.devices}
    gates = {d.terminals["g"] for d in graph.devices if d.terminals["g"] not in RAILS}
    outputs = [p for p in graph.ports if p in drains and p not in RAILS]
    # a "driven net" is a logic node: the cell output, or an internal net that is
    # both produced (a drain) and consumed (a gate) -- i.e. a gate-output stage.
    driven = [n for n in graph.nets
              if n not in RAILS and (n in outputs or (n in drains and n in gates))]
    return outputs, sorted(set(driven)), gates


def _stage_devices(graph: DeviceGraph, driven: str, kind: str,
                   driven_set: Set[str]) -> List:
    """Devices of `kind` in the source/drain stack of `driven` -- BFS over channel
    (d/s) nets, stopping at rails and at OTHER driven nets so each stage is its own
    network."""
    devs = [d for d in graph.devices if d.kind == kind]
    comp = {driven}
    used = []
    changed = True
    while changed:
        changed = False
        for d in devs:
            if d in used:
                continue
            a, b = d.terminals["d"], d.terminals["s"]
            if a in comp or b in comp:
                used.append(d)
                for nn in (a, b):
                    if (nn not in comp and nn not in RAILS
                            and not (nn in driven_set and nn != driven)):
                        comp.add(nn)
                        changed = True
    return used


def _sp_reduce(devices: List, terminal_a: str, terminal_b: str):
    """Reduce a two-terminal multigraph (edges = transistors) between terminal_a
    (the driven net) and terminal_b (a rail-class label) to a series/parallel
    expression. Returns ('flat', [...]) if the network is not series-parallel."""
    # edges: list of [u, v, sp]; rails collapse to terminal_b's class label.
    def railnorm(n):
        if n in HIGH_RAILS:
            return "VDD"
        if n in LOW_RAILS:
            return "VSS"
        return n
    edges = []
    for d in devices:
        u, v = railnorm(d.terminals["d"]), railnorm(d.terminals["s"])
        edges.append([u, v, ("dev", d.name, d.terminals["g"], d.kind)])
    ta, tb = railnorm(terminal_a), railnorm(terminal_b)
    if not edges:
        return ("flat", [])

    def endpoints():
        from collections import defaultdict
        deg = defaultdict(list)
        for i, e in enumerate(edges):
            deg[e[0]].append(i)
            deg[e[1]].append(i)
        return deg

    changed = True
    while changed and len(edges) > 1:
        changed = False
        # parallel: two edges sharing the same unordered endpoint pair
        seen: Dict[frozenset, int] = {}
        for i, e in enumerate(edges):
            key = frozenset((e[0], e[1]))
            if len(key) == 1:           # self-loop: drop (shorted device)
                continue
            if key in seen:
                j = seen[key]
                a, b = edges[j], edges[i]
                merged = ("parallel", _flatten("parallel", [a[2], b[2]]))
                edges[j] = [a[0], a[1], merged]
                edges.pop(i)
                changed = True
                break
            seen[key] = i
        if changed:
            continue
        # series: an interior node (not a terminal) with exactly two edges
        deg = endpoints()
        for node, eidx in deg.items():
            if node in (ta, tb):
                continue
            if len(eidx) == 2:
                i, j = eidx
                a, b = edges[i], edges[j]
                outer_a = a[1] if a[0] == node else a[0]
                outer_b = b[1] if b[0] == node else b[0]
                merged = ("series", _flatten("series", [a[2], b[2]]))
                new = [outer_a, outer_b, merged]
                for k in sorted((i, j), reverse=True):
                    edges.pop(k)
                edges.append(new)
                changed = True
                break

    if len(edges) == 1 and frozenset((edges[0][0], edges[0][1])) == frozenset((ta, tb)):
        return edges[0][2]
    # not reducible to a single SP edge -> flat fallback (list every device)
    leaves = []
    for d in devices:
        leaves.append(("dev", d.name, d.terminals["g"], d.kind))
    return ("flat", leaves)


def _flatten(kind: str, children: List):
    out = []
    for c in children:
        if isinstance(c, tuple) and c and c[0] == kind:
            out.extend(c[1])
        else:
            out.append(c)
    return out


def pull_networks(graph: DeviceGraph) -> List[dict]:
    """Per driven net: its PUN (PMOS -> high rail) and PDN (NMOS -> low rail) as
    series/parallel expressions. Output stage first."""
    outputs, driven, _ = _classify(graph)
    driven_set = set(driven)
    # order: outputs last so they render at the bottom near the output; internal
    # stages above. (UI can decide; we sort outputs first here, stages after.)
    ordered = outputs + [n for n in driven if n not in outputs]
    nets = []
    for d in ordered:
        pun = _sp_reduce(_stage_devices(graph, d, "pmos", driven_set), d, "VDD")
        pdn = _sp_reduce(_stage_devices(graph, d, "nmos", driven_set), d, "VSS")
        nets.append({"net": d, "is_output": d in outputs, "pun": pun, "pdn": pdn})
    return nets


def conducting(graph: DeviceGraph, assignment: Dict[str, int]) -> Set[str]:
    """Names of transistors that conduct under `assignment` (gate-controlled)."""
    v = switchlevel.evaluate(graph, assignment)
    on = set()
    for d in graph.devices:
        g = v[d.terminals["g"]]
        if (d.kind == "nmos" and g == 1) or (d.kind == "pmos" and g == 0):
            on.add(d.name)
    return on


def sp_to_text(sp) -> str:
    """Readable string for an SP expression (tests + bipartite fallback labels)."""
    if not sp:
        return "(none)"
    tag = sp[0]
    if tag == "dev":
        return sp[2]                       # gate pin name
    if tag == "flat":
        return "flat[" + ", ".join(sp_to_text(c) for c in sp[1]) + "]"
    sep = " - " if tag == "series" else " || "
    inner = sep.join(sp_to_text(c) for c in sp[1])
    return "(" + inner + ")"


def device_names(sp) -> List[str]:
    """All device names referenced in an SP expression."""
    if not sp:
        return []
    if sp[0] == "dev":
        return [sp[1]]
    out = []
    for c in sp[1]:
        out.extend(device_names(c))
    return out


# ---------------------------------------------------------------------------
# SVG renderer -- the audit detail "signature": VDD top / VSS bottom like a real
# CMOS gate, series = vertical stack, parallel = side-by-side, PMOS rose / NMOS
# blue, ON transistors energized teal (the one bold thing), rel_pin gold-ringed.
# Pure string building, ASCII, no external assets (airgap-safe).
# ---------------------------------------------------------------------------
_DW, _DH = 72, 30          # device box
_VGAP, _HGAP = 20, 18      # series gap (vertical), parallel gap (horizontal)
_PAD = 18                  # panel padding
_RAILH = 26                # rail band height
_COL = {"pmos": "#b14a6f", "nmos": "#2f6fb0"}
_ON = "#0a9a9a"


def _measure(sp):
    if not sp or sp[0] == "dev":
        return (_DW, _DH)
    sizes = [_measure(c) for c in sp[1]]
    if sp[0] == "series":
        return (max(w for w, _ in sizes),
                sum(h for _, h in sizes) + _VGAP * (len(sizes) - 1))
    # parallel / flat: side by side
    return (sum(w for w, _ in sizes) + _HGAP * (len(sizes) - 1),
            max(h for _, h in sizes))


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _draw(sp, x, y, w, h, on, rel_pin, parts):
    """Place `sp` centered in box (x,y,w,h). Return center x for connectors."""
    cx = x + w / 2.0
    if not sp:
        return cx
    if sp[0] == "dev":
        _, name, gate, kind = sp
        bx, by = cx - _DW / 2.0, y + h / 2.0 - _DH / 2.0
        lit = name in on
        fill = _ON if lit else "#ffffff"
        stroke = _ON if lit else _COL.get(kind, "#888")
        sw = 2.4 if lit else 1.3
        ring = (' style="filter:drop-shadow(0 0 0 2px #b8860b)"'
                if gate == rel_pin else "")
        parts.append(
            '<rect class="dev%s" data-dev="%s" x="%.1f" y="%.1f" width="%d" '
            'height="%d" rx="5" fill="%s" stroke="%s" stroke-width="%.1f"%s/>'
            % (" on" if lit else "", _esc(name), bx, by, _DW, _DH, fill, stroke,
               sw, ring))
        tcol = "#ffffff" if lit else _COL.get(kind, "#333")
        gl = _esc(gate) + ("*" if gate == rel_pin else "")
        parts.append('<text x="%.1f" y="%.1f" text-anchor="middle" '
                     'font-family="ui-monospace,monospace" font-size="12" '
                     'font-weight="600" fill="%s">%s</text>'
                     % (cx, by + _DH / 2.0 + 4, tcol, gl))
        # connector stubs to the allocated top/bottom
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#b9bec6"/>'
                     % (cx, y, cx, by))
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#b9bec6"/>'
                     % (cx, by + _DH, cx, y + h))
        return cx
    sizes = [_measure(c) for c in sp[1]]
    if sp[0] == "series":
        cy = y
        prev_cx = None
        for c, (cw, ch) in zip(sp[1], sizes):
            ccx = _draw(c, x, cy, w, ch, on, rel_pin, parts)
            cy += ch + _VGAP
            prev_cx = ccx
        return cx
    # parallel / flat: lay children left to right; bus them top and bottom
    cxs = []
    cxleft = x
    for c, (cw, ch) in zip(sp[1], sizes):
        ccx = _draw(c, cxleft, y + h / 2.0 - ch / 2.0, cw, ch, on, rel_pin, parts)
        cxs.append(ccx)
        cxleft += cw + _HGAP
    if len(cxs) > 1:
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#b9bec6"/>'
                     % (min(cxs), y, max(cxs), y))                       # top bus
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#b9bec6"/>'
                     % (min(cxs), y + h, max(cxs), y + h))               # bottom bus
    return cx


def render_svg(blocks: List[dict], on=None, rel_pin: Optional[str] = None,
               output: Optional[str] = None) -> str:
    """One stacked panel per driven net: VDD rail, PUN, net line, PDN, VSS rail.
    ON devices (from `conducting`) light teal. Returns an SVG string."""
    on = set(on or ())
    _LEG = 30
    panels = []
    total_h = _PAD + _LEG
    maxw = 420
    for b in blocks:
        pw, ph = _measure(b["pun"])
        dw_, dh = _measure(b["pdn"])
        inner_w = max(pw, dw_, 240)
        maxw = max(maxw, inner_w + 2 * _PAD)
        panels.append((b, inner_w, ph, dh))
        total_h += 18 + 14 + 16 + ph + 28 + dh + 14 + 30
    W = maxw
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d" font-family="ui-monospace,monospace">'
             % (W, int(total_h), W, int(total_h))]
    # legend (makes the figure self-explanatory)
    lx = _PAD
    def _leg(x, sw_fill, sw_stroke, label, star=False):
        s = []
        if star:
            s.append('<text x="%.1f" y="%.1f" font-size="12" font-weight="700" '
                     'fill="#b8860b">*</text>' % (x, _PAD + 12))
            s.append('<text x="%.1f" y="%.1f" font-size="10" fill="#444">%s</text>'
                     % (x + 9, _PAD + 11, label))
            return "".join(s), x + 11 + len(label) * 6 + 16
        s.append('<rect x="%.1f" y="%.1f" width="12" height="12" rx="2" fill="%s" '
                 'stroke="%s" stroke-width="1.6"/>' % (x, _PAD + 2, sw_fill, sw_stroke))
        s.append('<text x="%.1f" y="%.1f" font-size="10" fill="#444">%s</text>'
                 % (x + 16, _PAD + 11, label))
        return "".join(s), x + 16 + len(label) * 6 + 16
    for fill, stroke, lab, star in [
            (_ON, _ON, "conducting", False),
            ("#ffffff", _COL["pmos"], "PMOS (pull-up)", False),
            ("#ffffff", _COL["nmos"], "NMOS (pull-down)", False),
            (None, None, "toggling pin", True)]:
        frag, lx = _leg(lx, fill, stroke, lab, star)
        parts.append(frag)
    y = _PAD + _LEG
    for b, inner_w, ph, dh in panels:
        x = (W - inner_w) / 2.0
        net = b["net"]
        tag = net + ("  (output)" if b["is_output"] else "  (internal node)")
        parts.append('<text x="%.1f" y="%.1f" font-size="12" font-weight="700" '
                     'fill="#5b2a86">%s</text>' % (x, y + 12, _esc(tag)))
        y += 18
        # VDD rail
        parts.append('<rect x="%.1f" y="%.1f" width="%d" height="14" rx="3" '
                     'fill="#f3eef8" stroke="#d9cde8"/>' % (x, y, inner_w))
        parts.append('<text x="%.1f" y="%.1f" font-size="10" fill="#7a5b9a">VDD</text>'
                     % (x + 6, y + 11))
        y += 14
        parts.append('<text x="%.1f" y="%.1f" font-size="9" fill="#9a86b2">'
                     'pull-up: conduct -&gt; drives %s HIGH</text>'
                     % (x + 2, y + 12, _esc(net)))
        y += 16
        _draw(b["pun"], x, y, inner_w, ph, on, rel_pin, parts)
        y += ph
        # net line
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                     'stroke="#5b2a86" stroke-width="2"/>' % (x, y + 14, x + inner_w, y + 14))
        nlab = _esc(net) + (" = output" if b["is_output"] else "")
        parts.append('<text x="%.1f" y="%.1f" font-size="11" font-weight="600" '
                     'fill="#5b2a86" text-anchor="middle">%s</text>'
                     % (x + inner_w / 2.0, y + 10, nlab))
        y += 28
        parts.append('<text x="%.1f" y="%.1f" font-size="9" fill="#7d8aa0">'
                     'pull-down: conduct -&gt; drives %s LOW</text>'
                     % (x + 2, y + 2, _esc(net)))
        _draw(b["pdn"], x, y, inner_w, dh, on, rel_pin, parts)
        y += dh
        # VSS rail
        parts.append('<rect x="%.1f" y="%.1f" width="%d" height="14" rx="3" '
                     'fill="#eef2f8" stroke="#cdd8e8"/>' % (x, y, inner_w))
        parts.append('<text x="%.1f" y="%.1f" font-size="10" fill="#5a6b8a">VSS</text>'
                     % (x + 6, y + 11))
        y += 14 + 30
    parts.append('</svg>')
    return "".join(parts)
