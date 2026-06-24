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

from core.parsers.template_tcl import parse_template_tcl_full
from core.resolver import NetlistResolver, ResolutionError

# Above this many side pins, exhaustive 2^n enumeration is too slow; mark the arc
# OUT-OF-SCOPE rather than hang the whole library run on one wide cell.
_MAX_SIDE_PINS = 12

# Verdict importance: lower sorts first (most actionable on top).
_RANK = {"DIVERGENCE": 0, "UNSUPPORTED-WHEN": 1, "ERROR": 2,
         "OUT-OF-SCOPE": 3, "MATCH": 4}
_FLAGGED = {"DIVERGENCE", "UNSUPPORTED-WHEN", "ERROR"}
# OUT-OF-SCOPE = sequential/clock cells the combinational engine cannot audit;
# they are NOT flagged (not divergences) and NOT trust -- their own bucket.


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


def _row(cell, rel, out, status, whens, **extra):
    r = {"cell": cell, "rel_pin": rel, "output": out, "status": status,
         "kit_whens": whens}
    r.update(extra)
    return r


def _audit_arc(graph, ccc, cell: str, rel: str, output: str,
               whens: List[str]) -> dict:
    """One (cell, rel_pin -> output) arc group -> a verdict-level row, using a
    pre-parsed graph (parsed once per cell, reused across its arcs). Never raises.
    The rich region/topology data is recomputed on demand by arc_detail_view when
    a row is clicked, so the list rows stay light."""
    from engine.stages import stage2_sensitize
    from engine.types import Arc
    arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel, rel_dir="rise",
              constr_pin=output, constr_dir="rise", when="NO_CONDITION",
              measurement="", raw={"probe_pin": output})
    if not stage2_sensitize.is_combinational_arc(graph, arc, ccc):
        return _row(cell, rel, output, "OUT-OF-SCOPE", whens,
                    detail="arc CCC has a state node -- sequential, not combinational")
    # cap the 2^n enumeration so one wide cell can't hang the whole run
    inputs, _ = stage2_sensitize._inputs_outputs(graph)
    n_side = len([p for p in inputs if p != rel])
    if n_side > _MAX_SIDE_PINS:
        return _row(cell, rel, output, "OUT-OF-SCOPE", whens,
                    detail="too many inputs (%d side pins) for exhaustive "
                           "enumeration -- skipped" % n_side)
    when_args = [w for w in whens if w not in ("NO_CONDITION", "", "NONE")]
    res = stage2_sensitize.derive_combinational(graph, arc, ccc)
    v = stage2_sensitize.comb_verdict(res, when_args)
    return _row(cell, rel, output, v.status.value, whens,
                missing=v.missing, extra=v.extra, detail=v.detail)


def _sort_key(row: dict):
    sev = len(row.get("missing", [])) + len(row.get("extra", []))
    return (_RANK.get(row["status"], 9), -sev, row["cell"], row["rel_pin"])


def audit_from_paths(template_tcl_path: str, netlist_dir: Optional[str],
                     cells: Optional[List[str]] = None, progress=None) -> dict:
    """Core audit: parse template.tcl, derive+verdict each combinational arc from
    its netlist, aggregate. `cells` optionally restricts to a subset (e.g. for a
    fast GUI preview). `progress(done, total, cell, status)` is called after each
    arc (optional) so a GUI can show a bar + log. Discovery-free; see
    audit_combinational_library for the collateral-backed wrapper."""
    parsed = parse_template_tcl_full(template_tcl_path)
    groups = _combinational_groups(parsed)
    if cells:
        want = set(cells)
        groups = {k: v for k, v in groups.items() if k[0] in want}

    resolver = NetlistResolver(netlist_dir) if netlist_dir else None
    graph_cache: Dict[str, tuple] = {}        # cell -> (graph|None, ccc|None, err)

    def cell_graph(cell: str):
        """Parse a cell's netlist ONCE (graph + CCC), reused across all its arcs.
        Re-parsing the same large LPE netlist per arc was the main slowdown."""
        if cell in graph_cache:
            return graph_cache[cell]
        from engine.stages import stage0_parse, stage1_ccc
        graph = ccc = None
        err = None
        path = None
        if resolver is not None:
            try:
                path = resolver.resolve(cell)[0]
            except Exception:
                path = None
        if not path:
            err = "no netlist .spi resolved for cell"
        else:
            try:
                with open(path, encoding="ascii", errors="replace") as fh:
                    src = fh.read()
                graph = stage0_parse.parse(src, cell)
                ccc = stage1_ccc.decompose(graph)
            except Exception as e:
                graph = ccc = None
                err = "parse failed: %s" % e
        graph_cache[cell] = (graph, ccc, err)
        return graph_cache[cell]

    rows: List[dict] = []
    items = sorted(groups.items())
    total = len(items)
    for i, ((cell, rel, out), g) in enumerate(items):
        try:
            graph, ccc, err = cell_graph(cell)
            if graph is None:
                row = _row(cell, rel, out, "ERROR", g["whens"], detail=err)
            else:
                row = _audit_arc(graph, ccc, cell, rel, out, g["whens"])
        except Exception as e:                      # isolation: one cell never aborts
            row = _row(cell, rel, out, "ERROR", g.get("whens", []),
                       detail="audit exception: %s" % e)
        rows.append(row)
        if progress is not None:
            try:
                progress(i + 1, total, cell, row["status"])
            except Exception:
                pass                                # progress must never break the run

    rows.sort(key=_sort_key)
    flagged = [r for r in rows if r["status"] in _FLAGGED]
    trust = [r for r in rows if r["status"] == "MATCH"]
    out_of_scope = [r for r in rows if r["status"] == "OUT-OF-SCOPE"]
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
        "out_of_scope": counts.get("OUT-OF-SCOPE", 0),
        "flagged": len(flagged),
    }
    return {"summary": summary, "rows": rows,
            "cohorts": {"flagged": flagged, "trust": trust,
                        "out_of_scope": out_of_scope}}


def audit_combinational_library(collateral_root: str, node: str, lib_type: str,
                                corner: str, cells: Optional[List[str]] = None,
                                skip_autoscan: bool = False, progress=None) -> dict:
    """Collateral-backed wrapper: resolve template.tcl + netlist dir for (node,
    lib_type, corner) via CollateralStore, then run audit_from_paths. This is the
    airgap entry point -- the only thing that changes for real data is the
    collateral_root / corner pointer (ARCHITECTURE.md SS4)."""
    from core.collateral import CollateralStore
    store = CollateralStore(collateral_root, node, lib_type,
                            skip_autoscan=skip_autoscan)
    template = store.get_template_tcl(corner)
    netlist_dir = store.get_netlist_dir(corner)
    result = audit_from_paths(template, netlist_dir, cells=cells, progress=progress)
    result["context"] = {"node": node, "lib_type": lib_type, "corner": corner,
                         "template_tcl": template, "netlist_dir": netlist_dir}
    return result
