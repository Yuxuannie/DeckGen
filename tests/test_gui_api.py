"""Tests for new GUI collateral APIs."""
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
    # Patch the module-level default
    import gui
    monkeypatch.setattr(gui, '_DEFAULT_COLLATERAL_ROOT', str(dest))
    monkeypatch.setattr(gui.DeckgenHandler, 'COLLATERAL_ROOT', str(dest))
    return str(dest)


def test_list_nodes(tmp_path, monkeypatch):
    _setup_collateral(tmp_path, monkeypatch)
    from gui import _api_list_nodes
    nodes = _api_list_nodes()
    assert 'N2P_v1.0' in nodes


def test_list_lib_types(tmp_path, monkeypatch):
    _setup_collateral(tmp_path, monkeypatch)
    from gui import _api_list_lib_types
    libs = _api_list_lib_types('N2P_v1.0')
    assert 'test_lib' in libs


def test_list_corners(tmp_path, monkeypatch):
    _setup_collateral(tmp_path, monkeypatch)
    from gui import _api_list_corners
    corners = _api_list_corners('N2P_v1.0', 'test_lib')
    assert 'ssgnp_0p450v_m40c_cworst_CCworst_T' in corners


def test_list_cells(tmp_path, monkeypatch):
    _setup_collateral(tmp_path, monkeypatch)
    from gui import _api_list_cells
    result = _api_list_cells('N2P_v1.0', 'test_lib')
    cells = result.get('cells', result) if isinstance(result, dict) else result
    cell_names = [c['name'] if isinstance(c, dict) else c for c in cells]
    assert 'DFFQ1' in cell_names


def test_list_lib_types_unknown_node(tmp_path, monkeypatch):
    _setup_collateral(tmp_path, monkeypatch)
    from gui import _api_list_lib_types
    assert _api_list_lib_types('does_not_exist') == []


def test_engine_views_css_tokens_present():
    import gui_engine_views as v
    css = v.CSS_TOKENS + v.CSS_COMPONENTS
    for tok in ("--bg", "--surface", "--accent", "--border", "--text"):
        assert tok in css
    for cls in (".chip-pass", ".chip-fail", ".chip-stub", ".chip-error"):
        assert cls in css
    css.encode("ascii")


def test_topology_tab_fragment_structure():
    import gui_engine_views as v
    html = v.topology_tab_html()
    # eng-topo-verdict renamed to eng-topo-obl in the pin-picker redesign (same intent)
    for hook in ('id="eng-topo-canvas"', 'id="eng-topo-obl"',
                 'id="eng-topo-trace"', "eng-legend"):
        assert hook in html
    js = v.engine_js()
    for fn in ("engTopology", "engPanZoom", "engRenderTopo"):
        assert fn in js
    (html + js).encode("ascii")


def test_audit_tab_fragment_structure():
    import gui_engine_views as v
    html = v.audit_tab_html()
    for hook in ('id="eng-audit-summary"', 'id="eng-audit-rows"',
                 'id="eng-audit-csv"'):
        assert hook in html
    assert "engAudit" in v.engine_js()
    (html + v.engine_js()).encode("ascii")


def test_engine_topology_via_present_layer():
    import os
    import core.engine_present as ep
    sdfx = os.path.join(os.path.dirname(__file__), "..", "engine",
                        "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
    res = ep.topology_view(sdfx, "SDFX_LPE_PLACEHOLDER", when="notSE_SI")
    assert res["status"] == "OK" and "svg" in res and res["p1"]["status"] == "PASS"


def test_index_audit_first_nav_after_redesign():
    # 2026-06-24 redesign: audit-first nav. The Audit (combinational) workspace is
    # the default view; Explore/Direct are demoted to "Decks"; the Validate and old
    # sequential-Audit nav tabs are removed (their view divs may remain as hidden,
    # non-nav siblings). Topology is embedded in the per-arc detail, not a tab.
    import gui
    page = gui.HTML_PAGE if isinstance(getattr(gui, "HTML_PAGE", None), str) \
        else gui.build_page()
    for marker in ('id="view-comb-audit"', 'id="engCAudCorner"', 'id="ca-detail"',
                   'id="ca-d-svg"', "showTab('comb-audit')", "showTab('explore')"):
        assert marker in page, marker
    # the retired tabs are no longer reachable from the nav bar
    assert "showTab('validate')" not in page
    assert "showTab('topology')" not in page
    page.encode('ascii')


def test_topology_tab_has_pin_pickers():
    import gui_engine_views as v
    html = v.topology_tab_html()
    for hook in ('id="engTopoCell"', 'id="engTopoClk"', 'id="engTopoData"',
                 'id="engTopoCorner"', 'id="eng-topo-canvas"',
                 'id="eng-topo-bias"', 'id="eng-topo-struct"'):
        assert hook in html, hook
    js = v.engine_js()
    for fn in ('engTopoLoadCell', 'engTopology', 'engRenderTopo', 'engPinGuess',
               'engAudit', 'engAuditArcs'):
        assert fn in js, fn
    (html + js).encode('ascii')


def test_comb_audit_fragments_present():
    import gui_engine_views as v
    assert 'view-comb-audit' in v.comb_audit_tab_html()
    assert 'engCombAudit' in v.comb_audit_js()
    assert 'ca-cohort' in v.CSS_COMPONENTS


def test_comb_audit_in_assembled_page():
    import gui
    pg = gui.HTML_PAGE
    for tok in ('view-comb-audit', 'engCombAudit', 'engArcPick', 'engRenderDetail'):
        assert tok in pg
    assert ">Audit<" in pg            # tab relabeled Library Audit -> Audit


def test_comb_audit_wrapper_runs_over_collateral(tmp_path, monkeypatch):
    # The CollateralStore-backed airgap entry point must resolve template + netlist
    # and run without crashing, returning the cohort report shape. The DFFQ1 fixture
    # has no combinational arcs, so this is a wiring smoke (verdict logic is covered
    # by tests/test_library_audit.py against audit_from_paths).
    root = _setup_collateral(tmp_path, monkeypatch)
    from core.collateral import CollateralStore
    from core.library_audit import audit_combinational_library
    corner = CollateralStore(root, 'N2P_v1.0', 'test_lib').list_corners()[0]
    r = audit_combinational_library(root, 'N2P_v1.0', 'test_lib', corner)
    assert set(['summary', 'rows', 'cohorts', 'context']).issubset(r.keys())
    assert set(['flagged', 'trust']).issubset(r['cohorts'].keys())
    assert 'arcs' in r['summary']
