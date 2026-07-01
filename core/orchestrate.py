"""core/orchestrate.py -- Phase C run loop (discover / generate / submit).

Simulator-free, production-shaped. Drives generation through the proven
resolve_all_from_collateral -> assemble_* path, records every work item in an
append-only NDJSON ledger, and enforces the no-silent-drop invariant via
core/coverage.py. Generation and submission are two operator-gated phases.
ASCII only. Nothing here imports a front-end.
"""
from __future__ import annotations

import fnmatch
import os

from core.verify_sidecar import to_lit_when
from core.parsers.template_tcl import parse_template_tcl_full

SEQUENTIAL_ARCS = frozenset({
    'hold', 'setup', 'removal', 'recovery', 'mpw', 'min_pulse_width',
    'non_seq_hold', 'non_seq_setup',
})

_OPP = {'rise': 'fall', 'fall': 'rise'}


class SelectionEmpty(Exception):
    """A non-empty scope matched zero work items (surfaced at the scope gate)."""


def format_arc_id(arc_type, cell, probe_pin, probe_dir, rel_pin, rel_dir,
                  when, i1, i2):
    """Build a cell_arc_pt identifier; round-trips through
    parse_arc_identifier. when is encoded via to_lit_when
    ('!SE&SI'->'notSE_SI'); empty/NO_CONDITION -> literal 'NO_CONDITION'."""
    w = to_lit_when(when) or 'NO_CONDITION'
    return '_'.join([arc_type, cell, probe_pin, probe_dir, rel_pin, rel_dir,
                     w, str(i1), str(i2)])


def wi_universe_tuple(wi):
    return (wi['cell'], wi['arc_type'], wi['i1'], wi['i2'], wi['corner'])


def _template_for(cell_info, arc_type):
    if arc_type in ('mpw', 'min_pulse_width'):
        return cell_info.get('mpw_template')
    if arc_type in SEQUENTIAL_ARCS:
        return cell_info.get('constraint_template')
    return cell_info.get('delay_template')


def _grid_dims(template_info, cell_info, arc_type):
    """(n1, n2) LUT dimensions for this arc's backing template; (0, 0) if
    unknown."""
    name = _template_for(cell_info, arc_type)
    tpl = template_info.get('templates', {}).get(name or '', {})
    n1 = len(tpl.get('index_1') or [])
    n2 = len(tpl.get('index_2') or [])
    return n1, n2


def _points_for(n1, n2, table_points):
    """Return list of (i1, i2, skip) triples for one arc's grid given the
    scope's table_points. skip is None or 'no_such_point'."""
    all_pts = [(i1, i2) for i1 in range(1, n1 + 1) for i2 in range(1, n2 + 1)]
    if table_points is None:
        return [(i1, i2, None) for (i1, i2) in all_pts]
    if isinstance(table_points, int):
        return [(i1, i2, None) for (i1, i2) in all_pts[:table_points]]
    # explicit list of (i1, i2)
    out = []
    for (i1, i2) in table_points:
        ok = (1 <= i1 <= n1) and (1 <= i2 <= n2)
        out.append((i1, i2, None if ok else 'no_such_point'))
    return out


def discover(manifest, template_tcl_by_corner, scope=None):
    """manifest x per-corner template.tcl path, filtered by scope -> list of
    WorkItem dicts. Never raises for data problems (unreadable template.tcl ->
    that corner contributes a skipped:template_tcl_unreadable marker item).
    Raises SelectionEmpty only when the produced set is empty."""
    scope = scope or {}
    cell_globs = scope.get('cells')
    arcs_per_cell = scope.get('arcs_per_cell')
    table_points = scope.get('table_points')
    corner_filter = scope.get('corners')

    corners = list(manifest.get('corners', {}).keys())
    if corner_filter is not None:
        corners = [c for c in corners if c in set(corner_filter)]

    items = []
    for corner in corners:
        tcl_path = template_tcl_by_corner.get(corner)
        if not tcl_path or not os.path.isfile(tcl_path):
            items.append({
                'cell': '*', 'arc_type': '*', 'i1': 0, 'i2': 0,
                'corner': corner, 'arc': {}, 'arc_id': '',
                'skip': 'template_tcl_unreadable'})
            continue
        try:
            info = parse_template_tcl_full(tcl_path)
        except Exception:
            items.append({
                'cell': '*', 'arc_type': '*', 'i1': 0, 'i2': 0,
                'corner': corner, 'arc': {}, 'arc_id': '',
                'skip': 'template_tcl_unreadable'})
            continue
        arcs = info.get('arcs', [])
        cells_in_order = []
        for a in arcs:
            if a['cell'] not in cells_in_order:
                cells_in_order.append(a['cell'])
        for cell in cells_in_order:
            if cell_globs is not None and not any(
                    fnmatch.fnmatch(cell, g) for g in cell_globs):
                continue
            cell_info = info.get('cells', {}).get(cell, {})
            cell_arcs = [a for a in arcs if a['cell'] == cell]
            if arcs_per_cell is not None:
                cell_arcs = cell_arcs[:arcs_per_cell]
            for arc in cell_arcs:
                n1, n2 = _grid_dims(info, cell_info, arc['arc_type'])
                probe = (arc['probe_list'][0] if arc.get('probe_list')
                         else arc['pin'])
                for (i1, i2, skip) in _points_for(n1, n2, table_points):
                    items.append({
                        'cell': cell,
                        'arc_type': arc['arc_type'],
                        'i1': i1, 'i2': i2, 'corner': corner,
                        'arc': arc,
                        'arc_id': format_arc_id(
                            arc['arc_type'], cell, probe, arc['pin_dir'],
                            arc['rel_pin'], arc['rel_pin_dir'],
                            arc.get('when', ''), i1, i2),
                        'skip': skip,
                    })

    if not items:
        raise SelectionEmpty(
            'selection matched 0 items; check '
            '--cells/--arcs-per-cell/--table-points/--corners')
    return items
