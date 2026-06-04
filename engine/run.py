"""
engine/run.py -- CLI entry point for the DeckGen v2 skeleton.

  python3 -m engine.run                              # fixture backend, placeholder arc
  python3 -m engine.run --config engine/config.real.json
  python3 -m engine.run --arc hold_cp_d_placeholder
  python3 -m engine.run --deck                        # also dump the assembled deck

Prints the compact stage trace then the P1/P2/P3 verdict block -- together they
fit on one screen (spec SS7.4).
"""
from __future__ import annotations

import argparse

from engine.config import DEFAULT_CONFIG, ENGINE_DIR, load_config
from engine.dataaccess import make_data_access
from engine.pipeline import run_pipeline
from engine.verdict import render, render_status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DeckGen v2 core engine (SEGMENT 1 skeleton)")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="config JSON (default: fixture)")
    ap.add_argument("--arc", default=None, help="arc id (overrides config 'arc')")
    ap.add_argument("--deck", action="store_true", help="also print the assembled deck")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    da = make_data_access(config, base_dir=ENGINE_DIR)
    arc_id = args.arc or config["arc"]

    result = run_pipeline(arc_id, da)

    print(render_status(result))
    print(render(result))
    if args.deck:
        print("\n--- assembled deck ---")
        print(result.deck.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
