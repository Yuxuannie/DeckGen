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


def test_index_includes_engine_tabs_integrated_as_views():
    # Engine tabs are real view-* siblings driven by the existing showTab(),
    # each with its own cell/corner picker. (Phase-1 has no Core/Engine face
    # toggle yet -- deferred to Phase 2.)
    import gui
    page = gui.HTML_PAGE if isinstance(getattr(gui, "HTML_PAGE", None), str) \
        else gui.build_page()
    for marker in ('id="view-topology"', 'id="view-audit"', 'eng-topo-canvas',
                   'id="engTopoCell"', 'id="engTopoCorner"', 'id="engAuditCorner"',
                   "showTab('topology')", "showTab('audit')"):
        assert marker in page, marker
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
