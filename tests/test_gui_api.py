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
    cells = _api_list_cells('N2P_v1.0', 'test_lib')
    cell_names = [c['name'] if isinstance(c, dict) else c for c in cells]
    assert 'DFFQ1' in cell_names


def test_list_lib_types_unknown_node(tmp_path, monkeypatch):
    _setup_collateral(tmp_path, monkeypatch)
    from gui import _api_list_lib_types
    assert _api_list_lib_types('does_not_exist') == []
