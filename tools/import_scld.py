#!/usr/bin/env python3
"""import_scld.py - Reorganize SCLD lib delivery into DeckGen collateral layout.

SCLD ships each library as:

    <lib_root>/                                e.g. tcbn02p_bwph130nppnl3p48cpd_base_elvt_c221227_400i/
      Char/
        <lib>_<corner>.inc
        <lib>_<corner>.delay.inc
        <lib>_<corner>.hold.inc
        <lib>_<corner>.usage.l
        char_<lib>.cons.tcl                    (lib-global -- no corner in name)
        char_<lib>.non_cons.tcl                (lib-global -- no corner in name)
        <something>.template.tcl               (template files mixed in here)
        Netlist/
          LPE_<rc>_<temp>/
            <CELL>_c.spi
        ... other unrelated files ignored ...
      LVF/                                     (ignored)

DeckGen target:

    collateral/<node>/<lib_type>/
      Char/                                    <- SCLD .inc, .usage.l, char_*.tcl files
      Template/                                <- SCLD *.template.tcl files
      Netlist/                                 <- SCLD LPE_* dirs

The lib_type DeckGen uses is the basename of <lib_root>.

Usage:

    # One library:
    python3 tools/import_scld.py --node N2P_v1.0 \\
        --src /path/to/tcbn02p_bwph130nppnl3p48cpd_base_elvt_c221227_400i

    # All libraries under a parent dir:
    python3 tools/import_scld.py --node N2P_v1.0 \\
        --src-parent /path/to/scld_libs_root

    # Symlink instead of copy (saves disk; fast):
    python3 tools/import_scld.py --node N2P_v1.0 \\
        --src-parent /path/to/scld_libs_root --link

    # Dry-run (preview, no writes):
    python3 tools/import_scld.py --node N2P_v1.0 \\
        --src-parent /path/to/scld_libs_root --dry-run

After import, run scan_collateral.py to generate manifests.
"""

import argparse
import os
import shutil
import sys


# Files we want from SCLD's Char/ folder (lowercase suffix match).
WANTED_CHAR_SUFFIXES = (
    '.inc',          # base + .delay.inc / .hold.inc / .setup.inc / .mpw.inc all match
    '.usage.l',
    '.tcl',          # captures char_*.cons.tcl, .non_cons.tcl, template.tcl, plain char_*.tcl
)

# Always skip these (shell scripts, build/run helpers, logs, etc).
# Checked before WANTED_CHAR_SUFFIXES so we never accidentally include them.
DENY_SUFFIXES = (
    '.sh',
    '.csh',
    '.bash',
    '.zsh',
    '.py',
    '.pl',
    '.log',
    '.txt',
    '.md',
    '.json',
    '.yaml',
    '.yml',
)

# .tcl files containing this token go to Template/, otherwise Char/.
TEMPLATE_TCL_TOKEN = 'template.tcl'


