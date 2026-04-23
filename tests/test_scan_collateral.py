"""Tests for tools.scan_collateral -- manifest generator."""
import json
import os
import pytest
from tools.scan_collateral import scan_one, build_manifest

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'


def test_scan_one_returns_manifest_dict():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    assert manifest['schema_version'] == 1
    assert manifest['node'] == NODE
    assert manifest['lib_type'] == LIB


def test_scan_one_finds_corner():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    assert 'ssgnp_0p450v_m40c_cworst_CCworst_T' in manifest['corners']


def test_scan_one_corner_fields():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['process']     == 'ssgnp'
    assert c['vdd']         == '0.450'
    assert c['temperature'] == '-40'
    assert c['rc_type']     == 'cworst_CCworst_T'


def test_scan_one_char_cons_and_non_cons_found():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['char']['cons'].endswith('.cons.tcl')
    assert c['char']['non_cons'].endswith('.non_cons.tcl')
    assert c['char']['combined'] is None


def test_scan_one_model_files():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    m = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']['model']
    assert m['base'].endswith('.inc')
    assert m['delay'].endswith('.delay.inc')
    assert m['hold'].endswith('.hold.inc')


def test_scan_one_template_tcl():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['template_tcl'].endswith('.template.tcl')


def test_scan_one_netlist_dir():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['netlist_dir'] == 'Netlist/LPE_cworst_CCworst_T_m40c'


def test_scan_one_finds_cell():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    assert 'DFFQ1' in manifest['cells']
    assert 'LPE_cworst_CCworst_T_m40c' in manifest['cells']['DFFQ1']


def test_build_manifest_writes_file(tmp_path):
    # Copy fixture into tmp so we don't write into the real fixture dir
    import shutil
    dest = tmp_path / 'collateral' / NODE / LIB
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB), str(dest))
    path = build_manifest(str(tmp_path / 'collateral'), NODE, LIB)
    assert os.path.isfile(path)
    with open(path) as f:
        data = json.load(f)
    assert data['node'] == NODE
