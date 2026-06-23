#!/usr/bin/env python3
"""
gen_cell_report.py -- MVP driver: a cell -> its combinational FMC decks + an
interactive HTML report. The smallest end-to-end model to verify the flow.

  python3 tools/gen_cell_report.py \
      --collateral_root tests/fixtures/collateral \
      --node N2P_v1.0 --lib_type test_lib \
      --corner ssgnp_0p450v_m40c_cworst_CCworst_T \
      --cell DFFQ1 --output ./mvp_out

For each combinational arc of the cell (enumerated from template.tcl), it
resolves collateral, builds the deck, writes <output>/<cell>/<arc>.sp, and
collects an outcome row. Then it builds report.html (core/report.py).

One nominal index point per arc (i1=i2=1) -- full index-grid expansion is a
later step. Stdlib only, ASCII source.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.collateral import CollateralStore, CollateralError
from core.parsers.template_tcl import parse_template_tcl_full
from core.resolver import resolve_all_from_collateral
from core.deck_builder import build_deck
from core.report import build_report, render_html
from tools.scan_collateral import build_manifest

TOOL_VERSION = "mvp-0.1"


def _arc_id(cell, a, probe):
    when = (a.get("when") or "NO_CONDITION").replace("&", "_").replace("!", "not")
    return (f"{a.get('arc_type', '')}_{cell}_{probe}_{a.get('pin_dir', '')}_"
            f"{a.get('rel_pin', '')}_{a.get('rel_pin_dir', '')}_{when}").strip("_")


def _combinational_arcs(parsed, cell):
    out = []
    for a in parsed.get("arcs", []):
        if a.get("cell") == cell and a.get("arc_type") == "combinational":
            out.append(a)
    return out


def run(collateral_root, node, lib_type, corner, cell, output,
        method="template"):
    os.makedirs(output, exist_ok=True)
    # 1. manifest (build if missing)
    manifest = os.path.join(collateral_root, node, lib_type, "manifest.json")
    if not os.path.isfile(manifest):
        build_manifest(collateral_root, node, lib_type)
    store = CollateralStore(collateral_root, node, lib_type, skip_autoscan=True)

    # 2. enumerate combinational arcs from the cell's template.tcl
    tcl = store.get_template_tcl(corner)
    parsed = parse_template_tcl_full(tcl)
    cell_info = parsed.get("cells", {}).get(cell, {})
    out_pins = cell_info.get("output_pins", [])
    arcs = _combinational_arcs(parsed, cell)

    deck_dir = os.path.join(output, cell)
    os.makedirs(deck_dir, exist_ok=True)

    rows = []
    for a in arcs:
        probe = a.get("pin") or (out_pins[0] if out_pins else "")
        rel_pin, rel_dir = a.get("rel_pin", ""), a.get("rel_pin_dir", "")
        constr_dir = a.get("pin_dir", "")
        when = a.get("when", "NO_CONDITION")
        row = {"cell": cell, "arc_type": "combinational", "rel_pin": rel_pin,
               "rel_dir": rel_dir, "probe_pin": probe, "constr_dir": constr_dir,
               "when": when, "corner": corner}
        try:
            info = resolve_all_from_collateral(
                cell_name=cell, arc_type="combinational",
                rel_pin=rel_pin, rel_dir=rel_dir, constr_pin=probe,
                constr_dir=constr_dir, probe_pin=probe, node=node,
                lib_type=lib_type, corner_name=corner,
                collateral_root=collateral_root)
            info = info[0] if isinstance(info, list) else info
            tmpl = info.get("TEMPLATE_DECK_PATH") or ""
            row["template"] = os.path.basename(tmpl)
            row["index_1"] = info.get("INDEX_1_VALUE") or ""
            row["index_2"] = info.get("INDEX_2_VALUE") or ""
            if not tmpl:
                row["status"] = "SKIP"
                row["reason"] = "no template matched for this arc"
                rows.append(row)
                continue
            if method == "generator":
                from core.deck_recipe import build_combinational_deck
                lines = [ln + "\n" for ln in build_combinational_deck(info)]
                row["template"] = "deck_recipe (generator)"
            else:
                lines = build_deck(
                    info, slew=(info.get("INDEX_1_VALUE") or "0",
                                info.get("INDEX_1_VALUE") or "0"),
                    load=info.get("INDEX_2_VALUE") or "0",
                    when=info.get("WHEN", when),
                    max_slew=info.get("MAX_SLEW") or "1n")
            deck_text = "".join(lines)
            path = os.path.join(deck_dir, _arc_id(cell, a, probe) + ".sp")
            with open(path, "w", encoding="ascii", errors="replace") as fh:
                fh.write(deck_text)
            row["status"] = "OK"
            row["deck_path"] = path
            row["deck_text"] = deck_text
        except Exception as e:                       # never drop an arc silently
            row["status"] = "FAIL"
            row["reason"] = str(e)[:300]
        rows.append(row)

    context = {"node": node, "lib_type": lib_type, "corner": corner,
               "collateral_root": collateral_root, "output_dir": output,
               "tool_version": TOOL_VERSION}
    report = build_report(rows, context)
    html_path = os.path.join(output, "report.html")
    with open(html_path, "w", encoding="ascii", errors="replace") as fh:
        fh.write(render_html(report))

    s = report["summary"]
    print(f"cell {cell}: {s['total']} combinational arc(s) -> "
          f"OK={s['ok']} FAIL={s['fail']} SKIP={s['skip']} ERROR={s.get('error', 0)}")
    print(f"decks : {deck_dir}/")
    print(f"report: {html_path}   (open in a browser)")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="MVP: cell -> combinational FMC decks + HTML report")
    ap.add_argument("--collateral_root", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--lib_type", required=True)
    ap.add_argument("--corner", required=True)
    ap.add_argument("--cell", required=True)
    ap.add_argument("--output", default="./mvp_out")
    ap.add_argument("--method", default="template", choices=["template", "generator"])
    args = ap.parse_args(argv)
    run(args.collateral_root, args.node, args.lib_type, args.corner, args.cell,
        args.output, method=args.method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
