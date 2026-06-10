"""
engine/run.py -- CLI entry point for the DeckGen v2 engine.

  python3 -m engine.run                              # fixture backend, placeholder arc
  python3 -m engine.run --config engine/config.real.json
  python3 -m engine.run --netlist /path/CELL.spi     # parse a real netlist directly
                                                     #   (S0/S1 need no arc; no rename)
  python3 -m engine.run --deck                        # also dump the assembled deck

Prints the compact stage trace then the P1/P2/P3 verdict block -- together they
fit on one screen (spec SS7.4).
"""
from __future__ import annotations

import argparse
import os

from engine.config import DEFAULT_CONFIG, ENGINE_DIR, load_config
from engine.dataaccess import FixtureBackend, make_data_access
from engine.pipeline import run_pipeline, run_pipeline_src
from engine.verdict import render, render_status


def parse_force_bias(items: list[str] | None) -> dict[str, int]:
    """Parse repeated --force-bias PIN=VAL items into {pin: 0|1}."""
    out: dict[str, int] = {}
    for item in items or []:
        pin, sep, val = item.partition("=")
        if not sep or not pin or val not in ("0", "1"):
            raise ValueError(f"--force-bias expects PIN=0 or PIN=1, got {item!r}")
        out[pin] = int(val)
    return out


