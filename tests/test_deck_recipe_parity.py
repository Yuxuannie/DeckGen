"""
Step 2 gate: the programmatic generator (core/deck_recipe.build_combinational_deck)
reproduces the template-substitution deck BYTE-FOR-BYTE, for all 4 input/output
direction combinations. This proves the generator codifies the SAME recipe as the
legacy template_*.sp files -- the prerequisite for retiring them.

Name-invariance of the generator follows by transitivity: the generator equals the
template deck here, and tests/test_rename_invariance_deck.py proves the template
deck depends only on structure, not the cell-name pattern.
"""
import os
import shutil

import pytest

from core.deck_builder import build_deck
from core.deck_recipe import build_combinational_deck
from core.resolver import resolve_all_from_collateral

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
DELAY = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'templates', NODE, 'delay'))


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), NODE, LIB)
    return str(dest)


def _resolve(root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational', rel_pin='CP', rel_dir='rise',
        constr_pin='Q', constr_dir='rise', probe_pin='Q', node=NODE, lib_type=LIB,
        corner_name=CORNER, collateral_root=root)
    return info[0] if isinstance(info, list) else info


def _template_lines(info):
    ls = build_deck(info,
                    slew=(info.get('INDEX_1_VALUE') or '0',
                          info.get('INDEX_1_VALUE') or '0'),
                    load=info.get('INDEX_2_VALUE') or '0',
                    when=info.get('WHEN'), max_slew=info.get('MAX_SLEW') or '1n')
    return [ln.rstrip('\n') for ln in ls]


def test_generator_byte_parity_all_directions(collateral_root):
    base = _resolve(collateral_root)
    for rd in ('rise', 'fall'):
        for cd in ('rise', 'fall'):
            info = dict(base)
            info['REL_PIN_DIR'] = rd
            info['CONSTR_PIN_DIR'] = cd
            info['TEMPLATE_DECK_PATH'] = os.path.join(
                DELAY, 'template_common_inpin_%s_delay_%s.sp' % (rd, cd))
            tmpl = _template_lines(info)
            gen = build_combinational_deck(info)
            assert gen == tmpl, (
                'generator != template for inpin_%s_delay_%s' % (rd, cd))


def test_generator_is_fmc_combinational(collateral_root):
    g = '\n'.join(build_combinational_deck(_resolve(collateral_root)))
    assert '.tran 1p 5000n sweep monte=1' in g          # FMC Monte
    assert 'meas_delay' in g and 'meas_tt_out' in g      # fixed char measures
    assert "VSE SE 0 'vss_value'" in g                   # WHEN side pins (params)
    assert "VSI SI 0 'vdd_value'" in g
    assert "CQ Q 0 'cl'" in g                            # C<pin> output load
    assert "XVCP CP 0 stdvs_rise" in g                   # single input edge
    assert all(ord(c) < 128 for c in g)                  # ASCII


def test_generator_fall_output_uses_70_30():
    """A falling output measures 0.7 -> 0.3 (char-fixed); rising uses 0.3 -> 0.7."""
    base = {'HEADER_INFO': '', 'CELL_NAME': 'C', 'NETLIST_PINS': 'A Z',
            'REL_PIN': 'A', 'REL_PIN_DIR': 'rise', 'PROBE_PIN_1': 'Z',
            'CONSTR_PIN': 'A', 'CONSTR_PIN_DIR': 'fall', 'OUTPUT_PINS': 'Z',
            'WHEN': 'NO_CONDITION'}
    g = '\n'.join(build_combinational_deck(base))
    assert "val='vdd_value*0.7' cross=1 targ v(Z) val='vdd_value*0.3'" in g
