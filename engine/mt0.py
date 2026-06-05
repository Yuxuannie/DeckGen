"""
engine/mt0.py -- parse an HSPICE .mt0 measure-output file into {name: value}.

.mt0 format (whitespace/columnar):
  Title / comment lines start with '$' or '*'.
  A header row of measure names, then a row of values (may wrap). For a single
  operating point HSPICE writes one name row + one value row; names and values
  align by position. Failed measures show 'failed' -> stored as None.

We parse robustly: collect the name tokens and value tokens after the header and
zip them. Values like '1.2345e-01' -> float; 'failed'/'nan' -> None.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def _isfloat(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False


def parse_mt0(text: str) -> Dict[str, Optional[float]]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    # drop comment/title/directive lines ($DATA, *comment, .TITLE, ...)
    rows = [ln for ln in lines if ln.strip()
            and not ln.lstrip().startswith(("$", "*", "."))]
    if not rows:
        return {}

    # find the header row: tokens are measure names (non-numeric), e.g. starts
    # with 'alter#' or measure names. The following row(s) hold values.
    names: List[str] = []
    values: List[str] = []
    header_done = False
    for ln in rows:
        toks = ln.split()
        if not header_done and not all(_isfloat(t) or t in ("failed", "nan") for t in toks):
            names.extend(toks)
            # header may wrap across lines until a numeric row appears
            continue
        header_done = True
        values.extend(toks)

    out: Dict[str, Optional[float]] = {}
    for i, name in enumerate(names):
        if i < len(values):
            v = values[i]
            out[name] = float(v) if _isfloat(v) else None
    return out