def _direct(netlist_path: str, cell: str | None, constr="D", rel="CP", when="",
            arc_id: str | None = None, force_bias: dict | None = None):
    """Run on a netlist file directly. Used to validate on real data with no
    config/arc ceremony. S0/S1 use only the netlist; pass --when (or --arc-id) so
    Stage 2 can cross-check the derived bias against the arc's asserted condition."""
    with open(netlist_path, "r", encoding="ascii") as fh:
        src = fh.read()
    cell = cell or os.path.splitext(os.path.basename(netlist_path))[0]
    if arc_id:
        from engine.arc_id import parse_arc_id
        record = parse_arc_id(arc_id, cell)
    else:
        record = {
            "cell": cell, "arc_type": "hold", "rel_pin": rel, "rel_dir": "rise",
            "constr_pin": constr, "constr_dir": "fall", "when": when,
            "measurement": "(direct mode)",
        }
    if force_bias:
        record["force_bias"] = force_bias
    fx = FixtureBackend(os.path.join(ENGINE_DIR, "fixtures"))   # pass-through meas/model
    meas, model = fx.read_measurement_block(record), fx.read_model()
    return run_pipeline_src(record, src, meas, model,
                            "direct:" + os.path.basename(netlist_path))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DeckGen v2 core engine")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="config JSON (default: fixture)")
    ap.add_argument("--arc", default=None, help="arc id (overrides config 'arc')")
    ap.add_argument("--netlist", default=None, help="parse this netlist file directly (S0/S1)")
    ap.add_argument("--cell", default=None, help="cell name (default: netlist filename stem)")
    ap.add_argument("--when", default="", help="arc when-condition, e.g. notSE_SI (cross-check)")
    ap.add_argument("--constr-pin", default="D", help="constraint pin (direct mode, default D)")
    ap.add_argument("--rel-pin", default="CP", help="related/clock pin (direct mode, default CP)")
    ap.add_argument("--arc-id", default=None, help="full arc identifier (overrides when/pins)")
    ap.add_argument("--force-bias", action="append", default=None, metavar="PIN=VAL",
                    help="force a side-pin bias into the S2 derivation (repeatable); "
                         "demo: watch P1 catch a wrong bias")
    ap.add_argument("--sim", action="store_true", help="run hspice to evaluate P2 (real PASS/FAIL)")
    ap.add_argument("--hspice", default="hspice", help="hspice command (default: hspice)")
    ap.add_argument("--mt0", default=None, help="evaluate existing .mt0 (captured-D run) instead of running hspice")
    ap.add_argument("--mt0-inv", default=None, help="existing .mt0 for the inverted-D run (offline differential)")
    ap.add_argument("--simdir", default="/tmp/deckgen_p2", help="work dir for the P2 deck/run")
    ap.add_argument("--gen-p2-deck", default=None, metavar="PATH", help="just write the P2 deck and exit")
    ap.add_argument("--wave", default=None, metavar="PATH.svg", help="run P2 wave deck, render transient SVG (eog)")
    ap.add_argument("--tr0", default=None, help="render this existing CSDF .tr0 instead of running hspice")
    ap.add_argument("--viz", action="store_true", help="print the ASCII sensitization/init map")
    ap.add_argument("--topo", action="store_true", help="print parsed schematic + CCC channels")
    ap.add_argument("--topo-full", action="store_true", help="--topo plus the anonymous series nodes")
    ap.add_argument("--dot", default=None, metavar="PATH", help="write a Graphviz .dot of the topology")
    ap.add_argument("--svg", default=None, metavar="PATH", help="write a self-contained SVG (open in a browser)")
    ap.add_argument("--deck", action="store_true", help="also print the assembled deck")
    args = ap.parse_args(argv)

    try:
        force_bias = parse_force_bias(args.force_bias)
    except ValueError as e:
        ap.error(str(e))

    if args.netlist:
        result = _direct(args.netlist, args.cell, args.constr_pin, args.rel_pin,
                         args.when, args.arc_id, force_bias)
    else:
        config = load_config(args.config)
        da = make_data_access(config, base_dir=ENGINE_DIR)
        arc_id = args.arc or config["arc"]
        if force_bias:
            # Same four reads run_pipeline performs, with the override injected
            # into the record (pipeline itself stays untouched).
            record = da.read_arc(arc_id)
            record["force_bias"] = force_bias
            src = da.read_netlist(record["cell"])
            meas = da.read_measurement_block(record)
            model = da.read_model()
            result = run_pipeline_src(record, src, meas, model, da.name)
        else:
            result = run_pipeline(arc_id, da)

    if args.gen_p2_deck:
        from engine.p2_deck import build as build_p2
        text, _ = build_p2(result.arc, result.sens, result.init, result.init.probes)
        with open(args.gen_p2_deck, "w", encoding="ascii") as fh:
            fh.write(text)
        print(f"wrote {args.gen_p2_deck}  (run: hspice {args.gen_p2_deck})")
        return 0

    if args.wave or args.tr0:
        from engine.sim import run_wave
        out = args.wave or "p2_wave.svg"
        msg = run_wave(result.arc, result.sens, result.init, args.simdir, out,
                       hspice_cmd=args.hspice, tr0_path=args.tr0)
        print(msg)
        return 0

    if args.sim or args.mt0:
        from engine.sim import run_p2
        from engine.stages.stage5_verify import p2_property
        p2res = run_p2(result.arc, result.ccc, result.sens, result.init,
                       args.simdir, hspice_cmd=args.hspice,
                       mt0_path=args.mt0, mt0_inv_path=args.mt0_inv)
        result.verdict.p2 = p2_property(p2res)
        result.stage_log[-1] = (f"S5 verify   : P2 {'PASS' if p2res.passed else 'FAIL/n-a'} "
                                f"({'ran' if p2res.ran else p2res.note})")

    print(render_status(result))
    print(render(result))
    if args.topo or args.topo_full:
        from engine.topo_viz import render as render_topo
        print("\n" + render_topo(result.graph, result.ccc, result.arc,
                                 full=args.topo_full))
    if args.dot:
        from engine.draw import render_dot
        with open(args.dot, "w", encoding="ascii") as fh:
            fh.write(render_dot(result.graph, result.ccc, result.sens, result.arc))
        print(f"wrote {args.dot}  (render: dot -Tpng {args.dot} -o out.png)")
    if args.svg:
        from engine.draw import render_svg
        with open(args.svg, "w", encoding="ascii") as fh:
            fh.write(render_svg(result.graph, result.ccc, result.sens, result.arc))
        print(f"wrote {args.svg}  (open in a browser: firefox {args.svg})")
    if args.viz:
        from engine.viz import render as render_viz
        print("\n" + render_viz(result))
    if args.deck:
        print("\n--- assembled deck ---")
        print(result.deck.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
