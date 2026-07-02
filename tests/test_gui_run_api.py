"""Tests for the GUI Run/Report tab APIs (Phase C-2).

Pure-function seam over core.orchestrate: _api_run_plan / _api_run_generate /
_api_run_status / _api_run_coverage / _api_run_submit. Mirrors test_gui_api.py.
"""
import os

import pytest


def _setup_collateral(tmp_path, monkeypatch):
    """Copy fixture collateral into tmp, generate manifest, point gui at it."""
    import shutil
    from tools.scan_collateral import build_manifest
    fixture_root = os.path.join(
        os.path.dirname(__file__), 'fixtures', 'collateral')
    dest = tmp_path / 'collateral'
    shutil.copytree(fixture_root, str(dest))
    build_manifest(str(dest), 'N2P_v1.0', 'test_lib')
    import gui
    monkeypatch.setattr(gui, '_DEFAULT_COLLATERAL_ROOT', str(dest))
    monkeypatch.setattr(gui.DeckgenHandler, 'COLLATERAL_ROOT', str(dest))
    return str(dest)


def _payload(root, out, **extra):
    p = {'collateral': root, 'node': 'N2P_v1.0', 'lib_type': 'test_lib',
         'out': out, 'table_points': [[1, 1]]}
    p.update(extra)
    return p


def _generate_and_wait(gui, root, out, **extra):
    tid = gui._api_run_generate(_payload(root, out, **extra))['task_id']
    th = gui._RUN_TASKS[tid]['_thread']
    th.join(timeout=60)
    assert not th.is_alive(), 'generate worker did not finish'
    return tid


# --------------------------------------------------------------------------
# plan (dry-run scope preview)
# --------------------------------------------------------------------------

def test_run_plan_previews_scope(tmp_path, monkeypatch):
    root = _setup_collateral(tmp_path, monkeypatch)
    import gui
    res = gui._api_run_plan(_payload(root, str(tmp_path / 'run')))
    assert res['expected'] == 2
    assert 'walltime_est' in res


def test_run_plan_empty_selection_reports_error(tmp_path, monkeypatch):
    root = _setup_collateral(tmp_path, monkeypatch)
    import gui
    res = gui._api_run_plan(_payload(root, str(tmp_path / 'run'),
                                     table_points=[[99, 99]]))
    # (99,99) is out-of-grid, not empty -> still 2 rows (marked no_such_point),
    # so use a cell glob that matches nothing to force SelectionEmpty.
    res = gui._api_run_plan(_payload(root, str(tmp_path / 'run'),
                                     cells=['NOSUCHCELL*']))
    assert res.get('selection_empty') is True
    assert 'error' in res


# --------------------------------------------------------------------------
# generate -> status -> coverage
# --------------------------------------------------------------------------

def test_run_generate_then_status_balanced(tmp_path, monkeypatch):
    root = _setup_collateral(tmp_path, monkeypatch)
    import gui
    tid = _generate_and_wait(gui, root, str(tmp_path / 'run'))
    st = gui._api_run_status(tid)
    assert st['status'] == 'generated'
    assert st['total'] == 2 and st['progress'] == 2
    assert st['coverage']['summary']['balanced'] is True
    assert st['coverage']['summary']['expected'] == 2


def test_run_coverage_returns_report(tmp_path, monkeypatch):
    root = _setup_collateral(tmp_path, monkeypatch)
    import gui
    tid = _generate_and_wait(gui, root, str(tmp_path / 'run'))
    cov = gui._api_run_coverage(tid)
    for k in ('expected', 'generated', 'submitted', 'generation_error',
              'skipped', 'balanced'):
        assert k in cov['summary']


def test_run_status_and_coverage_are_json_serializable(tmp_path, monkeypatch):
    # The coverage report's matrix uses tuple keys / tuple lists; the HTTP layer
    # json.dumps() them, so the run APIs must return JSON-safe structures.
    import json
    root = _setup_collateral(tmp_path, monkeypatch)
    import gui
    tid = _generate_and_wait(gui, root, str(tmp_path / 'run'))
    json.dumps(gui._api_run_status(tid))
    json.dumps(gui._api_run_coverage(tid))
    json.dumps(gui._api_run_plan(_payload(root, str(tmp_path / 'run'))))


def test_run_status_unknown_task(tmp_path, monkeypatch):
    _setup_collateral(tmp_path, monkeypatch)
    import gui
    assert 'error' in gui._api_run_status('deadbeef')
    assert 'error' in gui._api_run_coverage('deadbeef')
    assert 'error' in gui._api_run_submit('deadbeef')


# --------------------------------------------------------------------------
# submit confirm gate
# --------------------------------------------------------------------------

def test_run_submit_nothing_to_submit(tmp_path, monkeypatch):
    # DFFQ1 fixture generates 0 decks (both work items combinational errors),
    # so submit must honestly refuse -- the confirm gate has nothing to send.
    root = _setup_collateral(tmp_path, monkeypatch)
    import gui
    tid = _generate_and_wait(gui, root, str(tmp_path / 'run'))
    res = gui._api_run_submit(tid)
    assert res.get('nothing_to_submit') is True
    assert 'error' in res


def test_run_submit_shapes_arrays_and_bjobs(tmp_path, monkeypatch):
    # Happy submit path shaping: fixture cannot generate a deck, so stub
    # orchestrate.submit with a real-shaped result and assert the API shapes it
    # (coverage + arrays + PEND-only bjobs from the real bjobs_snapshot).
    root = _setup_collateral(tmp_path, monkeypatch)
    import gui
    import core.orchestrate as orch
    tid = _generate_and_wait(gui, root, str(tmp_path / 'run'))
    fake = {
        'run_dir': gui._RUN_TASKS[tid]['out_dir'],
        'universe': [], 'rows': [],
        'coverage': {'summary': {'submitted': 3, 'balanced': True,
                                 'expected': 3}},
        'arrays': {'c1': {'script': 's', 'manifest': 'm', 'n_jobs': 3}},
    }
    monkeypatch.setattr(orch, 'submit', lambda *a, **k: fake)
    res = gui._api_run_submit(tid)
    assert res['coverage']['summary']['submitted'] == 3
    assert res['arrays']['c1']['n_jobs'] == 3
    assert res['bjobs'] and all('PEND' in l for l in res['bjobs'])
    assert gui._api_run_status(tid)['status'] == 'submitted'


# --------------------------------------------------------------------------
# view fragments + assembled page
# --------------------------------------------------------------------------

def test_run_tab_fragment_structure():
    import gui_engine_views as v
    html = v.run_tab_html()
    for hook in ('id="view-run"', 'id="runCorner"', 'id="run-summary"',
                 'id="run-triage"', 'id="runGenerateBtn"', 'id="runSubmitBtn"'):
        assert hook in html, hook
    js = v.run_js()
    for fn in ('runGenerate', 'runPoll', 'runSubmit', 'runRenderCoverage'):
        assert fn in js, fn
    (html + js).encode('ascii')


def test_run_tab_in_assembled_page():
    import gui
    pg = gui.HTML_PAGE
    for tok in ('view-run', 'runGenerate', 'runSubmit', "showTab('run')"):
        assert tok in pg, tok
