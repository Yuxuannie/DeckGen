"""
engine/whencond.py -- parse an arc's `when` condition into expected pin biases.

The `when` string is the incumbent flow's ASSERTED sensitization (e.g. from the
arc identifier `..._notSE_SI_...`). The engine derives the bias independently
from topology; this parser lets Stage 2 cross-check derived-vs-asserted so the
output shows agreement instead of looking like it recomputed a given value.

Format: `_`-joined tokens; `notX` -> X=0, `X` -> X=1. "NO_CONDITION"/""/"NONE" -> {}.
  "notSE_SI"  -> {"SE": 0, "SI": 1}
  "D_notSI"   -> {"D": 1, "SI": 0}
"""
from __future__ import annotations

import re
from typing import Dict, Optional


def parse_when_conjunction(when: str) -> Optional[Dict[str, int]]:
    """Parse a template.tcl-style `-when` CONJUNCTION into {pin: 0|1}.

    Accepts `&`- or whitespace-separated literals with `!`/`not` negation
    (e.g. "A1&!A2", "!A1 !A2 B", "notSE&SI"). Empty / NO_CONDITION -> {}.

    Returns None (-> UNSUPPORTED-WHEN, NEVER DIVERGENCE) when the string is not a
    pure conjunction: it contains an OR marker (`|` or `+`), or pins the same pin
    to conflicting values. SCLD realism guard: real kits write OR; coercing an
    OR'd condition into a conjunction computes the wrong covered region and
    false-flags a correct cell. A tool that says "I can't read this one" keeps
    trust; one that silently mis-parses loses it.
    """
    if when is None:
        return {}
    w = when.strip()
    if not w or w.upper() in ("NO_CONDITION", "NONE"):
        return {}
    if "|" in w or "+" in w:                 # OR markers -> not a conjunction
        return None
    out: Dict[str, int] = {}
    for tok in (t for t in re.split(r"[&\s]+", w) if t):
        if tok.startswith("!"):
            pin, val = tok[1:], 0
        elif tok.lower().startswith("not"):
            pin, val = tok[3:], 0
        else:
            pin, val = tok, 1
        if not pin:
            return None
        if pin in out and out[pin] != val:   # contradiction -> not coherent
            return None
        out[pin] = val
    return out


def parse_when(when: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not when or when.upper() in ("NO_CONDITION", "NONE"):
        return out
    for tok in when.split("_"):
        if not tok:
            continue
        if tok.lower().startswith("not"):
            out[tok[3:]] = 0
        else:
            out[tok] = 1
    return out