def import_one_lib(src_lib, deckgen_root, node, link=False, dry_run=False,
                    verbose=True):
    """Import one SCLD lib folder into DeckGen collateral.

    Args:
        src_lib:        absolute path to one SCLD library directory
        deckgen_root:   path to DeckGen repo root (parent of collateral/)
        node:           DeckGen node name (e.g. 'N2P_v1.0')
        link:           if True, create symlinks instead of copying
        dry_run:        if True, only print actions
        verbose:        if True, print per-file progress

    Returns:
        dict with counts: {char_files, template_files, netlist_dirs, skipped, errors}
    """
    if not os.path.isdir(src_lib):
        print(f"ERROR: source lib not found: {src_lib}", file=sys.stderr)
        return {'errors': 1, 'char_files': 0, 'template_files': 0,
                'netlist_dirs': 0, 'skipped': 0}

    lib_type = os.path.basename(os.path.normpath(src_lib))
    src_char = os.path.join(src_lib, 'Char')
    src_netlist = os.path.join(src_char, 'Netlist')

    if not os.path.isdir(src_char):
        print(f"ERROR: {src_lib}/Char/ not found", file=sys.stderr)
        return {'errors': 1, 'char_files': 0, 'template_files': 0,
                'netlist_dirs': 0, 'skipped': 0}

    dst_root = os.path.join(deckgen_root, 'collateral', node, lib_type)
    dst_char = os.path.join(dst_root, 'Char')
    dst_template = os.path.join(dst_root, 'Template')
    dst_netlist = os.path.join(dst_root, 'Netlist')

    if not dry_run:
        os.makedirs(dst_char, exist_ok=True)
        os.makedirs(dst_template, exist_ok=True)
        os.makedirs(dst_netlist, exist_ok=True)

    counts = {'char_files': 0, 'template_files': 0,
              'netlist_dirs': 0, 'skipped': 0, 'errors': 0}

    # ----- Char/ + Template/ files (top-level of SCLD's Char/) -----
    for fname in sorted(os.listdir(src_char)):
        src = os.path.join(src_char, fname)
        if os.path.isdir(src):
            continue                                 # Netlist/ etc. handled below
        lower = fname.lower()
        # Explicit denylist first -- shell scripts, logs, etc.
        if lower.endswith(DENY_SUFFIXES):
            counts['skipped'] += 1
            if verbose:
                print(f"  skip      {fname}  (denied extension)")
            continue
        if not lower.endswith(WANTED_CHAR_SUFFIXES):
            counts['skipped'] += 1
            continue

        # Decide destination based on filename
        if TEMPLATE_TCL_TOKEN in lower:
            dst = os.path.join(dst_template, fname)
            kind = 'template'
        else:
            dst = os.path.join(dst_char, fname)
            kind = 'char'

        if dry_run:
            if verbose:
                print(f"  [DRY] {kind:8s}  {src} -> {dst}")
        else:
            try:
                if os.path.exists(dst) or os.path.islink(dst):
                    os.remove(dst)
                if link:
                    os.symlink(os.path.abspath(src), dst)
                else:
                    shutil.copy2(src, dst)
                if verbose:
                    print(f"  {kind:8s}  {fname}")
            except OSError as e:
                print(f"  ERROR copying {fname}: {e}", file=sys.stderr)
                counts['errors'] += 1
                continue

        if kind == 'template':
            counts['template_files'] += 1
        else:
            counts['char_files'] += 1

    # ----- Netlist subdirs (LPE_*) -----
    if os.path.isdir(src_netlist):
        for sub in sorted(os.listdir(src_netlist)):
            srcd = os.path.join(src_netlist, sub)
            if not os.path.isdir(srcd):
                counts['skipped'] += 1
                continue
            dstd = os.path.join(dst_netlist, sub)

            if dry_run:
                if verbose:
                    print(f"  [DRY] netlist  {srcd} -> {dstd}")
                counts['netlist_dirs'] += 1
                continue

            try:
                if os.path.lexists(dstd):
                    if os.path.islink(dstd) or os.path.isfile(dstd):
                        os.remove(dstd)
                    else:
                        shutil.rmtree(dstd)
                if link:
                    os.symlink(os.path.abspath(srcd), dstd)
                else:
                    shutil.copytree(srcd, dstd)
                counts['netlist_dirs'] += 1
                if verbose:
                    print(f"  netlist   {sub}/")
            except OSError as e:
                print(f"  ERROR copying {sub}: {e}", file=sys.stderr)
                counts['errors'] += 1
    else:
        print(f"  WARN: no Netlist/ dir under {src_char}", file=sys.stderr)

    return counts


def _looks_like_scld_lib(path):
    """A SCLD lib dir is one that contains a Char/ subdir."""
    return os.path.isdir(os.path.join(path, 'Char'))


