import os
import shutil

import pytest

from tools.scan_collateral import build_manifest
from core.collateral import CollateralStore
from core.orchestrate import (format_arc_id, discover, wi_universe_tuple,
                              SelectionEmpty)
from core.parsers.arc import parse_arc_identifier

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


def _setup(dest):
    src = os.path.join(FIXTURE_ROOT, NODE, LIB)
    dst = os.path.join(dest, NODE, LIB)
    shutil.copytree(src, dst)
    build_manifest(dest, NODE, LIB)
    return dest


def _manifest_and_tcl(root):
    import json
    store = CollateralStore(root, NODE, LIB, skip_autoscan=True)
    mpath = os.path.join(root, NODE, LIB, 'manifest.json')
    manifest = json.load(open(mpath, encoding='ascii'))
    tcl_by_corner = {c: store.get_corner(c)['template_tcl']
                     for c in manifest['corners']}
    return manifest, tcl_by_corner


def test_format_arc_id_roundtrips_combinational():
    aid = format_arc_id('combinational', 'DFFQ1', 'Q', 'rise', 'CP', 'rise',
                        '!SE&SI', 3, 2)
    assert aid == 'combinational_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2'
    p = parse_arc_identifier(aid)
    assert (p['arc_type'], p['cell_name'], p['probe_pin'], p['rel_pin'],
            p['i1'], p['i2']) == ('combinational', 'DFFQ1', 'Q', 'CP', 3, 2)
    assert p['when'] == '!SE&SI'
    assert p['probe_dir'] == 'rise'
    assert p['rel_dir'] == 'rise'


def test_format_arc_id_no_condition():
    aid = format_arc_id('hold', 'DFFQ1', 'Q', 'fall', 'CP', 'rise',
                        'NO_CONDITION', 1, 1)
    assert aid == 'hold_DFFQ1_Q_fall_CP_rise_NO_CONDITION_1_1'
    assert parse_arc_identifier(aid)['when'] == 'NO_CONDITION'


def test_discover_all_points_two_arcs_times_grid(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope=None)
    # 2 arcs x 25 LUT points x 1 corner
    assert len(items) == 50
    assert {wi['arc_type'] for wi in items} == {'combinational', 'hold'}
    assert all(wi['corner'] == CORNER for wi in items)
    assert all(wi['skip'] is None for wi in items)


def test_discover_table_points_origin_only(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope={'table_points': [(1, 1)]})
    assert len(items) == 2
    assert {wi_universe_tuple(wi) for wi in items} == {
        ('DFFQ1', 'combinational', 1, 1, CORNER),
        ('DFFQ1', 'hold', 1, 1, CORNER)}


def test_discover_arcs_per_cell_one(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl,
                     scope={'arcs_per_cell': 1, 'table_points': [(1, 1)]})
    assert len(items) == 1  # first arc of DFFQ1 only


def test_discover_table_points_int_first_n(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope={'table_points': 3})
    # 3 points per arc x 2 arcs
    assert len(items) == 6
    combo = sorted((wi['i1'], wi['i2']) for wi in items
                   if wi['arc_type'] == 'combinational')
    assert combo == [(1, 1), (1, 2), (1, 3)]  # row-major first 3


def test_discover_no_such_point_is_skipped_not_dropped(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope={'table_points': [(99, 99)]})
    assert len(items) == 2               # accounted, not dropped
    assert all(wi['skip'] == 'no_such_point' for wi in items)


def test_discover_cells_glob_nonmatch_raises_empty(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    with pytest.raises(SelectionEmpty):
        discover(manifest, tcl, scope={'cells': ['NOSUCH*']})


def test_discover_corners_filter_nonmatch_raises_empty(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    with pytest.raises(SelectionEmpty):
        discover(manifest, tcl, scope={'corners': ['ffgnp_0p900v_125c_x']})
