"""
engine/verdict.py -- Compact, self-describing P1/P2/P3 verdict block (spec SS6, SS7.4).

Designed to fit on one screen so it survives the screenshot-only feedback loop
(spec SS7.4). render() returns a string; the caller prints it.
"""
from __future__ import annotations

from engine.types import PipelineResult, Property, PStatus

WIDTH = 72


def _bar(ch: str = "=") -> str:
    return ch * WIDTH


def _prop(p: Property) -> list[str]:
    lines = [f" {p.name} {p.title:<14} [{p.status.value}]"]
    for d in p.detail:
        lines.append(f"    {d}")
    return lines


def render(result: PipelineResult) -> str:
    v = result.verdict
    arc = result.arc
    lines: list[str] = []
    lines.append(_bar())
    lines.append(" DeckGen v2 -- P1/P2/P3 Verdict  (S0-2 real: LPE+CCC+sens | S3-5 stub)")
    lines.append(_bar("-"))
    lines.append(f" arc     : {arc.label()}   cell={arc.cell}")
    lines.append(f" backend : {result.backend_name:<8} deck: {result.deck.line_count()} lines"
                 f"     overall: {v.overall.value}")
    lines.append(_bar("-"))
    lines.extend(_prop(v.p1))
    lines.extend(_prop(v.p2))
    lines.append("    (P2 is the load-bearing property -- spec SS6/SS9)")
    lines.extend(_prop(v.p3))
    lines.append(_bar("="))
    lines.append(" Synthetic LPE fixture. S0/S1 derive real topology; S2-5 still stubbed.")
    lines.append(_bar("="))
    return "\n".join(lines)


def render_status(result: PipelineResult) -> str:
    """One-line-per-stage trace; pairs with render() for a full one-screen status."""
    return "\n".join(result.stage_log)
