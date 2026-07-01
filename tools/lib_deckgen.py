#!/usr/bin/env python3
"""lib_deckgen.py -- whole-library deck-generation PROTOTYPE (B2/B3 demo).

For every netlist in a directory it runs the DeckGen v2 engine end-to-end
(stage0..stage5, including the B2 structural sequential classifier and the B3
"precycle from structural depth" wiring), and for each SEQUENTIAL cell it writes
an assembled SPICE deck plus a one-line structural summary. Combinational and
recognized_unsupported cells are reported with a reason (never silently
dropped); no deck is written for them.

This is a hands-on prototype: it runs on the in-repo fixtures with NO PDK /
collateral, using the fixture measurement+model pass-through. The decks it emits
have placeholder COLLATERAL lines (see stage4) but real ENGINE-DERIVED content:
the P1 biases, the drive-and-settle init, and -- new in B3 -- a precycle count
that equals the cell's structural depth (latch 0, DFF 1, sync-N N, multibit =
deepest bit).

USAGE (from the repo root, or set PYTHONPATH to it):
  # sweep the bundled engine fixtures, write decks under ./proto_out/
  python3 tools/lib_deckgen.py --dir engine/fixtures --out proto_out

  # a single netlist
  python3 tools/lib_deckgen.py --netlist engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt

  # summary only, write nothing
  python3 tools/lib_deckgen.py --dir engine/fixtures --dry-run

  # override the direct-mode arc pins (default hold arc: CP rise / D fall)
  python3 tools/lib_deckgen.py --dir path/to/lib --rel CP --constr D --when notSE_SI

stdlib + engine only. ASCII only. Read-only except for the decks it writes.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from engine.run import _direct                                # noqa: E402
from engine.stages.stage1b_classify import classify           # noqa: E402
from engine.types import PStatus                              # noqa: E402
from core.deck_assemble import assemble_sequential            # noqa: E402
from core.measurement.emit import load_grammar                # noqa: E402

_SEQUENTIAL = {"latch", "ff_chain", "multibit"}


def _depth(seq):
    if seq.verdict == "ff_chain":
        return seq.bits[0].ff_depth
    if seq.verdict == "multibit":
        return max(b.ff_depth for b in seq.bits)
    return 0


def _cell_from_file(path, strip_suffix="_c"):
    stem = os.path.splitext(os.path.basename(path))[0]
    if strip_suffix and stem.endswith(strip_suffix):
        stem = stem[: -len(strip_suffix)]
    return stem


def process(path, cell, out_dir, constr, rel, when, dry_run, arc_type, grammar):
    """Run one netlist through the engine; write its deck if sequential.
    Returns a (cell, verdict, summary_line) tuple. Never raises."""
    try:
        res = _direct(path, cell, constr=constr, rel=rel, when=when)
        seq = classify(res.graph, cell)
        depth = _depth(seq)
        precycle = res.init.precycle_count.value
        p1 = res.verdict.p1.status.value
        base = ("%-28s class=%-22s depth=%d precycle=%d P1=%-4s"
                % (cell, seq.verdict, depth, precycle, p1))
        if seq.divergence:
            base += "  [name-div: %s]" % seq.divergence

        if seq.verdict in _SEQUENTIAL:
            if dry_run:
                return (cell, seq.verdict, base + "  deck=(dry-run)")
            arc_info = {
                "CELL_NAME": cell, "ARC_TYPE": arc_type,
                "REL_PIN": rel, "REL_PIN_DIR": "fall" if arc_type == "hold" else "rise",
                "CONSTR_PIN": constr, "CONSTR_PIN_DIR": "fall", "PROBE_PIN_1": "Q",
                "WHEN": when or "NO_CONDITION",
                "WAVEFORM_FILE": "std_wv.spi", "INCLUDE_FILE": "MODEL.%s.inc" % arc_type,
                "NETLIST_PATH": "%s.spi" % cell, "VDD_VALUE": "0.450",
                "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2e-10",
                "INDEX_2_VALUE": "5e-16", "MAX_SLEW": "1e-9", "OUTPUT_LOAD": "5e-16",
            }
            asm = assemble_sequential(arc_info, open(path, encoding="ascii").read(),
                                      grammar)
            if asm["status"] != "OK":
                return (cell, seq.verdict, base + "  NO DECK (%s)" % asm["error"])
            os.makedirs(out_dir, exist_ok=True)
            deck_path = os.path.join(out_dir, "%s.sp" % cell)
            with open(deck_path, "w", encoding="ascii") as fh:
                fh.write(asm["deck_text"])
            return (cell, seq.verdict,
                    base + "  deck=%s [%s/%s]" % (deck_path, asm["family"], asm["cluster_tag"]))

        # combinational / recognized_unsupported: reported, no deck emitted.
        reason = res.init.precycle_count.reason if seq.verdict != "combinational" \
            else "no storage core -- combinational cell, not a sequential arc"
        return (cell, seq.verdict, base + "  SKIP (%s)" % (seq.reason or reason))
    except Exception as e:                        # a bad cell is named, never crashes the sweep
        return (cell, "ERROR", "%-28s ENGINE ERROR: %s" % (cell, e))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Whole-library deck-generation prototype.")
    ap.add_argument("--dir", help="sweep every .spi/.subckt netlist in this directory")
    ap.add_argument("--netlist", help="a single netlist file")
    ap.add_argument("--out", default="proto_out", help="deck output dir (default: proto_out)")
    ap.add_argument("--dry-run", action="store_true", help="summarize only; write no decks")
    ap.add_argument("--rel", default="CP", help="related/clock pin (default CP)")
    ap.add_argument("--constr", default="D", help="constraint pin (default D)")
    ap.add_argument("--when", default="", help="arc when-condition, e.g. notSE_SI")
    ap.add_argument("--arc-type", default="hold", choices=["hold", "mpw"],
                    help="sequential deck family (default hold)")
    ap.add_argument("--strip-suffix", default="_c", help="filename suffix stripped for cell name")
    args = ap.parse_args(argv)

    if args.netlist:
        paths = [args.netlist]
    elif args.dir:
        paths = sorted(glob.glob(os.path.join(args.dir, "*.spi"))
                       + glob.glob(os.path.join(args.dir, "*.subckt")))
        if not paths:
            print("no .spi/.subckt netlists in %s" % args.dir)
            return 1
    else:
        ap.error("give --netlist FILE or --dir DIR")

    grammar = load_grammar()
    rows = []
    for p in paths:
        cell = _cell_from_file(p, args.strip_suffix)
        rows.append(process(p, cell, args.out, args.constr, args.rel,
                            args.when, args.dry_run, args.arc_type, grammar))

    print("===== DECK GENERATION (%d cell(s)) =====" % len(rows))
    for _, _, line in rows:
        print("  " + line)

    hist = {}
    for _, verdict, _ in rows:
        hist[verdict] = hist.get(verdict, 0) + 1
    print("\n===== VERDICT HISTOGRAM =====")
    for verdict in sorted(hist, key=lambda v: (-hist[v], v)):
        tag = "deck emitted" if verdict in _SEQUENTIAL else "no deck"
        print("  %5d  %-24s (%s)" % (hist[verdict], verdict, tag))
    generated = sum(n for v, n in hist.items() if v in _SEQUENTIAL)
    if not args.dry_run and generated:
        print("\n%d deck(s) written under %s/" % (generated, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
