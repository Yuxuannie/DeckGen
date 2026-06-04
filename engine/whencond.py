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

from typing import Dict


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
