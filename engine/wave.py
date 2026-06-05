"""
engine/wave.py -- parse HSPICE transient output and draw it as an SVG waveform.

Goal: see the P2 drive-and-settle transient in a WINDOW via `eog wave.svg`
(eog renders SVG; no Firefox, no gnuplot, no pip). Two pieces:

  parse_csdf(text)  -- read an HSPICE CSDF ascii output (`.option csdf=1`):
        #N 'v(cp)' 'v(d)' ...        (signal names, may span lines)
        #C <time> <n>                (a time point, n values follow)
         <v1> <v2> ... <vn>
     returns (times, {name: [values]}).

  render_svg(times, traces, vdd, marks) -- stacked step-style traces with a
     VDD/2 reference and optional vertical marker lines (e.g. the settle point).

The CSDF parser is tolerant; if a real file differs, send one screenshot and it
is a one-spot fix (same loop as the rest of the bring-up).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_csdf(text: str) -> Tuple[List[float], Dict[str, List[float]]]:
    names: List[str] = []
    in_names = False
    times: List[float] = []
    cols: List[List[float]] = []
    pending = 0
    vals: List[float] = []

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#N"):
            in_names = True
            names += re.findall(r"'([^']*)'", line)
            continue
        if in_names and line.startswith("'"):
            names += re.findall(r"'([^']*)'", line)
            continue
        in_names = False
        if line.startswith("#C"):
            nums = _NUM.findall(line)
            if nums:
                times.append(float(nums[0]))
            pending = int(nums[1]) if len(nums) > 1 else len(names)
            vals = []
            continue
        if line.startswith("#") or not line:
            continue
        # data values for the current #C point
        for tok in _NUM.findall(line):
            vals.append(float(tok))
        if len(vals) >= pending and pending:
            cols.append(vals[:pending])
            pending = 0

    traces: Dict[str, List[float]] = {n: [] for n in names}
    for row in cols:
        for i, n in enumerate(names):
            if i < len(row):
                traces[n].append(row[i])
    # trim names with no data
    traces = {n: v for n, v in traces.items() if v}
    return times, traces


def render_svg(times: List[float], traces: Dict[str, List[float]], vdd: float,
               marks: Optional[List[Tuple[float, str]]] = None,
               title: str = "P2 transient") -> str:
    marks = marks or []
    W, LH, PADL, PADR, PADT = 1000, 70, 90, 30, 40
    n = len(traces)
    H = PADT + n * LH + 30
    if not times:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="80">'
                f'<text x="10" y="40">no transient data</text></svg>')
    t0, t1 = times[0], times[-1]
    span = (t1 - t0) or 1.0

    def xt(t):
        return PADL + (t - t0) / span * (W - PADL - PADR)

    S = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'font-family="monospace" font-size="12">']
    S.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    S.append(f'<text x="10" y="20" font-size="14">{title}   '
             f't={t0*1e9:.2f}..{t1*1e9:.2f} ns   VDD={vdd}</text>')
    # marker lines (e.g. settle point, capturing edge)
    for tm, lab in marks:
        x = xt(tm)
        S.append(f'<line x1="{x:.1f}" y1="{PADT-5}" x2="{x:.1f}" y2="{H-10}" '
                 f'stroke="#cc0000" stroke-dasharray="4,3"/>')
        S.append(f'<text x="{x+3:.1f}" y="{PADT+6}" fill="#cc0000">{lab}</text>')
    for i, (name, ys) in enumerate(traces.items()):
        base = PADT + i * LH + LH - 18
        top = base - 36
        S.append(f'<text x="6" y="{base-12:.0f}">{name}</text>')
        S.append(f'<line x1="{PADL}" y1="{base}" x2="{W-PADR}" y2="{base}" stroke="#ddd"/>')
        # VDD/2 reference
        yhalf = base - 18
        S.append(f'<line x1="{PADL}" y1="{yhalf}" x2="{W-PADR}" y2="{yhalf}" '
                 f'stroke="#eebbbb" stroke-dasharray="2,3"/>')
        pts = []
        m = min(len(times), len(ys))
        for k in range(m):
            frac = max(0.0, min(1.0, ys[k] / vdd if vdd else 0))
            y = base - frac * 36
            pts.append(f"{xt(times[k]):.1f},{y:.1f}")
        S.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                 f'stroke="#0050b0" stroke-width="1.5"/>')
    S.append("</svg>")
    return "\n".join(S) + "\n"
