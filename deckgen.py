#!/usr/bin/env python3
"""
deckgen - Direct SPICE deck generator for library characterization.

Generate a SPICE simulation deck for a specific (cell, arc_type, PT) combination
without setting up the full MCQC flow.

Single-arc mode:
  python deckgen.py --cell DFFQ1 --arc_type hold \\
      --rel_pin CP --rel_dir rise --constr_pin D --constr_dir fall \\
      --probe_pin Q --slew 2.5n --rel_slew 1.2n --load 0.5f \\
      --vdd 0.45 --temp -40 \\
      --netlist /path/to/DFFQ1.spi \\
      --model /path/to/model.spi --waveform /path/to/wv.spi \\
      --output ./output/

Batch mode (N arcs x M corners):
  python deckgen.py \\
      --arcs_file arcs.txt \\
      --corners ssgnp_0p450v_m40c,ttgnp_0p800v_25c \\
      --netlist_dir /path/to/netlists/ \\
      --model /path/to/model.spi --waveform /path/to/wv.spi \\
      --template_tcl_dir /path/to/tcl/ \\
      --output ./output/
"""

import argparse
import os
import sys
import yaml

from core.resolver import resolve_all, ResolutionError
from core.deck_builder import build_deck, build_mc_deck
from core.writer import write_nominal_and_mc, write_deck, get_deck_dirname


