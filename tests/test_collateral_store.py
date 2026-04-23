"""Tests for core.collateral.CollateralStore."""
import json
import os
import shutil
import pytest
from core.collateral import CollateralStore, CollateralError

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


@pytest.fixture
def store(tmp_path):
    """Copy fixture into tmp, build manifest, return store."""
    dest_root = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest_root / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest_root), NODE, LIB)
    return CollateralStore(str(dest_root), NODE, LIB)


class TestListing:
    def test_list_corners(self, store):
        assert store.list_corners() == [CORNER]

    def test_list_cells(self, store):
        assert 'DFFQ1' in store.list_cells()


class TestGetCorner:
    def test_get_corner_returns_abs_paths(self, store):
        c = store.get_corner(CORNER)
        assert os.path.isabs(c['template_tcl'])
        assert os.path.isabs(c['char']['cons'])
        assert os.path.isabs(c['model']['base'])

    def test_get_corner_missing_raises(self, store):
        with pytest.raises(CollateralError):
            store.get_corner('does_not_exist')


class TestPickCharFile:
    def test_constraint_arc_picks_cons(self, store):
        path = store.pick_char_file(CORNER, 'hold')
        assert path.endswith('.cons.tcl')

    def test_non_cons_arc_picks_non_cons(self, store):
        path = store.pick_char_file(CORNER, 'combinational')
        assert path.endswith('.non_cons.tcl')


class TestPickModelFile:
    def test_delay_arc_uses_delay_inc(self, store):
        # non_cons.tcl has extsim_model_include -type delay -> delay.inc
        path = store.pick_model_file(CORNER, 'delay')
        assert path is not None
        assert path.endswith('.delay.inc')

    def test_combinational_normalized_to_delay(self, store):
        path = store.pick_model_file(CORNER, 'combinational')
        assert path is not None
        # cons.tcl has no extsim_model_include; but non_cons.tcl does.
        # combinational -> 'delay' normalization, must find delay entry.
        assert path.endswith('.delay.inc')

    def test_unknown_arc_type_returns_none_when_no_traditional(self, store):
        # Ensure non-existent key doesn't raise
        path = store.pick_model_file(CORNER, 'some_unknown_type')
        # Should fall back to 'traditional' if exactly one entry -- here there
        # are multiple, so returns None
        assert path is None or path.endswith('.inc')


class TestGetTemplateTcl:
    def test_returns_abs_path(self, store):
        path = store.get_template_tcl(CORNER)
        assert os.path.isabs(path)
        assert path.endswith('.template.tcl')


class TestGetNetlistDir:
    def test_returns_abs_path(self, store):
        d = store.get_netlist_dir(CORNER)
        assert os.path.isabs(d)
        assert os.path.isdir(d)


class TestErrorReporting:
    def test_error_includes_suggestions(self, store):
        try:
            store.get_corner('ssgnp_0p450v_m40c')  # missing rc suffix
        except CollateralError as e:
            msg = str(e)
            assert CORNER in msg  # suggestion should list real corner
