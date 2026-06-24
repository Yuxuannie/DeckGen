"""library_audit.py -- run the engine's combinational WHEN-derivation audit over a
whole library and produce an importance-sorted, cohort-split report.

This is the Demo-1 scale capability (ARCHITECTURE.md SS5): for every combinational
cell x arc in a collateral library, the engine derives the sensitizing REGION from
the .subckt topology ALONE (Red Line A) and the verdict compares it to the kit's
-when (region equivalence, Red Line B): MATCH / DIVERGENCE / UNSUPPORTED-WHEN.

The value is the SPLIT, not "all green":
  - cohort TRUST   = MATCH arcs (engine confirms the kit).
  - cohort FLAGGED = DIVERGENCE / UNSUPPORTED / ERROR arcs (the engine wants a look).
FLAGGED is sorted to the top by importance so a large report stays actionable.

Two entry points:
  audit_from_paths(template_tcl_path, netlist_dir, ...)   -- discovery-free core,
      testable without manifest/corner machinery.
  audit_combinational_library(collateral_root, node, lib_type, corner, ...)
      -- thin wrapper that resolves those paths via CollateralStore (real backend).

stdlib-only (airgap), ASCII. Never raises on a single bad cell: it becomes an
ERROR row so one broken cell cannot abort a library run.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List, Optional

from core.engine_present import combinational_sensitization_view
from core.parsers.template_tcl import parse_template_tcl_full
from core.resolver import NetlistResolver, ResolutionError

# Verdict importance: lower sorts first (most actionable on top).
_RANK = {"DIVERGENCE": 0, "UNSUPPORTED-WHEN": 1, "ERROR": 2, "MATCH": 3}
_FLAGGED = {"DIVERGENCE", "UNSUPPORTED-WHEN", "ERROR"}


def _output_from_vector(pinlist: List[str], vector: str,
                        output_pins: List[str]) -> Optional[str]:
    """Which output pin does this arc's -vector say is toggling?

    The -vector is one char per pin in pinlist order (R/F = transition, x = static;
    PROJECT_NOTES SS2.3). For a multi-output cell, only the -vector tells which
    output a given arc measures -- output_pins[0] would mis-assign carry/sum arcs.
    Returns None if it cannot be determined (caller falls back to output_pins[0]).
    """
    v = (vector or "").strip()
    if not v or not pinlist or len(v) != len(pinlist):
        return None
    outs = set(output_pins)
    for pin, ch in zip(pinlist, v):
        if pin in outs and ch in "RFrf":
            return pin
    return None


def _combinational_groups(parsed: dict):
    """{(cell, rel_pin, output): {output, whens[]}} for combinational arcs only.

    The collateral encodes a split sensitizing region as several arcs sharing
    (cell, rel_pin, output); we collect their distinct -when conjunctions into one
    set (W_coll) -- that is what region equivalence compares against. The output is
    taken from each arc's -vector (multi-output correctness), falling back to the
    cell's first output pin when the vector cannot disambiguate.
    """
    cells = parsed.get("cells", {})
    groups: Dict[tuple, dict] = {}
    whens: Dict[tuple, set] = defaultdict(set)
    for arc in parsed.get("arcs", []):
        if arc.get("arc_type") != "combinational":
            continue
        cell, rel = arc["cell"], arc["rel_pin"]
        cinfo = cells.get(cell, {})
        outs = cinfo.get("output_pins") or []
        if not outs:
            continue
        pinlist = (cinfo.get("pinlist") or "").split()
        out = _output_from_vector(pinlist, arc.get("vector", ""), outs) or outs[0]
        key = (cell, rel, out)
        groups.setdefault(key, {"output": out, "n_outputs": len(outs)})
        whens[key].add(arc.get("when", "NO_CONDITION"))
    for key, g in groups.items():
        g["whens"] = sorted(whens[key])
    return groups


def _audit_one(netlist_path: Optional[str], cell: str, rel: str, output: str,
               whens: List[str]) -> dict:
    """One (cell, rel_pin -> output) arc group -> a result row. Never raises."""
    if not netlist_path:
        return {"cell": cell, "rel_pin": rel, "output": output, "status": "ERROR",
                "detail": "no netlist .spi resolved for cell", "kit_whens": whens}
    # NO_CONDITION-only groups are unconditional arcs; pass [] so the verdict uses
    # Option A (cover := SENSITIZING), not a literal "NO_CONDITION" cover.
    when_args = [w for w in whens if w not in ("NO_CONDITION", "", "NONE")]
    view = combinational_sensitization_view(
        netlist_path, cell, rel_pin=rel, output=output, when_strings=when_args)
    if view.get("status") != "OK":
        return {"cell": cell, "rel_pin": rel, "output": output, "status": "ERROR",
                "detail": view.get("error", "engine could not derive"),
                "kit_whens": whens}
    v = view["verdict"]
    return {
        "cell": cell, "rel_pin": rel, "output": output,
        "status": v["status"],
        "kit_whens": whens,
        "side_pins": view["side_pins"],
        "sensitizing": view["sensitizing"],   # [{label,assign,out_dir,sig}]
        "blocked": view["blocked"],
        "needs_split": view["needs_split"],
        "cover": v["cover"],
        "missing": v["missing"],
        "extra": v["extra"],
        "detail": v["detail"],
    }


def _sort_key(row: dict):
    sev = len(row.get("missing", [])) + len(row.get("extra", []))
    return (_RANK.get(row["status"], 9), -sev, row["cell"], row["rel_pin"])


def audit_from_paths(template_tcl_path: str, netlist_dir: Optional[str],
                     cells: Optional[List[str]] = None) -> dict:
    """Core audit: parse template.tcl, derive+verdict each combinational arc from
    its netlist, aggregate. `cells` optionally restricts to a subset (e.g. for a
    fast GUI preview). Discovery-free; see audit_combinational_library for the
    collateral-backed wrapper."""
    parsed = parse_template_tcl_full(template_tcl_path)
    groups = _combinational_groups(parsed)
    if cells:
        want = set(cells)
        groups = {k: v for k, v in groups.items() if k[0] in want}

    resolver = NetlistResolver(netlist_dir) if netlist_dir else None
    netlist_cache: Dict[str, Optional[str]] = {}

    def resolve(cell: str) -> Optional[str]:
        if cell in netlist_cache:
            return netlist_cache[cell]
        path = None
        if resolver is not None:
            try:
                path = resolver.resolve(cell)[0]
            except (ResolutionError, Exception):
                path = None
        netlist_cache[cell] = path
        return path

    rows: List[dict] = []
    for (cell, rel, out), g in sorted(groups.items()):
        try:
            rows.append(_audit_one(resolve(cell), cell, rel, out, g["whens"]))
        except Exception as e:                      # isolation: one cell never aborts
            rows.append({"cell": cell, "rel_pin": rel, "output": out,
                         "status": "ERROR", "detail": "audit exception: %s" % e,
                         "kit_whens": g.get("whens", [])})

    rows.sort(key=_sort_key)
    flagged = [r for r in rows if r["status"] in _FLAGGED]
    trust = [r for r in rows if r["status"] == "MATCH"]
    counts: Dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    summary = {
        "cells": len({r["cell"] for r in rows}),
        "arcs": len(rows),
        "match": counts.get("MATCH", 0),
        "divergence": counts.get("DIVERGENCE", 0),
        "unsupported": counts.get("UNSUPPORTED-WHEN", 0),
        "error": counts.get("ERROR", 0),
        "flagged": len(flagged),
    }
    return {"summary": summary, "rows": rows,
            "cohorts": {"flagged": flagged, "trust": trust}}


def audit_combinational_library(collateral_root: str, node: str, lib_type: str,
                                corner: str, cells: Optional[List[str]] = None,
                                skip_autoscan: bool = False) -> dict:
    """Collateral-backed wrapper: resolve template.tcl + netlist dir for (node,
    lib_type, corner) via CollateralStore, then run audit_from_paths. This is the
    airgap entry point -- the only thing that changes for real data is the
    collateral_root / corner pointer (ARCHITECTURE.md SS4)."""
    from core.collateral import CollateralStore
    store = CollateralStore(collateral_root, node, lib_type,
                            skip_autoscan=skip_autoscan)
    template = store.get_template_tcl(corner)
    netlist_dir = store.get_netlist_dir(corner)
    result = audit_from_paths(template, netlist_dir, cells=cells)
    result["context"] = {"node": node, "lib_type": lib_type, "corner": corner,
                         "template_tcl": template, "netlist_dir": netlist_dir}
    return result
