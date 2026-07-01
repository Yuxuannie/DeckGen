"""core/coverage.py -- B4 no-silent-drop coverage report.

Pure functions plus two explicit emit helpers. Turns a list of OutcomeRow
dicts + the selected work-item universe into a coverage matrix, a no-drop
balance assertion, and NDJSON + HTML renderings. ASCII only.
"""
from __future__ import annotations

import json

OUTCOME_KEYS = ('arc_id', 'cell', 'arc_type', 'i1', 'i2', 'corner',
                'state', 'category', 'reason', 'netlist_path', 'deck_path')


def _tuple(row):
    return (row['cell'], row['arc_type'], row['i1'], row['i2'], row['corner'])


def build_coverage(rows, universe):
    """rows: list[OutcomeRow dict]; universe: list[(cell, arc_type, i1, i2,
    corner)]. Returns the CoverageReport dict (see module/spec)."""
    expected = len(universe)
    generated = submitted = errors = skipped = 0
    by_category = {}
    by_corner = {}
    matrix = {}
    triage = []

    def corner_slot(c):
        return by_corner.setdefault(
            c, {'generated': 0, 'submitted': 0, 'error': 0, 'skipped': 0})

    for r in rows:
        state = r['state']
        c = r['corner']
        matrix.setdefault((r['cell'], r['arc_type'], r['i1'], r['i2']), {})[c] = state
        slot = corner_slot(c)
        if state == 'generated':
            generated += 1
            slot['generated'] += 1
        elif state == 'submitted':
            submitted += 1
            slot['submitted'] += 1
        elif state == 'generation_error':
            errors += 1
            slot['error'] += 1
            cat = r.get('category') or 'unsupported_arc'
            by_category[cat] = by_category.get(cat, 0) + 1
            triage.append({k: r.get(k, '') for k in (
                'arc_id', 'cell', 'arc_type', 'i1', 'i2', 'corner',
                'category', 'reason', 'netlist_path', 'deck_path')})
        elif state == 'skipped':
            skipped += 1
            slot['skipped'] += 1

    row_tuples = {_tuple(r) for r in rows}
    unaccounted = [u for u in universe if u not in row_tuples]

    accounted = generated + submitted + errors + skipped
    balanced = (accounted == expected) and (not unaccounted)

    summary = {
        'expected': expected,
        'generated': generated,
        'submitted': submitted,
        'generation_error': errors,
        'skipped': skipped,
        'balanced': balanced,
    }
    return {
        'summary': summary,
        'by_category': by_category,
        'by_corner': by_corner,
        'matrix': matrix,
        'triage': triage,
        'unaccounted': unaccounted,
    }


def coverage_ndjson(report, path):
    """One JSON line per (cell, arc_type, i1, i2, corner) matrix cell."""
    with open(path, 'w', encoding='ascii') as fh:
        for (cell, at, i1, i2), per_corner in sorted(
                report['matrix'].items(), key=lambda kv: str(kv[0])):
            for corner, state in sorted(per_corner.items()):
                fh.write(json.dumps({
                    'cell': cell, 'arc_type': at, 'i1': i1, 'i2': i2,
                    'corner': corner, 'state': state,
                }) + '\n')


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def coverage_html(report, path):
    """Static HTML: QA balance block + coverage matrix + triage cards."""
    s = report['summary']
    ok = s['balanced']
    headline = ('BALANCED -- no arcs dropped' if ok
                else 'INCOMPLETE -- coverage does not balance')
    color = '#0a0' if ok else '#c00'
    out = ['<!DOCTYPE html><html><head><meta charset="ascii">',
           '<title>DeckGen coverage</title></head><body>',
           '<h1 style="color:%s">%s</h1>' % (color, _esc(headline)),
           '<p>expected=%d generated=%d submitted=%d error=%d skipped=%d</p>'
           % (s['expected'], s['generated'], s['submitted'],
              s['generation_error'], s['skipped'])]
    if report['unaccounted']:
        out.append('<p style="color:#c00">unaccounted: %s</p>'
                   % _esc(report['unaccounted']))
    out.append('<h2>Matrix</h2><table border="1"><tr>'
               '<th>cell</th><th>arc_type</th><th>i1</th><th>i2</th>'
               '<th>corner</th><th>state</th></tr>')
    for (cell, at, i1, i2), per_corner in sorted(
            report['matrix'].items(), key=lambda kv: str(kv[0])):
        for corner, state in sorted(per_corner.items()):
            out.append('<tr><td>%s</td><td>%s</td><td>%d</td><td>%d</td>'
                       '<td>%s</td><td>%s</td></tr>'
                       % (_esc(cell), _esc(at), i1, i2, _esc(corner),
                          _esc(state)))
    out.append('</table><h2>Triage (%d)</h2>' % len(report['triage']))
    for t in report['triage']:
        out.append('<div style="border:1px solid #c00;margin:4px;padding:4px">'
                   '<b>%s</b> [%s]<br>%s<br>netlist: %s<br>deck: %s</div>'
                   % (_esc(t['arc_id']), _esc(t['category']),
                      _esc(t['reason']), _esc(t['netlist_path']),
                      _esc(t['deck_path'])))
    out.append('</body></html>')
    with open(path, 'w', encoding='ascii') as fh:
        fh.write('\n'.join(out))
