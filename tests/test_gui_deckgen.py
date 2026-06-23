"""
The deck-generation GUI (gui_deckgen.py) is server-rendered: all page-building
and action logic lives in pure functions, so it is testable without the HTTP
layer. These tests exercise the listing helpers, the form renderer, and
run_action for both the report (generator) and the cross-validation (diff)
methods against the fixture collateral. A browser cannot run here -- the HTTP
Handler is a thin wrapper over these functions.
"""
import os
import shutil

import pytest

import gui_deckgen as G

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


@pytest.fixture
def root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    return str(dest)


def test_listing_helpers_walk_the_collateral(root):
    assert NODE in G.list_nodes(root)
    assert LIB in G.list_libs(root, NODE)
    assert CORNER in G.list_corners(root, NODE, LIB)
    cells = G.list_cells(root, NODE, LIB, CORNER)
    assert 'DFFQ1' in cells


def test_listing_helpers_degrade_on_bad_paths(tmp_path):
    # never raise -- return empty so the form can still render
    missing = str(tmp_path / 'no_such_root')
    assert G.list_nodes(missing) == []
    assert G.list_libs(missing, 'x') == []
    assert G.list_corners(missing, 'x', 'y') == []
    assert G.list_cells(missing, 'x', 'y', 'z') == []


def test_render_form_is_valid_html_with_selected_state(root):
    state = {"root": root, "node": NODE, "lib": LIB, "corner": CORNER,
             "cell": "DFFQ1", "method": "diff"}
    form = G.render_form(state)
    assert "<form" in form and "action='/run'" in form
    # the chosen node/corner are pre-selected, the cell is filled, diff is checked
    assert ("value='%s' selected" % NODE) in form
    assert ("value='%s' selected" % CORNER) in form
    assert "value='DFFQ1'" in form
    assert "value='diff' checked" in form
    assert all(ord(c) < 128 for c in form)


def test_page_wraps_form_and_results(root):
    state = {"root": root, "node": NODE, "lib": LIB, "corner": CORNER}
    html = G.page(state, "<p>hello results</p>")
    assert html.lstrip().startswith("<!doctype html")
    assert html.rstrip().endswith("</html>")
    assert "<style>" in html and "--purple" in html
    assert "hello results" in html
    assert all(ord(c) < 128 for c in html)


def test_run_action_generator_returns_report_and_iframe(root):
    state = {"root": root, "node": NODE, "lib": LIB, "corner": CORNER,
             "cell": "DFFQ1", "method": "generator"}
    results, rid = G.run_action(state)
    assert rid is not None
    assert "<iframe" in results and ("id=%s" % rid) in results
    assert "deck_recipe" not in results  # generator deck content stays in report
    # the report was stashed and is renderable, self-contained ASCII HTML
    report_html = G._REPORTS[rid]
    assert report_html.lstrip().startswith("<!") and "DFFQ1" in report_html
    assert all(ord(c) < 128 for c in report_html)


def test_run_action_diff_cross_validates(root):
    state = {"root": root, "node": NODE, "lib": LIB, "corner": CORNER,
             "cell": "DFFQ1", "method": "diff"}
    results, rid = G.run_action(state)
    assert rid is None                       # diff renders inline, no report iframe
    assert "Cross-validation" in results
    # generator reproduces the template byte-for-byte -> all arcs MATCH
    assert "ALL MATCH" in results
    assert "pill MATCH" in results
    assert all(ord(c) < 128 for c in results)


def test_run_action_without_cell_prompts(root):
    state = {"root": root, "node": NODE, "lib": LIB, "corner": CORNER,
             "cell": "", "method": "generator"}
    results, rid = G.run_action(state)
    assert rid is None and "Enter a cell" in results
