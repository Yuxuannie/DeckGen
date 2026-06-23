#!/usr/bin/env python3
"""
batch_report.py -- run the REAL batch pipeline from an arcs CSV/file and emit an
interactive report.html. Connects the report to the existing feasibility flow:
core.batch resolves every (arc, corner) against the collateral and records why an
arc cannot be generated; this driver renders that outcome.

  python3 tools/batch_report.py \
      --arcs_file arcs.txt --corners ssgnp_0p450v_m40c_cworst_CCworst_T \
      --node N2P_v1.0 --lib_type test_lib \
      --collateral_root tests/fixtures/collateral --output ./batch_out

arcs file: one cell_arc_pt identifier per line (the existing CSV/batch format).
Stdlib only, ASCII source.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.batch import run_batch
from core.report import build_report, render_html, rows_from_batch
from tools.scan_collateral import build_manifest

TOOL_VERSION = "batch-report-0.1"


def run(arcs_text, corners, node, lib_type, collateral_root, output,
        nominal_only=True):
    os.makedirs(output, exist_ok=True)
    manifest = os.path.join(collateral_root, node, lib_type, "manifest.json")
    if not os.path.isfile(manifest):
        build_manifest(collateral_root, node, lib_type)

    arc_ids = [ln.strip() for ln in arcs_text.splitlines()
               if ln.strip() and not ln.strip().startswith("#")]
    jobs, results, errors = run_batch(
        arc_ids, corners, files={}, output_dir=output,
        node=node, lib_type=lib_type, collateral_root=collateral_root,
        nominal_only=nominal_only)

    rows = rows_from_batch(jobs, results)
    context = {"node": node, "lib_type": lib_type,
               "corner": ", ".join(corners), "collateral_root": collateral_root,
               "output_dir": output, "arcs_requested": str(len(arc_ids)),
               "tool_version": TOOL_VERSION,
               "planner_errors": "; ".join(errors) if errors else ""}
    report = build_report(rows, context)
    html_path = os.path.join(output, "report.html")
    with open(html_path, "w", encoding="ascii", errors="replace") as fh:
        fh.write(render_html(report))

    s = report["summary"]
    print("batch: %d arc-job(s) -> OK=%d FAIL=%d SKIP=%d ERROR=%d"
          % (s["total"], s["ok"], s["fail"], s["skip"], s.get("error", 0)))
    if errors:
        print("planner errors: %s" % "; ".join(errors))
    print("report: %s   (open in a browser)" % html_path)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run the batch pipeline from an arcs CSV -> report.html")
    ap.add_argument("--arcs_file", required=True)
    ap.add_argument("--corners", default="", help="comma-separated corner names")
    ap.add_argument("--corners_file", default="")
    ap.add_argument("--node", required=True)
    ap.add_argument("--lib_type", required=True)
    ap.add_argument("--collateral_root", required=True)
    ap.add_argument("--output", default="./batch_out")
    ap.add_argument("--with_mc", action="store_true",
                    help="also build the MC deck (default: nominal/FMC only)")
    args = ap.parse_args(argv)

    with open(args.arcs_file, "r", encoding="ascii", errors="replace") as fh:
        arcs_text = fh.read()
    if args.corners_file:
        with open(args.corners_file, "r", encoding="ascii") as fh:
            corners = [c.strip() for c in fh if c.strip()]
    else:
        corners = [c.strip() for c in args.corners.split(",") if c.strip()]
    if not corners:
        ap.error("provide --corners or --corners_file")

    run(arcs_text, corners, args.node, args.lib_type, args.collateral_root,
        args.output, nominal_only=not args.with_mc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
