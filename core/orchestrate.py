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


import json

from core.coverage import build_coverage, coverage_ndjson, coverage_html

_CATEGORY_RULES = [
    ('combinational', 'combinational_cell'),
    ('latch', 'latch_unsupported'),
    ('p1 not proven', 'p1_unproven'),
    ('p1 could not be proven', 'p1_unproven'),
    ('seqscope', 'out_of_corpus'),
    ('beyond depth', 'out_of_corpus'),
    ('beyond corpus', 'out_of_corpus'),
    ('parse', 'parse_fail'),
    ('no .subckt', 'parse_fail'),
    ('port order', 'parse_fail'),
    ('grammar', 'no_grammar'),
]


def categorize(error_msg):
    low = (error_msg or '').lower()
    for needle, cat in _CATEGORY_RULES:
        if needle in low:
            return cat
    return 'unsupported_arc'


def _row(wi, state, category='', reason='', netlist_path='', deck_path=''):
    return {
        'arc_id': wi.get('arc_id', ''),
        'cell': wi['cell'], 'arc_type': wi['arc_type'],
        'i1': wi['i1'], 'i2': wi['i2'], 'corner': wi['corner'],
        'state': state, 'category': category, 'reason': reason,
        'netlist_path': netlist_path, 'deck_path': deck_path,
    }


def _deck_path(out_dir, lib_type, wi):
    return os.path.join(out_dir, 'decks', lib_type, wi['corner'],
                        wi['arc_type'], wi['arc_id'], 'nominal_sim.sp')


def generate_one(work_item, node, lib_type, collateral_root, grammar, out_dir,
                 engine_cache=None):
    """Resolve + route + assemble one work item; write its deck if OK.
    Returns an OutcomeRow. Never raises for data/generation problems."""
    from core.deck_assemble import assemble_combinational, assemble_sequential
    from core.resolver import resolve_all_from_collateral

    if work_item.get('skip'):
        return _row(work_item, 'skipped', reason=work_item['skip'])

    arc = work_item['arc']
    probe = arc['probe_list'][0] if arc.get('probe_list') else arc['pin']
    try:
        result = resolve_all_from_collateral(
            cell_name=arc['cell'], arc_type=arc['arc_type'],
            rel_pin=arc['rel_pin'], rel_dir=arc['rel_pin_dir'],
            constr_pin=arc['pin'],
            constr_dir=_OPP.get(arc['rel_pin_dir'], 'fall'),
            probe_pin=probe, node=node, lib_type=lib_type,
            corner_name=work_item['corner'], collateral_root=collateral_root,
            overrides={'index_1_index': work_item['i1'],
                       'index_2_index': work_item['i2']})
    except Exception as e:                                    # resolution failure
        return _row(work_item, 'generation_error',
                    category=categorize(str(e)), reason=str(e))

    arc_info = result[0] if isinstance(result, list) else result

    # Overlay the routing/identity keys the engine emitters need, from the
    # authoritative template.tcl arc. resolve provides the resolved numeric /
    # file keys (VDD, TEMP, INDEX_*, MAX_SLEW, OUTPUT_LOAD, NETLIST_PATH, ...).
    arc_info.setdefault('WAVEFORM_FILE', 'std_wv.spi')
    arc_info.setdefault('INCLUDE_FILE', 'MODEL.inc')
    arc_info.update({
        'CELL_NAME': arc['cell'], 'ARC_TYPE': arc['arc_type'],
        'REL_PIN': arc['rel_pin'], 'REL_PIN_DIR': arc['rel_pin_dir'],
        'CONSTR_PIN': arc['pin'],
        'CONSTR_PIN_DIR': _OPP.get(arc['rel_pin_dir'], 'fall'),
        'PROBE_PIN_1': probe,
        'WHEN': arc.get('when') or 'NO_CONDITION',
    })

    netlist_path = arc_info.get('NETLIST_PATH', '')
    if not netlist_path or not os.path.isfile(netlist_path):
        return _row(work_item, 'generation_error', category='parse_fail',
                    reason='netlist not found: %r' % netlist_path,
                    netlist_path=netlist_path)
    netlist_src = open(netlist_path, encoding='latin-1').read()

    if arc['arc_type'].startswith('combinational'):
        asm = assemble_combinational(arc_info, netlist_src, grammar,
                                     engine_cache=engine_cache)
    else:
        asm = assemble_sequential(arc_info, netlist_src, grammar,
                                  engine_cache=engine_cache)

    if asm.get('status') != 'OK':
        return _row(work_item, 'generation_error',
                    category=categorize(asm.get('error', '')),
                    reason=asm.get('error', 'unknown'),
                    netlist_path=netlist_path)

    dpath = _deck_path(out_dir, lib_type, work_item)
    os.makedirs(os.path.dirname(dpath), exist_ok=True)
    with open(dpath, 'w', encoding='ascii') as fh:
        fh.write(asm['deck_text'])
    return _row(work_item, 'generated', netlist_path=netlist_path,
                deck_path=dpath)


