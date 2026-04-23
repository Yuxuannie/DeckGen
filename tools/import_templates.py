#!/usr/bin/env python3
"""
import_templates.py - Import SCLD templates into DeckGen's node-organized structure.

SCLD delivers templates as a flat directory with arc-type subfolders:
  source_dir/
    hold/     template__CP__rise__fall__1.sp  ...
    delay/    template__invdX__fall.sp  ...
    mpw/      template__CP__rise__fall__1.sp  ...

This utility copies them into DeckGen's node-organized structure:
  templates/{node}/hold/   template__CP__rise__fall__1.sp  ...
  templates/{node}/delay/  template__invdX__fall.sp  ...
  templates/{node}/mpw/    template__CP__rise__fall__1.sp  ...

Usage:
  python3 tools/import_templates.py \\
      --source /path/to/scld/templates \\
      --node N2

  python3 tools/import_templates.py \\
      --source /path/to/scld/templates \\
      --node N2P_v1.0 \\
      --arc_types hold delay mpw   # only copy these subtypes (default: all found)

  python3 tools/import_templates.py \\
      --source /path/to/scld/templates \\
      --node N2 \\
      --dry_run               # print what would be copied without doing it

Non-ASCII check is run automatically after import.
"""

import argparse
import os
import shutil
import sys


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DECKGEN_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '..'))
_TEMPLATES_DIR = os.path.join(_DECKGEN_ROOT, 'templates')

# Arc-type subfolders recognized from SCLD deliveries
KNOWN_ARC_TYPES = ('hold', 'delay', 'slew', 'setup', 'removal', 'recovery', 'mpw',
                   'min_pulse_width')

# Canonical name mapping (SCLD sometimes uses 'min_pulse_width', DeckGen uses 'mpw')
ARC_TYPE_ALIASES = {
    'min_pulse_width': 'mpw',
}


def parse_args():
    p = argparse.ArgumentParser(
        description='Import SCLD templates into DeckGen node-organized structure.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('--source', required=True,
                   help='Path to SCLD template delivery directory '
                        '(contains hold/, delay/, mpw/ subdirs)')
    p.add_argument('--node', required=True,
                   help='Process node identifier (e.g. N2, N2P_v1.0, A14)')
    p.add_argument('--arc_types', nargs='+', default=None,
                   help='Limit to these arc types (default: all found)')
    p.add_argument('--dry_run', action='store_true',
                   help='Print what would be copied without writing files')
    p.add_argument('--overwrite', action='store_true',
                   help='Overwrite existing files (default: skip existing)')
    return p.parse_args()


def check_non_ascii(path):
    """Return list of (filename, byte_offset) tuples for non-ASCII bytes found."""
    violations = []
    for root, _, files in os.walk(path):
        for fname in files:
            if not fname.endswith('.sp'):
                continue
            fpath = os.path.join(root, fname)
            data = open(fpath, 'rb').read()
            for i, b in enumerate(data):
                if b > 127:
                    violations.append((fpath, i, b))
                    break  # one violation per file is enough
    return violations


def main():
    args = parse_args()

    if not os.path.isdir(args.source):
        print(f"ERROR: source directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    # Discover arc-type subdirectories in source
    found_arc_types = [
        d for d in os.listdir(args.source)
        if os.path.isdir(os.path.join(args.source, d))
    ]

    if args.arc_types:
        arc_types_to_copy = [a for a in found_arc_types if a in args.arc_types]
        missing = [a for a in args.arc_types if a not in found_arc_types]
        if missing:
            print(f"WARNING: requested arc types not found in source: {missing}",
                  file=sys.stderr)
    else:
        arc_types_to_copy = [a for a in found_arc_types if a in KNOWN_ARC_TYPES]
        unknown = [a for a in found_arc_types if a not in KNOWN_ARC_TYPES]
        if unknown:
            print(f"INFO: skipping unrecognized subdirectories: {unknown}")

    if not arc_types_to_copy:
        print("ERROR: no recognized arc-type subdirectories found in source.",
              file=sys.stderr)
        print(f"  Expected one or more of: {', '.join(KNOWN_ARC_TYPES)}", file=sys.stderr)
        print(f"  Found: {found_arc_types}", file=sys.stderr)
        sys.exit(1)

    total_copied = 0
    total_skipped = 0
    total_errors = 0

    for src_arc_type in arc_types_to_copy:
        # Apply canonical name alias (min_pulse_width -> mpw)
        dest_arc_type = ARC_TYPE_ALIASES.get(src_arc_type, src_arc_type)

        src_dir = os.path.join(args.source, src_arc_type)
        dest_dir = os.path.join(_TEMPLATES_DIR, args.node, dest_arc_type)

        template_files = [
            f for f in os.listdir(src_dir)
            if f.endswith(('.sp', '.spi', '.spice'))
        ]

        if not template_files:
            print(f"  [{src_arc_type}] no .sp files found -- skipping")
            continue

        if not args.dry_run:
            os.makedirs(dest_dir, exist_ok=True)

        print(f"  [{src_arc_type}] -> templates/{args.node}/{dest_arc_type}/"
              f"  ({len(template_files)} files)")

        for fname in sorted(template_files):
            src_path = os.path.join(src_dir, fname)
            dest_path = os.path.join(dest_dir, fname)

            if os.path.exists(dest_path) and not args.overwrite and not args.dry_run:
                total_skipped += 1
                continue

            if args.dry_run:
                print(f"    [DRY] {fname}")
                total_copied += 1
                continue

            try:
                shutil.copy2(src_path, dest_path)
                total_copied += 1
            except OSError as e:
                print(f"    ERROR copying {fname}: {e}", file=sys.stderr)
                total_errors += 1

    if args.dry_run:
        print(f"\nDry run: would copy {total_copied} file(s)")
        return

    print(f"\nImport complete: {total_copied} copied, "
          f"{total_skipped} skipped (already exist), "
          f"{total_errors} errors")

    if total_errors:
        sys.exit(1)

    # Non-ASCII check on newly imported node templates
    node_dest = os.path.join(_TEMPLATES_DIR, args.node)
    violations = check_non_ascii(node_dest)
    if violations:
        print(f"\nWARNING: {len(violations)} file(s) contain non-ASCII bytes:", file=sys.stderr)
        for path, offset, byte in violations:
            rel = os.path.relpath(path, _DECKGEN_ROOT)
            print(f"  {rel}  offset={offset}  byte=0x{byte:02x}", file=sys.stderr)
        print("  Run: grep -rn '.' on those files to find the characters.",
              file=sys.stderr)
        sys.exit(1)
    else:
        print("Non-ASCII check: OK")


if __name__ == '__main__':
    main()
