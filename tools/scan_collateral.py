#!/usr/bin/env python3
"""scan_collateral.py - Scan collateral/{node}/{lib_type}/ and emit manifest.json.

Does NOT copy files. Walks Char/, Template/, Netlist/ and records paths
grouped by corner. Writes manifest.json in the leaf directory.

Usage:
    python3 tools/scan_collateral.py --node N2P_v1.0 --lib_type <lib>
    python3 tools/scan_collateral.py --node N2P_v1.0 --all
    python3 tools/scan_collateral.py --all
"""

import argparse
import datetime
import json
import os
import re
import sys


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DECKGEN_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '..'))

# Corner regex: captures {process}_{voltage}v_{temp}c_{rc_type} with rc ending in _T
# Example match: ssgnp_0p450v_m40c_cworst_CCworst_T
# Boundary before <process> can be: start, '_', or a digit (handles SCLD's
# c221227ssgnp_... naming where process is glued to a date suffix without '_').
# Voltage allows 1+ digits before/after 'p' (handles 0p7, 0p475, 1p1, etc.).
_CORNER_RE = re.compile(
    r'(?:^|_|(?<=\d))(?P<process>[a-z]+\d*)_(?P<vdd>\d+p\d+)v_(?P<temp>m?\d+)c_(?P<rc>[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*?_T)(?=[._]|$)'
)


def _parse_corner(name):
    """Extract (process, vdd, temp, rc_type) from a corner token.

    Returns (process, vdd_dotted, temp_signed, rc) or None.
    """
    m = _CORNER_RE.search(name)
    if not m:
        return None
    vdd_raw = m.group('vdd')              # '0p450'
    vdd = vdd_raw.replace('p', '.')       # '0.450'
    temp_raw = m.group('temp')            # 'm40' or '25'
    temp = ('-' + temp_raw[1:]) if temp_raw.startswith('m') else temp_raw
    return m.group('process'), vdd, temp, m.group('rc')


def _find_char_files(char_dir):
    """Scan Char/ and bucket files by corner + kind.

    Returns (result, warnings, lib_global) where:
      result    -- {corner_key: {kind: relpath}} for files with corner in name
      warnings  -- list of strings
      lib_global -- {kind: relpath} for files with NO corner in name (e.g.,
                    SCLD's lib-wide char_<lib>.cons.tcl). These will be bound
                    to every discovered corner by the caller.
    """
    result = {}
    warnings = []
    lib_global = {}
    if not os.path.isdir(char_dir):
        return result, warnings, lib_global

    # Priority-ordered suffixes (longest first)
    SUFFIXES = [
        ('char_cons',     '.cons.tcl'),
        ('char_non_cons', '.non_cons.tcl'),
        ('char_combined', '.tcl'),       # plain *.tcl after .cons/.non_cons fail
        ('inc_delay',     '.delay.inc'),
        ('inc_hold',      '.hold.inc'),
        ('inc_setup',     '.setup.inc'),
        ('inc_mpw',       '.mpw.inc'),
        ('inc_base',      '.inc'),
        ('usage_l',       '.usage.l'),
    ]

    # Philosophy: Char/ may contain anything (it's a "disk"). We grab only
    # what MCQC needs and silently skip the rest -- no warnings about
    # unrecognized files. Warnings are reserved for MISSING required data.
    for fname in sorted(os.listdir(char_dir)):
        full = os.path.join(char_dir, fname)
        if not os.path.isfile(full):
            continue

        # Skip template tcl files that ended up in Char/ (collected separately).
        if fname.endswith('.template.tcl'):
            continue

        for kind, suffix in SUFFIXES:
            if not fname.endswith(suffix):
                continue
            stem = fname[:-len(suffix)]
            corner_parse = _parse_corner(stem)

            # No corner in the filename -> for char tcl, treat as lib-global.
            # For other types (.inc, .usage.l) silently skip; not actionable.
            if corner_parse is None:
                if kind in ('char_cons', 'char_non_cons', 'char_combined'):
                    rel = os.path.relpath(full, os.path.dirname(char_dir))
                    lib_global.setdefault(kind, rel)
                break

            process, vdd, temp, rc = corner_parse
            vdd_raw = vdd.replace('.', 'p')
            temp_raw = ('m' + temp[1:]) if temp.startswith('-') else temp
            corner_key = f"{process}_{vdd_raw}v_{temp_raw}c_{rc}"
            entry = result.setdefault(corner_key, {})
            entry.setdefault(kind, os.path.relpath(full, os.path.dirname(char_dir)))
            break
        # No suffix match -> silently ignore (could be README, .sh, junk)

    return result, warnings, lib_global


