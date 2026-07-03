import os
import shutil

import pytest

from tools.scan_collateral import build_manifest
from core.orchestrate import (generate, submit, run, plan, read_ledger,
                              NothingToSubmit)

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'


def _setup(dest):
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    os.path.join(dest, NODE, LIB))
    build_manifest(dest, NODE, LIB)
    return dest


def test_generate_then_submit_advances_rows(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    gen = generate(root, NODE, LIB, out, scope={'table_points': [(1, 1)]})
    n_generated = gen['coverage']['summary']['generated']
    if n_generated == 0:
        pytest.skip('fixture generated 0 decks; submit path needs >=1')
    res = submit(out)
    rows = read_ledger(os.path.join(out, 'ledger.ndjson'))
    submitted = [r for r in rows if r['state'] == 'submitted']
    assert len(submitted) == n_generated
    # bsub now exists (post-confirm)
    assert any(f.endswith('.bsub') for f in os.listdir(os.path.join(out, 'lsf')))
    # after submit invariant: generated == submitted
    assert res['coverage']['summary']['submitted'] == n_generated


def test_submit_with_no_generated_refuses(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    # scope of all no_such_point -> 0 generated, only skipped rows
    generate(root, NODE, LIB, out, scope={'table_points': [(99, 99)]})
    with pytest.raises(NothingToSubmit):
        submit(out)
    # no partial bsub written
    lsf = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf) and any(
        f.endswith('.bsub') for f in os.listdir(lsf)))


def test_run_dry_run_generates_nothing(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = run(root, NODE, LIB, out, scope={'table_points': [(1, 1)]},
              dry_run=True)
    assert res['expected'] == 2
    assert not os.path.isdir(os.path.join(out, 'decks'))
    assert not os.path.isfile(os.path.join(out, 'ledger.ndjson'))


def test_run_confirm_false_stops_at_generated(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = run(root, NODE, LIB, out, scope={'table_points': [(1, 1)]},
              confirm=lambda r: False)
    rows = read_ledger(os.path.join(out, 'ledger.ndjson'))
    assert all(r['state'] != 'submitted' for r in rows)
    lsf = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf) and any(
        f.endswith('.bsub') for f in os.listdir(lsf)))


def test_run_confirm_true_submits(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = run(root, NODE, LIB, out, scope={'table_points': [(1, 1)]},
              confirm=lambda r: True)
    if res['coverage']['summary'].get('submitted', 0) == 0:
        # only valid if 0 decks generated
        assert res['coverage']['summary']['generated'] == 0
    else:
        assert any(f.endswith('.bsub')
                   for f in os.listdir(os.path.join(out, 'lsf')))
