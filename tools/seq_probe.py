#!/usr/bin/env python3
"""seq_probe.py -- air-gapped structural probe for sequential cells (B2 de-risk).

WHY THIS EXISTS
  B2 will classify a sequential cell's CCC as latch / FF-chain / multibit /
  recognized-unsupported and derive depth. Before writing B2, we want to know how
  the ALREADY-BUILT engine (stage0 parse + stage1 CCC/storage detection) actually
  behaves on the REAL production library -- not on hand-guessed fixtures.

  This script runs entirely inside your air-gapped environment on the real LPE
  netlists and prints ONLY an abstract structural signature per cell:
    - device / net / port counts and port roles (in / out / rail)
    - storage cores the engine finds (cross-coupled SCCs), their size, their
      influence-distance to the output, and the master/slave label stage1 assigns
    - which OUTPUT CONE each storage core feeds, and the output-cone PARTITION
      (this is the multibit discriminator: N independent bits => N groups)
    - a clearly-labeled HEURISTIC verdict guess (this is the probe's guess, NOT
      B2 -- B2 does not exist yet)

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
from collections import deque

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from engine.stages import stage0_parse, stage1_ccc          # noqa: E402
from engine.stages.stage1_ccc import _sccs, _min_dist, RAILS  # noqa: E402


def _reachable_outputs(influence, core, outputs):
    """Output ports forward-reachable from a storage core in the influence graph."""
    seen = set(core)
    q = deque(core)
    hit = set()
    while q:
        n = q.popleft()
        if n in outputs:
            hit.add(n)
        for w in influence.get(n, ()):
            if w not in seen:
                seen.add(w)
                q.append(w)
    return hit


def _partition_by_cone(cores_meta):
    """Union cores that share any reachable output -> one group per independent bit.
    cores_meta: list of dicts with 'outs' (frozenset). Returns list of index lists."""
    parent = list(range(len(cores_meta)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(cores_meta)):
        for j in range(i + 1, len(cores_meta)):
            if cores_meta[i]["outs"] & cores_meta[j]["outs"]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups = {}
    for i in range(len(cores_meta)):
        groups.setdefault(find(i), []).append(i)
    return [sorted(v) for v in groups.values()]


def _heuristic(n_cores, groups, cores_meta):
    """PROBE guess (NOT B2). Returns a one-line string."""
    if n_cores == 0:
        return "combinational (no storage core found)"
    if len(groups) == 1:
        if n_cores == 1:
            return "LATCH (1 storage core; latch_stages=1)"
        if n_cores % 2 == 0:
            return "FF-chain (latch_stages=%d, ff_depth=%d)" % (n_cores, n_cores // 2)
        return ("FF-chain? ODD core count=%d (sync1p5-like / review -- "
                "cannot pair cleanly)" % n_cores)
    sizes = sorted(len(g) for g in groups)
    per_bit = "; ".join(
        "bit%d=%d core(s)" % (i, len(g)) for i, g in enumerate(groups))
    tag = "MULTIBIT" if all(s == sizes[0] for s in sizes) else "MULTIBIT? (uneven bits)"
    return "%s: %d bits (%s)" % (tag, len(groups), per_bit)


def _bucket(n_cores, groups):
    """Short canonical bucket key for aggregation (one per distinct structure)."""
    if n_cores == 0:
        return "combinational"
    if len(groups) == 1:
        if n_cores == 1:
            return "latch"
        if n_cores % 2 == 0:
            return "FF-chain depth=%d" % (n_cores // 2)
        return "FF-chain ODD cores=%d (review)" % n_cores
    sizes = sorted(len(g) for g in groups)
    even = "MULTIBIT" if all(s == sizes[0] for s in sizes) else "MULTIBIT-uneven"
    return "%s %dbit (cores/bit=%s)" % (even, len(groups), ",".join(map(str, sizes)))


def analyze(netlist_path, cell, anon=True, show_devices=False):
    with open(netlist_path, encoding="ascii", errors="replace") as fh:
        src = fh.read()
    graph = stage0_parse.parse(src, cell)
    devs = graph.devices

    driven = {d.terminals["d"] for d in devs}
    input_ports = {p for p in graph.ports if p not in RAILS and p not in driven}
    output_ports = {p for p in graph.ports if p in driven and p not in RAILS}
    boundaries = RAILS | input_ports

    # influence graph exactly as stage1_ccc.decompose builds it
    influence = {}
    for d in devs:
        dd, g, s = d.terminals["d"], d.terminals["g"], d.terminals["s"]
        for src_net in (g, s):
            if src_net not in RAILS and dd not in RAILS:
                influence.setdefault(src_net, set()).add(dd)

    internal_adj = {u: {w for w in vs if w not in boundaries}
                    for u, vs in influence.items() if u not in boundaries}
    gate_nets = {d.terminals["g"] for d in devs if d.terminals["g"] not in RAILS}
    cores = []
    for scc in _sccs(internal_adj):
        if len(scc) < 2:
            continue
        core = sorted(n for n in scc if n in gate_nets)
        if len(core) >= 2:
            cores.append(core)

    # official stage1 labels, for cross-check
    ccc = stage1_ccc.decompose(graph)
    net_role = {sn.net: sn.role for sn in ccc.state_nodes}

    cores_meta = []
    for core in cores:
        outs = frozenset(_reachable_outputs(influence, core, output_ports))
        dist = _min_dist(influence, set(core), output_ports)
        roles = sorted({net_role.get(n, "?") for n in core})
        cores_meta.append({"core": core, "outs": outs, "dist": dist, "roles": roles})
    cores_meta.sort(key=lambda m: (m["dist"], m["core"]))
    groups = _partition_by_cone(cores_meta)

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
               % len(cores_meta))
    for i, m in enumerate(cores_meta):
        out.append("  core#%d %-18s dist->out %-3s influences %-14s stage1-role=%s"
                   % (i, showset(m["core"]),
                      ("inf" if m["dist"] >= 10 ** 9 else str(m["dist"])),
                      showset(m["outs"]), ",".join(m["roles"])))
    part = "  ".join("bit%d->%s:core%s"
                     % (i, showset(cores_meta[g[0]]["outs"]), g)
                     for i, g in enumerate(groups)) if cores_meta else "(none)"
    out.append("output-cone partition: %d group(s)   %s" % (len(groups), part))
    out.append("HEURISTIC (probe guess, NOT B2): %s"
               % _heuristic(len(cores_meta), groups, cores_meta))
    if show_devices:
        out.append("-- transistors (%sanonymized) --" % ("" if anon else "NOT "))
        for d in devs:
            t = d.terminals
            out.append("  %-6s %-4s d=%s g=%s s=%s b=%s"
                       % (d.name, d.kind, show(t["d"]), show(t["g"]),
                          show(t["s"]), show(t.get("b", "?"))))
    return ("\n".join(out), _heuristic(len(cores_meta), groups, cores_meta),
            _bucket(len(cores_meta), groups))


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