def _find_template_files(template_dir):
    """Scan Template/ for *.template.tcl per corner."""
    result = {}
    warnings = []
    if not os.path.isdir(template_dir):
        return result, warnings

    # Same philosophy as Char/: silently skip anything that isn't a
    # *.template.tcl with a parseable corner.
    for fname in sorted(os.listdir(template_dir)):
        if not fname.endswith('.template.tcl'):
            continue
        full = os.path.join(template_dir, fname)
        stem = fname[:-len('.template.tcl')]
        corner_parse = _parse_corner(stem)
        if not corner_parse:
            continue
        process, vdd, temp, rc = corner_parse
        vdd_raw = vdd.replace('.', 'p')
        temp_raw = ('m' + temp[1:]) if temp.startswith('-') else temp
        corner_key = f"{process}_{vdd_raw}v_{temp_raw}c_{rc}"
        result[corner_key] = os.path.relpath(full, os.path.dirname(template_dir))

    return result, warnings


def _find_netlist_dirs(netlist_dir):
    """Scan Netlist/ for LPE_{rc}_{temp} subdirs."""
    lpe_dirs = {}
    cells = {}
    if not os.path.isdir(netlist_dir):
        return lpe_dirs, cells

    for sub in sorted(os.listdir(netlist_dir)):
        subpath = os.path.join(netlist_dir, sub)
        if not os.path.isdir(subpath):
            continue
        rel = os.path.relpath(subpath, os.path.dirname(netlist_dir))
        lpe_dirs[sub] = rel
        for f in os.listdir(subpath):
            if not f.endswith(('.spi', '.sp', '.spice')):
                continue
            stem = f
            for s in ('_c_qa.spi', '_c.spi', '.spi', '.sp', '.spice'):
                if stem.endswith(s):
                    stem = stem[:-len(s)]
                    break
            cells.setdefault(stem, []).append(sub)

    return lpe_dirs, cells


def _lpe_suffix_for_corner(rc, temp):
    """Build 'LPE_{rc}_{temp}c' suffix matching netlist subdir naming."""
    t = 'm' + temp[1:] if temp.startswith('-') else temp
    return f"LPE_{rc}_{t}c"


