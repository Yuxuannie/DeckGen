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


def _direct(netlist_path: str, cell: str | None):
    """Run on a netlist file directly. Used to validate S0/S1 on real data with
    no config/arc ceremony -- S0/S1 use only the netlist; the arc is synthetic."""
    with open(netlist_path, "r", encoding="ascii") as fh:
        src = fh.read()
    cell = cell or os.path.splitext(os.path.basename(netlist_path))[0]
    record = {
        "cell": cell, "arc_type": "hold", "rel_pin": "CP", "rel_dir": "rise",
        "constr_pin": "D", "constr_dir": "fall", "when": "",
        "measurement": "(direct mode -- synthetic arc; S0/S1 do not use it)",
    }
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
    ap.add_argument("--deck", action="store_true", help="also print the assembled deck")
    args = ap.parse_args(argv)

    if args.netlist:
        result = _direct(args.netlist, args.cell)
    else:
        config = load_config(args.config)
        da = make_data_access(config, base_dir=ENGINE_DIR)
        result = run_pipeline(args.arc or config["arc"], da)

    print(render_status(result))
    print(render(result))
    if args.deck:
        print("\n--- assembled deck ---")
        print(result.deck.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
