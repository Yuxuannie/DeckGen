#!/usr/bin/env python3
"""
deckgen - Direct SPICE deck generator for library characterization.

Generate a SPICE simulation deck for a specific (cell, arc_type, PT) combination
without setting up the full MCQC flow.

Supports: delay, slew, hold arc types.

Usage examples:

  # Hold deck with corner config
  python deckgen.py --cell DFFQ1 --arc_type hold \\
      --rel_pin CP --rel_dir rise --constr_pin D --constr_dir fall \\
      --probe_pin Q --slew 2.5n --rel_slew 1.2n --load 0.5f \\
      --corner_config corners/ss_0p45v_m40c.yaml \\
      --output ./output/

  # Delay deck with explicit parameters
  python deckgen.py --cell INV1 --arc_type delay \\
      --rel_pin A --rel_dir fall --probe_pin Y \\
      --vdd 0.45 --temp -40 --slew 0.5n --load 0.5f \\
      --netlist /path/to/INV1.spi \\
      --model /path/to/model.spi --waveform /path/to/wv.spi \\
      --output ./output/

  # Use a custom template directly (bypass registry)
  python deckgen.py --cell MYSYNC --arc_type hold \\
      --template /path/to/my_template.sp \\
      ...
"""

import argparse
import os
import sys
import yaml

from resolver import resolve_all, ResolutionError
from deck_builder import build_deck, build_mc_deck
from writer import write_nominal_and_mc


