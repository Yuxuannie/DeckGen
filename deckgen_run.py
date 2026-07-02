#!/usr/bin/env python3
"""deckgen_run.py -- lights-out, production-shaped DeckGen run (CLI).

One command discovers a scoped set of (cell, arc, table-point, corner) work
items from the collateral manifest, generates a deck or a reasoned refusal for
each, prints a no-silent-drop coverage headline + triage, and -- only after an
operator confirm -- writes real bsub job-array scripts. Simulator-free: stops
honestly at 'submitted' (team runs HSPICE). Stdlib + core only. ASCII only.
"""
from __future__ import annotations

import argparse
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from core.orchestrate import (generate, submit, plan, SelectionEmpty,   # noqa: E402
                              NothingToSubmit)
from core.lsf import bjobs_snapshot                                     # noqa: E402


def parse_scope(args):
    """Build the Scope dict from parsed CLI args. Omitted knob -> None (all)."""
    scope = {}
    scope['cells'] = ([c.strip() for c in args.cells.split(',') if c.strip()]
                      if args.cells else None)
    scope['arc_types'] = ([t.strip() for t in args.arc_types.split(',')
                           if t.strip()] if args.arc_types else None)
    scope['arcs_per_cell'] = args.arcs_per_cell
    scope['corners'] = ([c.strip() for c in args.corners.split(',')
                         if c.strip()] if args.corners else None)
    tp = args.table_points
    if not tp:
        scope['table_points'] = None
    elif ';' in tp or ',' in tp:
        pts = []
        for chunk in tp.split(';'):
            chunk = chunk.strip()
            if not chunk:
                continue
            i1, i2 = chunk.split(',')
            pts.append((int(i1), int(i2)))
        # a bare "N" (no comma) is an int count; handled below
        if len(pts) == 1 and ',' not in tp and ';' not in tp:
            scope['table_points'] = int(tp)
        else:
            scope['table_points'] = pts
    else:
        scope['table_points'] = int(tp)      # "N" -> first N points
    return scope


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--collateral', required=True)
    ap.add_argument('--node', required=True)
    ap.add_argument('--lib_type', required=True)
    ap.add_argument('--cells', help='comma-separated fnmatch globs')
    ap.add_argument('--arc-types', dest='arc_types',
                    help='comma-separated arc types e.g. "hold,mpw" '
                         '(mpw and min_pulse_width are equivalent)')
    ap.add_argument('--arcs-per-cell', type=int, dest='arcs_per_cell')
    ap.add_argument('--table-points', dest='table_points',
                    help='"N" (first N points) or ";"-separated i1,i2 e.g. "1,1;2,3"')
    ap.add_argument('--corners', help='comma-separated corner keys')
    ap.add_argument('--out', default='run_out')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--slot-limit', type=int, default=50, dest='slot_limit')
    args = ap.parse_args(argv)

    scope = parse_scope(args)

    # ---- dry-run scope gate ----
    if args.dry_run:
        try:
            pl = plan(args.collateral, args.node, args.lib_type, scope)
        except SelectionEmpty as e:
            print('SELECTION EMPTY: %s' % e)
            return 2
        print('Scope: %d selected work items' % pl['expected'])
        for (cell, corner), n in sorted(pl['matrix_counts'].items()):
            print('  %-24s %-40s %d items' % (cell, corner, n))
        print('Estimated walltime: ~%d s (%.1f min)'
              % (pl['walltime_est'], pl['walltime_est'] / 60.0))
        print('(dry-run: nothing generated)')
        return 0

    # ---- generation phase ----
    def _progress(done, total, row):
        sys.stdout.write('\r  generated %d/%d ...' % (done, total))
        sys.stdout.flush()

    try:
        res = generate(args.collateral, args.node, args.lib_type, args.out,
                       scope=scope, progress=_progress)
    except SelectionEmpty as e:
        print('SELECTION EMPTY: %s' % e)
        return 2
    print()

    s = res['coverage']['summary']
    accounted = s['generated'] + s['generation_error'] + s['skipped']
    print('=' * 60)
    print('NO-DROP LEDGER: %d items in -> %d accounted for '
          '(%d generated / %d error / %d skip)'
          % (s['expected'], accounted, s['generated'],
             s['generation_error'], s['skipped']))
    if s['balanced']:
        print('BALANCED -- no arcs dropped')
    else:
        print('!!! INCOMPLETE -- coverage does not balance !!!')
        for u in res['coverage']['unaccounted']:
            print('  unaccounted: %s' % (u,))

    triage = res['coverage']['triage']
    if triage:
        print('\nTRIAGE (%d generation errors):' % len(triage))
        for t in triage:
            print('  [%s] %s' % (t['category'], t['arc_id']))
            print('      reason: %s' % t['reason'])
            print('      netlist: %s' % t['netlist_path'])

    # ---- confirm-before-submit gate ----
    do_submit = args.yes or (sys.stdin.isatty() and
                             input('\nSubmit %d array jobs to LSF? [y/N] '
                                   % s['generated']).strip().lower() == 'y')
    if not do_submit:
        print('\nDecks ready, not submitted '
              '(re-run with --yes or use the GUI Submit button).')
        return 0 if s['balanced'] else 1

    try:
        res = submit(args.out, slot_limit=args.slot_limit)
    except NothingToSubmit as e:
        print('\nNothing to submit: %s' % e)
        return 0 if s['balanced'] else 1

    arrays = res.get('arrays', {})
    n_jobs = sum(a['n_jobs'] for a in arrays.values())
    print('\nSUBMITTED %d array job(s):' % n_jobs)
    for corner, a in sorted(arrays.items()):
        print('  bsub < %s   (%d jobs)' % (a['script'], a['n_jobs']))
    for line in bjobs_snapshot(arrays):
        print('  %s' % line)
    print('(team runs HSPICE)')
    return 0 if res['coverage']['summary']['balanced'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
