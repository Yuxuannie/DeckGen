import json
import os

from core.coverage import build_coverage, coverage_ndjson, coverage_html


def _row(cell, at, i1, i2, corner, state, category='', reason='',
         netlist_path='', deck_path='', parity=''):
    return {
        'arc_id': f'{at}_{cell}_Q_rise_CP_rise_NO_CONDITION_{i1}_{i2}',
        'cell': cell, 'arc_type': at, 'i1': i1, 'i2': i2, 'corner': corner,
        'state': state, 'category': category, 'reason': reason,
        'netlist_path': netlist_path, 'deck_path': deck_path,
        'parity': parity,
    }


def _universe(*tuples):
    return list(tuples)


def test_balanced_all_generated():
    uni = _universe(('DFFQ1', 'combinational', 1, 1, 'c1'),
                    ('DFFQ1', 'hold', 1, 1, 'c1'))
    rows = [_row('DFFQ1', 'combinational', 1, 1, 'c1', 'generated'),
            _row('DFFQ1', 'hold', 1, 1, 'c1', 'generated')]
    rep = build_coverage(rows, uni)
    s = rep['summary']
    assert s['expected'] == 2 and s['generated'] == 2
    assert s['generation_error'] == 0 and s['skipped'] == 0
    assert s['balanced'] is True
    assert rep['unaccounted'] == []


def test_balanced_mixed_states():
    uni = _universe(('C', 'combinational', 1, 1, 'c1'),
                    ('C', 'hold', 1, 1, 'c1'),
                    ('C', 'mpw', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'generated'),
            _row('C', 'hold', 1, 1, 'c1', 'generation_error',
                 category='latch_unsupported', reason='latch not supported',
                 netlist_path='/n/C.spi'),
            _row('C', 'mpw', 1, 1, 'c1', 'skipped', reason='no_such_point')]
    rep = build_coverage(rows, uni)
    s = rep['summary']
    assert (s['expected'], s['generated'], s['generation_error'],
            s['skipped']) == (3, 1, 1, 1)
    assert s['balanced'] is True
    assert rep['by_category'] == {'latch_unsupported': 1}
    assert rep['by_corner']['c1'] == {'generated': 1, 'submitted': 0,
                                      'error': 1, 'skipped': 1}
    assert len(rep['triage']) == 1
    t = rep['triage'][0]
    assert t['category'] == 'latch_unsupported' and t['netlist_path'] == '/n/C.spi'
    assert rep['matrix'][('C', 'hold', 1, 1)]['c1'] == 'generation_error'


def test_submitted_counts_as_generated_for_balance():
    uni = _universe(('C', 'combinational', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'submitted')]
    rep = build_coverage(rows, uni)
    assert rep['summary']['submitted'] == 1
    assert rep['summary']['balanced'] is True


def test_unbalanced_when_universe_item_has_no_row():
    uni = _universe(('C', 'combinational', 1, 1, 'c1'),
                    ('C', 'hold', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'generated')]
    rep = build_coverage(rows, uni)
    assert rep['summary']['balanced'] is False
    assert rep['unaccounted'] == [('C', 'hold', 1, 1, 'c1')]


def test_ndjson_one_line_per_matrix_cell(tmp_path):
    uni = _universe(('C', 'combinational', 1, 1, 'c1'),
                    ('C', 'hold', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'generated'),
            _row('C', 'hold', 1, 1, 'c1', 'generated')]
    rep = build_coverage(rows, uni)
    p = os.path.join(str(tmp_path), 'coverage.ndjson')
    coverage_ndjson(rep, p)
    lines = [l for l in open(p, encoding='ascii').read().splitlines() if l.strip()]
    assert len(lines) == 2
    recs = [json.loads(l) for l in lines]
    assert all({'cell', 'arc_type', 'i1', 'i2', 'corner', 'state'} <= set(r)
               for r in recs)


def test_parity_review_lists_each_diff_deck():
    # The 'N diff (review)' count must be backed by an actual review queue:
    # one entry per diff verdict, carrying the deck path. byte/engine_extras/
    # no_golden rows stay out of it.
    uni = _universe(('C', 'hold', 1, 1, 'c1'), ('C', 'hold', 2, 2, 'c1'),
                    ('C', 'hold', 3, 3, 'c1'))
    rows = [_row('C', 'hold', 1, 1, 'c1', 'generated', parity='byte',
                 deck_path='/o/d1/nominal_sim.sp'),
            _row('C', 'hold', 2, 2, 'c1', 'generated', parity='diff',
                 deck_path='/o/d2/nominal_sim.sp'),
            _row('C', 'hold', 3, 3, 'c1', 'generated', parity='no_golden',
                 deck_path='/o/d3/nominal_sim.sp')]
    rep = build_coverage(rows, uni)
    assert rep['by_parity'] == {'byte': 1, 'diff': 1, 'no_golden': 1}
    assert len(rep['parity_review']) == 1
    r = rep['parity_review'][0]
    assert r['deck_path'] == '/o/d2/nominal_sim.sp'
    assert r['arc_id'] == 'hold_C_Q_rise_CP_rise_NO_CONDITION_2_2'
    assert r['corner'] == 'c1'


def test_parity_review_empty_when_no_diffs():
    uni = _universe(('C', 'hold', 1, 1, 'c1'))
    rows = [_row('C', 'hold', 1, 1, 'c1', 'generated', parity='byte')]
    assert build_coverage(rows, uni)['parity_review'] == []


def test_html_review_queue_names_deck_and_golden(tmp_path):
    uni = _universe(('C', 'hold', 1, 1, 'c1'))
    rows = [_row('C', 'hold', 1, 1, 'c1', 'generated', parity='diff',
                 deck_path='/o/d/nominal_sim.sp')]
    rep = build_coverage(rows, uni)
    p = os.path.join(str(tmp_path), 'coverage.html')
    coverage_html(rep, p)
    html = open(p, encoding='ascii').read()
    assert 'Review queue (1 diff vs golden)' in html
    assert '/o/d/nominal_sim.sp' in html
    assert '/o/d/nominal_sim.golden.sp' in html
    assert all(ord(ch) < 128 for ch in html)


def test_html_has_qa_block_and_triage(tmp_path):
    # One arc errored (produces a triage card) AND one universe item has no
    # row at all -> unaccounted -> unbalanced -> the INCOMPLETE QA headline.
    # (An errored arc alone is still *accounted for*, i.e. balanced=True; the
    # INCOMPLETE headline only appears when the universe is not fully covered.)
    uni = _universe(('C', 'hold', 1, 1, 'c1'),
                    ('C', 'hold', 2, 2, 'c1'))
    rows = [_row('C', 'hold', 1, 1, 'c1', 'generation_error',
                 category='latch_unsupported', reason='latch not supported')]
    rep = build_coverage(rows, uni)
    assert rep['summary']['balanced'] is False   # ('C','hold',2,2,'c1') unaccounted
    p = os.path.join(str(tmp_path), 'coverage.html')
    coverage_html(rep, p)
    html = open(p, encoding='ascii').read()
    assert 'INCOMPLETE' in html or 'incomplete' in html.lower()
    assert 'latch_unsupported' in html
    assert all(ord(ch) < 128 for ch in html)
