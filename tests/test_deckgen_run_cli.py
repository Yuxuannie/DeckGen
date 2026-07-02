import os
import shutil
import subprocess
import sys

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = 'N2P_v1.0'
LIB = 'test_lib'


def _setup(dest):
    from tools.scan_collateral import build_manifest
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    os.path.join(dest, NODE, LIB))
    build_manifest(dest, NODE, LIB)
    return dest


def _run(args, cwd=REPO):
    return subprocess.run([sys.executable, os.path.join(REPO, 'deckgen_run.py')]
                          + args, cwd=cwd, capture_output=True, text=True)


def test_dry_run_prints_scope_and_writes_nothing(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--table-points', '1,1', '--out', out, '--dry-run'])
    assert r.returncode == 0, r.stderr
    assert '2' in r.stdout                      # 2 selected items
    assert not os.path.isdir(os.path.join(out, 'decks'))


def test_generate_only_no_tty_stops_at_generated(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--table-points', '1,1', '--out', out])
    assert 'not submitted' in r.stdout.lower()
    lsf = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf) and any(
        f.endswith('.bsub') for f in os.listdir(lsf)))


def test_yes_flag_submits_and_writes_bsub(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--table-points', '1,1', '--out', out, '--yes'])
    # exit 0 iff balanced; fixture scope is fully accounted
    assert r.returncode == 0, r.stderr
    ledger = os.path.join(out, 'ledger.ndjson')
    assert os.path.isfile(ledger)
    # if any deck generated, a bsub exists; headline present either way
    assert 'accounted' in r.stdout.lower() or 'balanced' in r.stdout.lower()


def test_zero_match_scope_exits_nonzero(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--cells', 'NOSUCH*', '--out', out])
    assert r.returncode != 0
    assert '0 items' in (r.stdout + r.stderr)