def scan_one(collateral_root, node, lib_type):
    """Scan one {node}/{lib_type}/ leaf and return a manifest dict."""
    leaf = os.path.join(collateral_root, node, lib_type)
    char_dir     = os.path.join(leaf, 'Char')
    template_dir = os.path.join(leaf, 'Template')
    netlist_dir  = os.path.join(leaf, 'Netlist')

    warnings = []

    char_map, w, lib_global_char = _find_char_files(char_dir); warnings.extend(w)
    template_map, w = _find_template_files(template_dir); warnings.extend(w)
    lpe_dirs, cells  = _find_netlist_dirs(netlist_dir)

    # SCLD pattern: char_<lib>.cons.tcl / .non_cons.tcl have NO corner in name.
    # Bind such lib-global files to every corner discovered via .inc files.
    if lib_global_char:
        # Make sure every corner with .inc files has a char entry to receive
        # the lib-global tcl. (corners may exist via .inc only.)
        for corner_key, entry in char_map.items():
            for k, v in lib_global_char.items():
                entry.setdefault(k, v)

    corners = {}
    for corner_key, char in char_map.items():
        parse = _parse_corner(corner_key)
        if parse is None:
            # corner_key was produced by _parse_corner above, this is
            # effectively unreachable; ignore silently.
            continue
        process, vdd, temp, rc = parse
        lpe_subdir = _lpe_suffix_for_corner(rc, temp)

        corners[corner_key] = {
            'process':     process,
            'vdd':         vdd,
            'temperature': temp,
            'rc_type':     rc,
            'char': {
                'combined':       char.get('char_combined'),
                'cons':           char.get('char_cons'),
                'non_cons':       char.get('char_non_cons'),
                'group_combined': None,
                'group_cons':     None,
                'group_non_cons': None,
            },
            'model': {
                'base':  char.get('inc_base'),
                'delay': char.get('inc_delay'),
                'hold':  char.get('inc_hold'),
                'setup': char.get('inc_setup'),
                'mpw':   char.get('inc_mpw'),
            },
            'usage_l':      char.get('usage_l'),
            'template_tcl': template_map.get(corner_key),
            'netlist_dir':  lpe_dirs.get(lpe_subdir),
        }

        if corners[corner_key]['netlist_dir'] is None:
            warnings.append(
                f"corner '{corner_key}': expected Netlist/{lpe_subdir} not found")
        if corners[corner_key]['template_tcl'] is None:
            warnings.append(
                f"corner '{corner_key}': no matching template.tcl")

    return {
        'schema_version':  1,
        'node':            node,
        'lib_type':        lib_type,
        'collateral_root': os.path.relpath(leaf, _DECKGEN_ROOT),
        'generated_at':    datetime.datetime.utcnow().isoformat() + 'Z',
        'corners':         corners,
        'cells':           cells,
        'warnings':        warnings,
    }


def build_manifest(collateral_root, node, lib_type):
    """Scan one leaf and write its manifest.json. Returns the manifest path."""
    manifest = scan_one(collateral_root, node, lib_type)
    leaf = os.path.join(collateral_root, node, lib_type)
    os.makedirs(leaf, exist_ok=True)
    path = os.path.join(leaf, 'manifest.json')
    with open(path, 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--node', default=None)
    p.add_argument('--lib_type', default=None)
    p.add_argument('--all', action='store_true',
                   help='scan every (node, lib_type) leaf under collateral/')
    p.add_argument('--collateral_root', default='collateral')
    args = p.parse_args()

    root = os.path.abspath(os.path.join(_DECKGEN_ROOT, args.collateral_root)) \
        if not os.path.isabs(args.collateral_root) else args.collateral_root

    if not os.path.isdir(root):
        print(f"ERROR: collateral root not found: {root}", file=sys.stderr)
        sys.exit(1)

    jobs = []
    if args.all and not args.node:
        for node in sorted(os.listdir(root)):
            node_dir = os.path.join(root, node)
            if not os.path.isdir(node_dir):
                continue
            for lib in sorted(os.listdir(node_dir)):
                if os.path.isdir(os.path.join(node_dir, lib)):
                    jobs.append((node, lib))
    elif args.node and args.all:
        node_dir = os.path.join(root, args.node)
        for lib in sorted(os.listdir(node_dir)):
            if os.path.isdir(os.path.join(node_dir, lib)):
                jobs.append((args.node, lib))
    elif args.node and args.lib_type:
        jobs.append((args.node, args.lib_type))
    else:
        p.error("provide --node + --lib_type, --node + --all, or --all")

    total_warnings = 0
    for node, lib in jobs:
        path = build_manifest(root, node, lib)
        with open(path) as f:
            data = json.load(f)
        n_warn = len(data.get('warnings', []))
        total_warnings += n_warn
        print(f"  {node}/{lib}: {len(data['corners'])} corners, {n_warn} warnings"
              f"  -> {os.path.relpath(path, _DECKGEN_ROOT)}")
        for w in data['warnings'][:10]:
            print(f"      WARN: {w}")

    print(f"\nScanned {len(jobs)} leaf(s), {total_warnings} warnings total.")


if __name__ == '__main__':
    main()
