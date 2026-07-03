"""
engine/arc_id.py -- parse a real arc identifier (the demo dir-name format) into
an Arc record, so any of the cell's arcs can be pointed at by --arc-id.

Format (anchored on a known cell name, which has no underscores):
  {arc_type}_{cell}_{constr_pin}_{constr_dir}_{rel_pin}_{rel_dir}_{when...}_{i1-i2}

Examples (from the demo listing):
  hold_SDFQSXG..._D_fall_CP_rise_notSE_SI_2-4
      -> hold, constr D/fall, rel CP/rise, when notSE_SI, idx 2-4
  hold_SDFQSXG..._SE_fall_CP_rise_D_notSI_3-3
      -> hold, constr SE/fall, rel CP/rise, when D_notSI, idx 3-3

The cell is passed in (we know it from the netlist) to anchor the split, since
`when` is also `_`-joined. The trailing `i1-i2` token carries a hyphen.
"""
from __future__ import annotations

from typing import Any, Dict


def parse_arc_id(arc_id: str, cell: str) -> Dict[str, Any]:
    toks = arc_id.split("_")
    arc_type = toks[0]
    # strip the leading "{arc_type}_{cell}_"
    prefix = f"{arc_type}_{cell}_"
    if not arc_id.startswith(prefix):
        raise ValueError(f"arc-id {arc_id!r} does not contain cell {cell!r} after "
                         f"the arc_type prefix")
    rest = arc_id[len(prefix):].split("_")
    if len(rest) < 5:
        raise ValueError(f"arc-id tail too short: {rest}")
    constr_pin, constr_dir, rel_pin, rel_dir = rest[0], rest[1], rest[2], rest[3]
    idx = rest[-1]                       # "i1-i2"
    when = "_".join(rest[4:-1]) or "NO_CONDITION"
    return {
        "cell": cell, "arc_type": arc_type,
        "constr_pin": constr_pin, "constr_dir": constr_dir,
        "rel_pin": rel_pin, "rel_dir": rel_dir,
        "when": when, "measurement": f"(from arc-id; idx {idx})",
        "_idx": idx,
    }
