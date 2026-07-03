import os

from core.lsf import emit_arrays, bjobs_snapshot


def _grow(corner, n):
    return [{'arc_id': 'hold_C_Q_fall_CP_rise_NO_CONDITION_%d_1' % i,
             'corner': corner, 'state': 'generated',
             'deck_path': '/run/decks/%s/%d/nominal_sim.sp' % (corner, i)}
            for i in range(1, n + 1)]


def test_emit_arrays_writes_bsub_and_manifest(tmp_path):
    out = str(tmp_path)
    rows = _grow('c1', 3)
    arrays = emit_arrays(rows, out, slot_limit=50, runlimit='00:20')
    assert arrays['c1']['n_jobs'] == 3
    bsub = open(arrays['c1']['script'], encoding='ascii').read()
    assert '#BSUB -J "deckgen_c1[1-3]%50"' in bsub
    assert '#BSUB -W 00:20' in bsub
    assert 'LSB_JOBINDEX' in bsub
    man = open(arrays['c1']['manifest'], encoding='ascii').read().splitlines()
    assert len(man) == 3
    assert all(ord(ch) < 128 for ch in bsub)


def test_emit_arrays_groups_by_corner(tmp_path):
    out = str(tmp_path)
    rows = _grow('c1', 2) + _grow('c2', 1)
    arrays = emit_arrays(rows, out)
    assert set(arrays) == {'c1', 'c2'}
    assert arrays['c1']['n_jobs'] == 2 and arrays['c2']['n_jobs'] == 1


def test_emit_arrays_ignores_non_generated(tmp_path):
    out = str(tmp_path)
    rows = _grow('c1', 1)
    rows.append({'arc_id': 'x', 'corner': 'c1', 'state': 'generation_error',
                 'deck_path': ''})
    arrays = emit_arrays(rows, out)
    assert arrays['c1']['n_jobs'] == 1


def test_bjobs_snapshot_is_pend_only(tmp_path):
    arrays = emit_arrays(_grow('c1', 2), str(tmp_path))
    lines = bjobs_snapshot(arrays)
    assert lines and all('PEND' in l for l in lines)
    assert all('DONE' not in l and 'EXIT' not in l for l in lines)
    assert any('team runs HSPICE' in l for l in lines)
