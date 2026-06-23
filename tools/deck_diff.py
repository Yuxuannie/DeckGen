#!/usr/bin/env python3
"""
deck_diff.py -- cross-validate the two deck-generation paths.

For every combinational arc of a cell it generates the deck BOTH ways -- the
legacy template substitution (core.deck_builder.build_deck on a template_*.sp)
and the programmatic generator (core.deck_recipe.build_combinational_deck) -- and
diffs them line by line. This is the gate before retiring the .sp templates: the
generator must reproduce them exactly.

  python3 tools/deck_diff.py --cell DFFQ1 \
      --corner ssgnp_0p450v_m40c_cworst_CCworst_T \
      --node N2P_v1.0 --lib_type test_lib \
      --collateral_root tests/fixtures/collateral [--out diffs.txt]

Exit 0 iff every combinational arc MATCHES (and at least one was checked).
Stdlib only, ASCII source.
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.collateral import CollateralStore
from core.deck_builder import build_deck
from core.deck_recipe import build_combinational_deck
from core.parsers.template_tcl import parse_template_tcl_full
from core.resolver import resolve_all_from_collateral
from tools.scan_collateral import build_manifest


def _arc_id(cell, a, probe):
    when = (a.get("when") or "NO_CONDITION").replace("&", "_").replace("!", "not")
    return ("combinational_%s_%s_%s_%s_%s_%s"
            % (cell, probe, a.get("pin_dir", ""), a.get("rel_pin", ""),
               a.get("rel_pin_dir", ""), when))


def _template_lines(info):
    ls = build_deck(info,
                    slew=(info.get("INDEX_1_VALUE") or "0",
                          info.get("INDEX_1_VALUE") or "0"),
                    load=info.get("INDEX_2_VALUE") or "0",
                    when=info.get("WHEN"), max_slew=info.get("MAX_SLEW") or "1n")
    return [ln.rstrip("\n") for ln in ls]


def diff_cell(collateral_root, node, lib_type, corner, cell):
    """Return a list of {arc, status, ndiff, diff} for the cell's comb. arcs."""
    manifest = os.path.join(collateral_root, node, lib_type, "manifest.json")
    if not os.path.isfile(manifest):
        build_manifest(collateral_root, node, lib_type)
    store = CollateralStore(collateral_root, node, lib_type, skip_autoscan=True)
    parsed = parse_template_tcl_full(store.get_template_tcl(corner))
    out_pins = parsed.get("cells", {}).get(cell, {}).get("output_pins", [])
    arcs = [a for a in parsed.get("arcs", [])
            if a.get("cell") == cell and a.get("arc_type") == "combinational"]

    rows = []
    for a in arcs:
        probe = a.get("pin") or (out_pins[0] if out_pins else "")
        rec = {"arc": _arc_id(cell, a, probe), "status": "", "ndiff": 0, "diff": ""}
        try:
            info = resolve_all_from_collateral(
                cell_name=cell, arc_type="combinational",
                rel_pin=a.get("rel_pin", ""), rel_dir=a.get("rel_pin_dir", ""),
                constr_pin=probe, constr_dir=a.get("pin_dir", ""),
                probe_pin=probe, node=node, lib_type=lib_type,
                corner_name=corner, collateral_root=collateral_root,
                # nominal index point (1,1) -- same on both paths, so the deck
                # carries real slew/load and the diff stays a fair comparison.
                overrides={"index_1_index": 1, "index_2_index": 1})
            info = info[0] if isinstance(info, list) else info
            tmpl = _template_lines(info)
            gen = build_combinational_deck(info)
            if tmpl == gen:
                rec["status"] = "MATCH"
            else:
                rec["status"] = "DIFF"
                ud = list(difflib.unified_diff(
                    tmpl, gen, fromfile="template", tofile="generator",
                    lineterm=""))
                rec["ndiff"] = sum(1 for d in ud
                                   if d[:1] in "+-" and d[:3] not in ("+++", "---"))
                rec["diff"] = "\n".join(ud)
        except Exception as e:                       # never drop an arc silently
            rec["status"] = "ERROR"
            rec["diff"] = str(e)[:400]
        rows.append(rec)
    return rows


def run(collateral_root, node, lib_type, corner, cells, out_path=None):
    all_rows = []
    for cell in cells:
        all_rows.extend(diff_cell(collateral_root, node, lib_type, corner, cell))

    n = len(all_rows)
    nmatch = sum(1 for r in all_rows if r["status"] == "MATCH")
    ndiff = sum(1 for r in all_rows if r["status"] == "DIFF")
    nerr = sum(1 for r in all_rows if r["status"] == "ERROR")
    print("deck_diff: %d combinational arc(s) -> MATCH=%d DIFF=%d ERROR=%d"
          % (n, nmatch, ndiff, nerr))
    for r in all_rows:
        if r["status"] != "MATCH":
            print("  [%s] %s  (%d diff line(s))"
                  % (r["status"], r["arc"], r["ndiff"]))
    if out_path:
        with open(out_path, "w", encoding="ascii", errors="replace") as fh:
            for r in all_rows:
                fh.write("=== %s [%s] ===\n" % (r["arc"], r["status"]))
                if r["diff"]:
                    fh.write(r["diff"] + "\n")
        print("wrote %s" % out_path)
    return all_rows, (n > 0 and ndiff == 0 and nerr == 0)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Diff template vs programmatic deck generation (combinational)")
    ap.add_argument("--cell", help="cell name (or --cells)")
    ap.add_argument("--cells", help="comma-separated cell names")
    ap.add_argument("--corner", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--lib_type", required=True)
    ap.add_argument("--collateral_root", required=True)
    ap.add_argument("--out", default=None, help="write full diffs to this file")
    args = ap.parse_args(argv)

    cells = []
    if args.cells:
        cells += [c.strip() for c in args.cells.split(",") if c.strip()]
    if args.cell:
        cells.append(args.cell)
    if not cells:
        ap.error("provide --cell or --cells")

    _rows, ok = run(args.collateral_root, args.node, args.lib_type, args.corner,
                    cells, args.out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