def parse_args():
    p = argparse.ArgumentParser(
        description='Generate SPICE decks for specific cell/arc/PT combinations.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Arc specification (single-arc mode)
    p.add_argument('--cell', default=None, help='Cell name (e.g., DFFQ1, SYNC2)')
    p.add_argument('--arc_type', default=None, choices=['delay', 'slew', 'hold'],
                   help='Arc type')
    p.add_argument('--rel_pin', default=None, help='Related pin name (e.g., CP, A)')
    p.add_argument('--rel_dir', default=None, choices=['rise', 'fall'],
                   help='Related pin transition direction')
    p.add_argument('--constr_pin', default=None,
                   help='Constrained pin name (e.g., D). Required for hold.')
    p.add_argument('--constr_dir', default=None, choices=['rise', 'fall'],
                   help='Constrained pin direction')
    p.add_argument('--probe_pin', default=None,
                   help='Probe/output pin for measurement (e.g., Q, Y)')

    # Batch mode: arc input
    p.add_argument('--arcs_file', default=None,
                   help='File with one cell_arc_pt identifier per line (batch mode)')

    # Batch mode: corner input
    p.add_argument('--corners_file', default=None,
                   help='File with one corner name per line (batch mode)')
    p.add_argument('--corners', default=None,
                   help='Comma-separated corner names (e.g., ssgnp_0p450v_m40c,ttgnp_0p800v_25c)')

    # Batch mode: template.tcl auto-fill
    p.add_argument('--template_tcl_dir', default=None,
                   help='Directory with {corner}.template.tcl files for slew/load auto-fill')

    # Electrical parameters
    p.add_argument('--slew', default=None,
                   help='Constrained pin slew with units (e.g., 2.5n)')
    p.add_argument('--rel_slew', default=None,
                   help='Related pin slew. Defaults to --slew value.')
    p.add_argument('--load', default=None,
                   help='Output load with units (e.g., 0.5f)')
    p.add_argument('--max_slew', default=None,
                   help='Max slew for timing window (e.g., 2.5n)')

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


def _is_batch_mode(args):
    """Return True when batch flags indicate batch mode."""
    return bool(args.arcs_file or args.corners or args.corners_file)


def main():
    args = parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    if _is_batch_mode(args):
        _run_batch(args, script_dir)
    else:
        _run_single(args, script_dir)


# ---------------------------------------------------------------------------
# Single-arc mode
# ---------------------------------------------------------------------------

def _run_single(args, script_dir):
    # Validate required single-arc args
    missing = [f for f, v in [('--cell', args.cell), ('--arc_type', args.arc_type),
                               ('--rel_pin', args.rel_pin), ('--rel_dir', args.rel_dir)]
               if not v]
    if missing:
        print(f"ERROR: {', '.join(missing)} required in single-arc mode. "
              f"Use --arcs_file for batch mode.", file=sys.stderr)
        sys.exit(1)

    # Load global config if available
    config_path = args.config or os.path.join(script_dir, 'config', 'config.yaml')
    global_config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            global_config = yaml.safe_load(f) or {}

    registry_rel = global_config.get('template_registry', 'template_registry.yaml')
    registry_path = os.path.join(script_dir, 'config', registry_rel)
    templates_dir = os.path.join(script_dir, 'templates')

    if args.arc_type == 'hold' and not args.constr_pin:
        print("ERROR: --constr_pin is required for hold arcs.", file=sys.stderr)
        sys.exit(1)

    cli_overrides = {
        'vdd': args.vdd,
        'temperature': args.temp,
        'model_file': args.model,
        'waveform_file': args.waveform,
        'netlist_dir': args.netlist_dir,
        'pushout_per': global_config.get('pushout_per', '0.4'),
        'num_samples': args.num_samples,
    }

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

    constr_slew = args.slew or '0'
    rel_slew = args.rel_slew or args.slew or '0'
    max_slew = args.max_slew or _max_slew_value(constr_slew, rel_slew)

    nominal_lines = build_deck(
        arc_info=arc_info,
        global_config=global_config,
        slew=(constr_slew, rel_slew),
        load=args.load or '0',
        when=args.when,
        max_slew=max_slew,
    )

    if args.nominal_only:
        dirname = get_deck_dirname(arc_info, args.when)
        out_path = os.path.join(args.output, dirname, 'nominal_sim.sp')
        write_deck(nominal_lines, out_path)
        print(f"Nominal deck: {out_path}")
    else:
        mc_lines = build_mc_deck(nominal_lines, args.num_samples)
        nominal_path, mc_path = write_nominal_and_mc(
            nominal_lines, mc_lines, args.output, arc_info, args.when
        )
        print(f"Nominal deck: {nominal_path}")
        print(f"MC deck:      {mc_path}")

    print(f"\nDeck generated for: {args.cell} / {args.arc_type} / "
          f"{args.rel_pin}({args.rel_dir})->{args.constr_pin or ''}({args.constr_dir or ''})")


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------

def _run_batch(args, script_dir):
    from core.batch import run_batch
    from core.parsers.arc import parse_arc_list
    from core.parsers.corner import parse_corner_list

    # Collect arc identifiers
    arc_ids = []
    if args.arcs_file:
        if not os.path.exists(args.arcs_file):
            print(f"ERROR: arcs file not found: {args.arcs_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.arcs_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    arc_ids.append(line)
    elif args.cell and args.arc_type and args.rel_pin and args.rel_dir:
        # Single arc specified via flags but batch corners given
        # Build a synthetic identifier (best-effort)
        arc_ids.append(
            f"{args.arc_type}_{args.cell}_{args.probe_pin or 'Q'}_rise"
            f"_{args.rel_pin}_{args.rel_dir}_NO_CONDITION_1_1"
        )

    if not arc_ids:
        print("ERROR: No arc identifiers found. "
              "Provide --arcs_file or single-arc flags.", file=sys.stderr)
        sys.exit(1)

    # Collect corner names
    corner_names = []
    if args.corners_file:
        if not os.path.exists(args.corners_file):
            print(f"ERROR: corners file not found: {args.corners_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.corners_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    corner_names.append(line)
    if args.corners:
        for name in args.corners.split(','):
            name = name.strip()
            if name:
                corner_names.append(name)

    if not corner_names:
        print("ERROR: No corners specified. Use --corners or --corners_file.",
              file=sys.stderr)
        sys.exit(1)

    files = {
        'netlist_dir': args.netlist_dir or '',
        'netlist': args.netlist or '',
        'model': args.model or '',
        'waveform': args.waveform or '',
        'template_tcl_dir': args.template_tcl_dir or '',
    }
    overrides = {}
    if args.vdd:
        overrides['vdd'] = args.vdd
    if args.temp:
        overrides['temperature'] = args.temp
    if args.slew:
        overrides['slew'] = args.slew
    if args.load:
        overrides['load'] = args.load
    if args.max_slew:
        overrides['max_slew'] = args.max_slew
    if args.constr_pin:
        overrides['constr_pin'] = args.constr_pin
    if args.constr_dir:
        overrides['constr_dir'] = args.constr_dir

    print(f"Batch: {len(arc_ids)} arc(s) x {len(corner_names)} corner(s) "
          f"= {len(arc_ids) * len(corner_names)} job(s)")

    jobs, results, errors = run_batch(
        arc_ids=arc_ids,
        corner_names=corner_names,
        files=files,
        overrides=overrides,
        output_dir=args.output,
        nominal_only=args.nominal_only,
        num_samples=args.num_samples,
    )

    # Report fatal parse errors
    for err in errors:
        print(f"  ERROR: {err}", file=sys.stderr)

    # Report per-job results
    ok = sum(1 for r in results if r['success'])
    fail = len(results) - ok
    print(f"\nResults: {ok} succeeded, {fail} failed")
    for r in results:
        job = next((j for j in jobs if j['id'] == r['id']), {})
        label = f"  [{r['id']:3d}] {job.get('cell', '?')} / {job.get('corner', '?')}"
        if r['success']:
            print(f"{label}  ->  {r['nominal']}")
        else:
            print(f"{label}  FAILED: {r['error']}", file=sys.stderr)

    if fail:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _max_slew_value(s1, s2):
    """Return the larger of two slew strings (with units)."""
    def to_float(s):
        if not s or s == '0':
            return 0.0
        s = s.strip()
        multipliers = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
        if s[-1] in multipliers:
            return float(s[:-1]) * multipliers[s[-1]]
        return float(s)

    try:
        return s1 if to_float(s1) >= to_float(s2) else s2
    except (ValueError, IndexError):
        return s1 or s2


# Keep old name as alias so any existing callers don't break
max_slew_value = _max_slew_value


if __name__ == '__main__':
    main()
