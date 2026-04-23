"""Tests for core.resolver.resolve_all_from_collateral -- end-to-end orchestration."""
import os
import shutil
import pytest
from core.resolver import resolve_all_from_collateral

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), NODE, LIB)
    return str(dest)


def test_resolves_combinational_arc(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root,
        overrides={'index_1_index': 1, 'index_2_index': 1})
    assert info['CELL_NAME'] == 'DFFQ1'
    assert info['ARC_TYPE']  == 'combinational'


def test_include_file_from_extsim_model_include(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root,
        overrides={})
    assert info['INCLUDE_FILE'].endswith('.delay.inc')


def test_vdd_from_corner(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root, overrides={})
    assert info['VDD_VALUE']   == '0.450'
    assert info['TEMPERATURE'] == '-40'


def test_glitch_from_chartcl(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root, overrides={})
    assert info['GLITCH'] == '0.05'


def test_pushout_per_from_chartcl(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root, overrides={})
    assert info['PUSHOUT_PER'] == '0.25'