def _autodiscover_libs(root, max_depth=4):
    """Walk `root` up to max_depth and return every dir that looks like
    a SCLD lib (has Char/ subdir)."""
    found = []
    root = os.path.abspath(root)
    base_depth = root.count(os.sep)
    for dirpath, dirnames, _ in os.walk(root):
        depth = dirpath.count(os.sep) - base_depth
        if depth > max_depth:
            dirnames[:] = []
            continue
        if _looks_like_scld_lib(dirpath):
            found.append(dirpath)
            # Don't descend into a recognized lib (Char/ is inside it)
            dirnames[:] = []
    return sorted(set(found))


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--node', required=True,
                   help='DeckGen node name (e.g. N2P_v1.0)')
    src_g = p.add_mutually_exclusive_group(required=True)
    src_g.add_argument('--src',
                       help='Path to ONE SCLD lib folder')
    src_g.add_argument('--src-parent',
                       help='Parent dir containing multiple SCLD lib folders '
                            '(direct children only)')
    src_g.add_argument('--auto',
                       help='Auto-discover SCLD lib folders anywhere under this path '
                            '(walks up to 4 levels deep)')
    p.add_argument('--filter', default=None,
                   help='Only import lib folders whose name contains this substring '
                        '(use with --src-parent or --auto)')
    p.add_argument('--deckgen-root', default=None,
                   help='Path to DeckGen repo root (default: parent of this script)')
    p.add_argument('--link', action='store_true',
                   help='Symlink instead of copy (saves disk and time)')
    p.add_argument('--dry-run', action='store_true',
                   help='Preview without writing')
    p.add_argument('--quiet', action='store_true',
                   help='Suppress per-file output')
    args = p.parse_args()

    if args.deckgen_root:
        root = os.path.abspath(args.deckgen_root)
    else:
        root = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

    if args.src:
        libs = [os.path.abspath(args.src)]
    elif args.src_parent:
        parent = os.path.abspath(args.src_parent)
        if not os.path.isdir(parent):
            print(f"ERROR: --src-parent not found: {parent}", file=sys.stderr)
            sys.exit(1)
        libs = []
        for name in sorted(os.listdir(parent)):
            full = os.path.join(parent, name)
            if not os.path.isdir(full):
                continue
            if args.filter and args.filter not in name:
                continue
            if _looks_like_scld_lib(full):
                libs.append(full)
    else:
        # --auto: walk recursively up to depth 4 to find SCLD libs anywhere
        root = os.path.abspath(args.auto)
        if not os.path.isdir(root):
            print(f"ERROR: --auto not found: {root}", file=sys.stderr)
            sys.exit(1)
        libs = _autodiscover_libs(root)
        if args.filter:
            libs = [l for l in libs
                    if args.filter in os.path.basename(l)]
        print(f"Auto-discovered {len(libs)} SCLD lib folder(s) under {root}")

    if not libs:
        print("ERROR: no SCLD lib folders to import.", file=sys.stderr)
        sys.exit(1)

    total = {'char_files': 0, 'template_files': 0,
             'netlist_dirs': 0, 'skipped': 0, 'errors': 0}
    print(f"Importing {len(libs)} library/libraries -> "
          f"{root}/collateral/{args.node}/")
    if args.dry_run:
        print("(dry-run; no files written)")
    print()

    for src_lib in libs:
        lib_type = os.path.basename(os.path.normpath(src_lib))
        print(f"== {lib_type} ==")
        c = import_one_lib(src_lib, root, args.node,
                           link=args.link, dry_run=args.dry_run,
                           verbose=not args.quiet)
        for k in total:
            total[k] += c[k]
        print(f"  char={c['char_files']} template={c['template_files']} "
              f"netlist_dirs={c['netlist_dirs']} skipped={c['skipped']} "
              f"errors={c['errors']}")
        print()

    print("---")
    print(f"TOTAL  char={total['char_files']} template={total['template_files']} "
          f"netlist_dirs={total['netlist_dirs']} skipped={total['skipped']} "
          f"errors={total['errors']}")
    if total['errors']:
        sys.exit(1)

    if args.dry_run:
        print("\nDry-run complete. Re-run without --dry-run to actually import.")
        return

    print("\nNext step: generate manifests")
    print(f"  python3 tools/scan_collateral.py --node {args.node} --all")


if __name__ == '__main__':
    main()