def write_ledger(rows, path):
    """Atomic full-file NDJSON rewrite (temp + rename)."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='ascii') as fh:
        for r in rows:
            fh.write(json.dumps(r) + '\n')
    os.replace(tmp, path)


def read_ledger(path):
    rows = []
    with open(path, encoding='ascii') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_manifest_and_tcl(collateral_dir, node, lib_type):
    from core.collateral import CollateralStore
    from tools.scan_collateral import build_manifest
    mpath = build_manifest(collateral_dir, node, lib_type)
    manifest = json.load(open(mpath, encoding='ascii'))
    store = CollateralStore(collateral_dir, node, lib_type, skip_autoscan=True)
    tcl = {c: store.get_corner(c)['template_tcl'] for c in manifest['corners']}
    return manifest, tcl


def _write_reports(rows, universe, out_dir):
    report = build_coverage(rows, universe)
    coverage_ndjson(report, os.path.join(out_dir, 'coverage.ndjson'))
    coverage_html(report, os.path.join(out_dir, 'coverage.html'))
    return report


def generate(collateral_dir, node, lib_type, out_dir, scope=None,
             progress=None):
    """Phase 1: discover -> generate_one each -> ledger + coverage. Writes NO
    bsub. Returns RunResult. Stops at the resting state."""
    from core.measurement.emit import load_grammar

    os.makedirs(out_dir, exist_ok=True)
    manifest, tcl = _load_manifest_and_tcl(collateral_dir, node, lib_type)
    work_items = discover(manifest, tcl, scope)     # may raise SelectionEmpty
    grammar = load_grammar()

    rows = []
    total = len(work_items)
    engine_cache = {}    # per-run: parse/decompose/classify once per cell
    for idx, wi in enumerate(work_items):
        rows.append(generate_one(wi, node, lib_type, collateral_dir, grammar,
                                 out_dir, engine_cache=engine_cache))
        if progress:
            progress(idx + 1, total, rows[-1])

    write_ledger(rows, os.path.join(out_dir, 'ledger.ndjson'))
    with open(os.path.join(out_dir, 'run_config.json'), 'w',
              encoding='ascii') as fh:
        json.dump({'collateral': collateral_dir, 'node': node,
                   'lib_type': lib_type, 'scope': scope or {},
                   'out_dir': out_dir}, fh, indent=2)
    universe = [wi_universe_tuple(wi) for wi in work_items]
    report = _write_reports(rows, universe, out_dir)
    return {'run_dir': out_dir, 'universe': universe, 'rows': rows,
            'coverage': report}


class NothingToSubmit(Exception):
    """submit() called but no rows are in the 'generated' state."""


def submit(run_dir, slot_limit=50, runlimit="00:20", progress=None):
    """Phase 2 (post-confirm): read generated rows, emit real bsub arrays,
    advance rows generated -> submitted, rewrite ledger + coverage. Refuses
    (NothingToSubmit, no partial writes) if there is nothing to submit."""
    from core.lsf import emit_arrays

    ledger_path = os.path.join(run_dir, 'ledger.ndjson')
    rows = read_ledger(ledger_path)
    generated = [r for r in rows if r['state'] == 'generated']
    if not generated:
        raise NothingToSubmit('no generated decks to submit in %s' % run_dir)

    arrays = emit_arrays(generated, run_dir, slot_limit=slot_limit,
                         runlimit=runlimit)
    submitted_ids = {r['arc_id'] for r in generated}
    for r in rows:
        if r['state'] == 'generated' and r['arc_id'] in submitted_ids:
            r['state'] = 'submitted'
    write_ledger(rows, ledger_path)

    universe = [(r['cell'], r['arc_type'], r['i1'], r['i2'], r['corner'])
                for r in rows]
    report = _write_reports(rows, universe, run_dir)
    if progress:
        progress(arrays)
    return {'run_dir': run_dir, 'universe': universe, 'rows': rows,
            'coverage': report, 'arrays': arrays}


_PIN_BUCKET_SECONDS = {'small': 30, 'medium': 90, 'large': 180}


def plan(collateral_dir, node, lib_type, scope=None):
    """dry-run: discover only, return the scope plan without generating."""
    manifest, tcl = _load_manifest_and_tcl(collateral_dir, node, lib_type)
    work_items = discover(manifest, tcl, scope)      # may raise SelectionEmpty
    matrix_counts = {}
    for wi in work_items:
        key = (wi['cell'], wi['corner'])
        matrix_counts[key] = matrix_counts.get(key, 0) + 1
    # heuristic walltime: 90s/item baseline (medium pin bucket)
    est = len(work_items) * _PIN_BUCKET_SECONDS['medium']
    return {'expected': len(work_items), 'matrix_counts': matrix_counts,
            'walltime_est': est, 'work_items': work_items}


def run(collateral_dir, node, lib_type, out_dir, scope=None, dry_run=False,
        confirm=None, slot_limit=50, progress=None):
    """CLI convenience wiring. dry_run -> plan only. Else generate; if confirm
    is provided and returns True, submit. confirm=None -> generate only (safe
    default, no submission)."""
    if dry_run:
        return plan(collateral_dir, node, lib_type, scope)
    res = generate(collateral_dir, node, lib_type, out_dir, scope=scope,
                   progress=progress)
    if confirm is not None and confirm(res):
        try:
            return submit(out_dir, slot_limit=slot_limit)
        except NothingToSubmit:
            return res
    return res
