#!/usr/bin/env python3
"""seq_probe.py -- air-gapped structural probe for sequential cells (B2 de-risk).

WHY THIS EXISTS
  B2 classifies a sequential cell's CCC as latch / ff_chain / multibit /
  recognized_unsupported and derives depth. This script exercises the SHARED
  engine functions (build_storage_view + classify) on real LPE netlists and
  prints an abstract structural signature per cell:
    - device / net / port counts and port roles (in / out / rail)
    - storage cores the engine finds (cross-coupled SCCs), their size, their
      influence-distance to the output, and the master/slave label stage1 assigns
    - which OUTPUT CONE each storage core feeds, and the output-cone PARTITION
      (this is the multibit discriminator: N independent bits => N groups)
    - the B2 verdict from classify() -- probe and engine cannot diverge

  Internal net names are ANONYMIZED by default (n0, n1, ...), so nothing
  proprietary leaves your environment -- only counts, roles, and graph shape.
  The output is compact and ASCII, so a screenshot carries everything back.

WHAT TO SEND BACK
  A screenshot (or paste) of the report for one cell of each kind you have:
  a transparent latch, a single DFF, a 2+ stage synchronizer (sync2..sync6),
  a multibit / multi-bank FF, and (if handy) a retention FF. That tells us
  whether the engine already sees the right structure, and exactly where B2
  must add logic.

USAGE (run from the deckgen/ repo root, or set PYTHONPATH to it)
  # one cell (cell name defaults to the file stem minus a trailing _c):
  python3 tools/seq_probe.py path/to/DFFQ1_c.spi
  python3 tools/seq_probe.py path/to/NETLIST.spi --cell DFFQ1

  # every .spi/.subckt netlist in a directory (one report each + a summary):
  python3 tools/seq_probe.py --dir path/to/Netlist/LPE_cworst_CCworst_T_m40c/

  # show the (anonymized) transistor list too, so a fixture can be reconstructed:
  python3 tools/seq_probe.py path/to/DFFQ1_c.spi --devices

  # show REAL net names instead of anonymized ones (only if you deem it safe):
  python3 tools/seq_probe.py path/to/DFFQ1_c.spi --raw

stdlib + engine only. ASCII only. Read-only: it never writes or simulates.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from engine.stages import stage0_parse, stage1_ccc          # noqa: E402
from engine.stages.stage1_ccc import RAILS                  # noqa: E402
from engine.stages.storage_view import build_storage_view   # noqa: E402
from engine.stages.stage1b_classify import classify         # noqa: E402


def analyze(netlist_path, cell, anon=True, show_devices=False):
    with open(netlist_path, encoding="ascii", errors="replace") as fh:
        src = fh.read()
    graph = stage0_parse.parse(src, cell)
    devs = graph.devices

    # Shared B2 engine: extract storage structure and classify.
    view = build_storage_view(graph)
    result = classify(graph, cell)

    # Official stage1 labels for the per-core role column (cross-check only).
    ccc = stage1_ccc.decompose(graph)
    net_role = {sn.net: sn.role for sn in ccc.state_nodes}

    # Port roles (needed for the ports: display line).
    driven = {d.terminals["d"] for d in devs}
    input_ports = {p for p in graph.ports if p not in RAILS and p not in driven}
    output_ports = {p for p in graph.ports if p in driven and p not in RAILS}

    # anonymize internal net names for display
    if anon:
        internal = sorted(n for n in graph.nets
                          if n not in graph.ports and n not in RAILS)
        amap = {n: "n%d" % i for i, n in enumerate(internal)}
    else:
        amap = {}
    show = lambda n: amap.get(n, n)
    showset = lambda ss: "{%s}" % ",".join(sorted(show(n) for n in ss))

    n_nmos = sum(1 for d in devs if d.kind == "nmos")
    n_pmos = sum(1 for d in devs if d.kind == "pmos")

    out = []
    out.append("=== %s [%s] ===" % (cell, os.path.basename(netlist_path)))
    out.append("devices: %d (nmos %d, pmos %d)   nets: %d"
               % (len(devs), n_nmos, n_pmos, len(graph.nets)))
    out.append("ports: in=%s  out=%s  rail=%s"
               % ("{%s}" % ",".join(sorted(input_ports)),
                  "{%s}" % ",".join(sorted(output_ports)),
                  "{%s}" % ",".join(sorted(p for p in graph.ports if p in RAILS))))
    out.append("CCC channel-components: %d" % len(ccc.components))
    out.append("storage cores (cross-coupled SCC>=2, gate-controlling): %d"
               % len(view.cores))
    for i, c in enumerate(view.cores):
        roles = sorted({net_role.get(n, "?") for n in c.nets})
        out.append("  core#%d %-18s dist->out %-3s influences %-14s stage1-role=%s"
                   % (i, showset(c.nets),
                      ("inf" if c.dist_to_out >= 10 ** 9 else str(c.dist_to_out)),
                      showset(c.cone), ",".join(roles)))

    # output-cone partition from classify() bits
    nets_to_idx = {c.nets: i for i, c in enumerate(view.cores)}
    if view.cores and result.bits:
        parts = []
        for b_idx, b in enumerate(result.bits):
            cidxs = sorted(nets_to_idx.get(s.nets, -1) for s in b.stages)
            outs_str = "{%s}" % ",".join(sorted(b.outputs))
            parts.append("bit%d->%s:core%s" % (b_idx, outs_str, cidxs))
        part = "  ".join(parts)
        n_groups = len(result.bits)
    elif view.cores:
        part = "(all cores drive no output)"
        n_groups = 0
    else:
        part = "(none)"
        n_groups = 0
    out.append("output-cone partition: %d group(s)   %s" % (n_groups, part))

    # verdict from B2 classify() -- probe now delegates to shared engine
    verdict_str = "B2 verdict: %s" % result.verdict
    if result.reason:
        verdict_str += "  reason: %s" % result.reason
    if result.divergence:
        verdict_str += "  [name-divergence: %s]" % result.divergence
    out.append(verdict_str)

    if show_devices:
        out.append("-- transistors (%sanonymized) --" % ("" if anon else "NOT "))
        for d in devs:
            t = d.terminals
            out.append("  %-6s %-4s d=%s g=%s s=%s b=%s"
                       % (d.name, d.kind, show(t["d"]), show(t["g"]),
                          show(t["s"]), show(t.get("b", "?"))))
    return ("\n".join(out), result.verdict, result.verdict)


def _cell_from_file(path, strip_suffix="_c"):
    stem = os.path.splitext(os.path.basename(path))[0]
    if strip_suffix and stem.endswith(strip_suffix):
        stem = stem[: -len(strip_suffix)]
    return stem


def main(argv=None):
    ap = argparse.ArgumentParser(description="Structural probe for sequential cells.")
    ap.add_argument("netlist", nargs="?", help="path to one LPE netlist (.spi/.subckt)")
    ap.add_argument("--cell", help="cell name (default: file stem minus trailing _c)")
    ap.add_argument("--dir", help="probe every .spi/.subckt netlist in this directory")
    ap.add_argument("--raw", action="store_true",
                    help="show REAL net names (default: anonymized n0,n1,...)")
    ap.add_argument("--devices", action="store_true",
                    help="also print the (anonymized) transistor list")
    ap.add_argument("--aggregate", action="store_true",
                    help="with --dir: print only a verdict histogram + one "
                         "representative full report per bucket (best for big libs)")
    ap.add_argument("--strip-suffix", default="_c",
                    help="filename suffix to strip for cell name (default: _c)")
    args = ap.parse_args(argv)
    anon = not args.raw

    if args.dir:
        paths = sorted(glob.glob(os.path.join(args.dir, "*.spi"))
                       + glob.glob(os.path.join(args.dir, "*.subckt")))
        if not paths:
            print("no .spi/.subckt netlists in %s" % args.dir)
            return 1
        summary = []          # (cell, guess, bucket, report)
        for p in paths:
            cell = _cell_from_file(p, args.strip_suffix)
            try:
                report, guess, bucket = analyze(p, cell, anon=anon,
                                                show_devices=args.devices)
                summary.append((cell, guess, bucket, report))
            except Exception as e:            # a bad cell must be named, never crash the sweep
                summary.append((cell, "PROBE ERROR: %s" % e, "PROBE ERROR",
                                "=== %s [%s] ===\n  PROBE ERROR: %s"
                                % (cell, os.path.basename(p), e)))

        if args.aggregate:
            hist = {}
            first = {}
            for cell, guess, bucket, report in summary:
                hist[bucket] = hist.get(bucket, 0) + 1
                first.setdefault(bucket, (cell, report))
            print("===== VERDICT HISTOGRAM (%d cells) =====" % len(summary))
            for bucket in sorted(hist, key=lambda b: (-hist[b], b)):
                print("  %5d  %-28s e.g. %s" % (hist[bucket], bucket,
                                                first[bucket][0]))
            print("\n===== ONE REPRESENTATIVE REPORT PER BUCKET =====")
            for bucket in sorted(hist, key=lambda b: (-hist[b], b)):
                if bucket == "combinational":
                    continue          # skip the (usually huge) combinational bucket's report
                print("\n# bucket: %s  (%d cells)" % (bucket, hist[bucket]))
                print(first[bucket][1])
            return 0

        for cell, guess, bucket, report in summary:
            print(report)
            print("")
        print("===== SUMMARY (%d cells) =====" % len(summary))
        for cell, guess, bucket, report in summary:
            print("  %-32s %s" % (cell, guess))
        return 0

    if not args.netlist:
        ap.error("give a NETLIST path or --dir")
    cell = args.cell or _cell_from_file(args.netlist, args.strip_suffix)
    report, _, _ = analyze(args.netlist, cell, anon=anon, show_devices=args.devices)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