def parse_args():
    p = argparse.ArgumentParser(
        description='Generate SPICE decks for specific cell/arc/PT combinations.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Required: arc specification
    p.add_argument('--cell', required=True, help='Cell name (e.g., DFFQ1, SYNC2)')
    p.add_argument('--arc_type', required=True, choices=['delay', 'slew', 'hold'],
                   help='Arc type')
    p.add_argument('--rel_pin', required=True, help='Related pin name (e.g., CP, A)')
    p.add_argument('--rel_dir', required=True, choices=['rise', 'fall'],
                   help='Related pin transition direction')
    p.add_argument('--constr_pin', default=None,
                   help='Constrained pin name (e.g., D). Required for hold.')
    p.add_argument('--constr_dir', default=None, choices=['rise', 'fall'],
                   help='Constrained pin direction')
    p.add_argument('--probe_pin', default=None,
                   help='Probe/output pin for measurement (e.g., Q, Y)')

    # Electrical parameters
    p.add_argument('--slew', default=None,
                   help='Constrained pin slew with units (e.g., 2.5n)')
    p.add_argument('--rel_slew', default=None,
                   help='Related pin slew with units (e.g., 1.2n). Defaults to --slew value.')
    p.add_argument('--load', default=None,
                   help='Output load with units (e.g., 0.5f)')
    p.add_argument('--max_slew', default=None,
                   help='Max slew for timing window (e.g., 2.5n). Defaults to max of slew values.')

    # PVT corner
    p.add_argument('--vdd', default=None, help='Supply voltage (e.g., 0.45)')
    p.add_argument('--temp', default=None, help='Temperature (e.g., -40)')
    p.add_argument('--corner_config', default=None,
                   help='Path to corner YAML config file')

    # File paths
    p.add_argument('--netlist', default=None, help='Direct path to cell netlist (.spi)')
    p.add_argument('--netlist_dir', default=None,
                   help='Directory containing cell netlists')
    p.add_argument('--pins', default=None,
                   help='Pin list string (e.g., "VDD VSS A Y"). '
                        'Auto-extracted from netlist if not provided.')
    p.add_argument('--model', default=None, help='Path to model/process include file')
    p.add_argument('--waveform', default=None, help='Path to waveform definitions file')
    p.add_argument('--template', default=None,
                   help='Direct path to SPICE template (bypasses registry)')

    # When condition
    p.add_argument('--when', default='NO_CONDITION',
                   help='When condition (e.g., "!SE&SI"). Default: NO_CONDITION')

    # Simulation
    p.add_argument('--num_samples', type=int, default=5000,
                   help='Monte Carlo samples (default: 5000)')
    p.add_argument('--nominal_only', action='store_true',
                   help='Generate only the nominal deck (skip MC)')

    # Config and output
    p.add_argument('--config', default=None,
                   help='Path to global config.yaml')
    p.add_argument('--output', default='./output',
                   help='Output directory (default: ./output)')

    return p.parse_args()


def main():
    args = parse_args()

    # Locate config files relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Load global config if available
    config_path = args.config or os.path.join(script_dir, 'config.yaml')
    global_config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            global_config = yaml.safe_load(f) or {}

    # Registry and templates directories
    registry_path = os.path.join(
        script_dir,
        global_config.get('template_registry', 'template_registry.yaml')
    )
    templates_dir = os.path.join(script_dir, 'templates')

    # Validate arc_type-specific requirements
    if args.arc_type == 'hold' and not args.constr_pin:
        print("ERROR: --constr_pin is required for hold arcs.", file=sys.stderr)
        sys.exit(1)

    # Build CLI overrides for corner resolution
    cli_overrides = {
        'vdd': args.vdd,
        'temperature': args.temp,
        'model_file': args.model,
        'waveform_file': args.waveform,
        'netlist_dir': args.netlist_dir,
        'pushout_per': global_config.get('pushout_per', '0.4'),
        'num_samples': args.num_samples,
    }

    # Resolve all parameters
    try:
        arc_info = resolve_all(
            cell_name=args.cell,
            arc_type=args.arc_type,
            rel_pin=args.rel_pin,
            rel_dir=args.rel_dir,
            constr_pin=args.constr_pin or args.rel_pin,
            constr_dir=args.constr_dir,
            probe_pin=args.probe_pin,
            registry_path=registry_path,
            templates_dir=templates_dir,
            netlist_dir=args.netlist_dir or global_config.get('netlist_dir'),
            corner_config=args.corner_config,
            cli_overrides=cli_overrides,
            template_override=args.template,
            netlist_override=args.netlist,
            pins_override=args.pins,
        )
    except ResolutionError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)

    # Compute slew values
    constr_slew = args.slew or '0'
    rel_slew = args.rel_slew or args.slew or '0'
    max_slew = args.max_slew or max_slew_value(constr_slew, rel_slew)

    # Build nominal deck
    nominal_lines = build_deck(
        arc_info=arc_info,
        global_config=global_config,
        slew=(constr_slew, rel_slew),
        load=args.load or '0',
        when=args.when,
        max_slew=max_slew,
    )

    # Build MC deck
    mc_lines = None
    if not args.nominal_only:
        mc_lines = build_mc_deck(nominal_lines, args.num_samples)

    # Write output
    if mc_lines:
        nominal_path, mc_path = write_nominal_and_mc(
            nominal_lines, mc_lines, args.output, arc_info, args.when
        )
        print(f"Nominal deck: {nominal_path}")
        print(f"MC deck:      {mc_path}")
    else:
        from writer import get_deck_dirname, write_deck
        dirname = get_deck_dirname(arc_info, args.when)
        out_path = os.path.join(args.output, dirname, 'nominal_sim.sp')
        write_deck(nominal_lines, out_path)
        print(f"Nominal deck: {out_path}")

    print(f"\nDeck generated for: {args.cell} / {args.arc_type} / "
          f"{args.rel_pin}({args.rel_dir})->{args.constr_pin or ''}({args.constr_dir or ''})")


def max_slew_value(s1, s2):
    """Return the larger of two slew strings (with units) as a string."""
    def to_float(s):
        if not s or s == '0':
            return 0.0
        # Strip common unit suffixes for comparison
        s = s.strip()
        multipliers = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
        if s[-1] in multipliers:
            return float(s[:-1]) * multipliers[s[-1]]
        return float(s)

    try:
        v1 = to_float(s1)
        v2 = to_float(s2)
        return s1 if v1 >= v2 else s2
    except (ValueError, IndexError):
        return s1 or s2


if __name__ == '__main__':
    main()
