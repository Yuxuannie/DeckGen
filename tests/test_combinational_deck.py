"""
End-to-end: a combinational arc now selects the GENERIC combinational delay
template (templates/N2P_v1.0/delay/template_common_inpin_*_delay_*.sp) and builds
a deck that matches the real MCQC N2P combinational deck structure.

Locks the MCQC-parity facts transcribed from real reference decks (OAI2220 /
MUX4 / BUFFND at ssgnp_0p450v_m40c): simple .options, FMC monte .tran, side-pin
V sources on vss_value/vdd_value, C<pin> load cap, meas_delay / half_tt_out /
meas_tt_out, single stdvs_<dir> input edge.
"""
import os
import shutil

import pytest

from core.deck_builder import build_deck
from core.resolver import resolve_all_from_collateral

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
DELAY_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'templates', NODE, 'delay'))


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), NODE, LIB)
    return str(dest)


def _deck(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise', constr_pin='Q', constr_dir='rise',
        probe_pin='Q', node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root)
    info = info[0] if isinstance(info, list) else info
    lines = build_deck(info, slew=('0', '0'), load='0',
                       when=info.get('WHEN'), max_slew=info.get('MAX_SLEW') or '1n')
    return info, '\n'.join(lines)


def test_combinational_selects_generic_delay_template(collateral_root):
    info, _ = _deck(collateral_root)
    assert info['TEMPLATE_DECK_PATH'].endswith(
        'template_common_inpin_rise_delay_rise.sp'), \
        "combinational arc must use the generic delay template, not an MPW fallback"


def test_combinational_deck_matches_mcqc_structure(collateral_root):
    _, text = _deck(collateral_root)

    # FMC: Monte Carlo transient
    assert '.tran 1p 5000n sweep monte=1' in text
    # combinational .options (simpler than MPW; from the real reference deck)
    assert ('.options RUNLVL=6 ACCURATE=1 BRIEF=1 autostop MODSRH=1 '
            'gmindc=1e-15 gmin=1e-15') in text
    assert '.option sampling_method=lhs' in text
    # output load cap named C<pin> (CQ), like real CZ/CZN
    assert "CQ Q 0 'cl'" in text
    # held side pins from WHEN use vss_value/vdd_value params (not literals)
    assert "VSE SE 0 'vss_value'" in text          # !SE -> low
    assert "VSI SI 0 'vdd_value'" in text          # SI  -> high
    # single toggling input edge
    assert "XVCP CP 0 stdvs_rise" in text
    # measurements: input->output delay + output transition (rise: 0.3 -> 0.7)
    assert ("meas_delay trig v(CP) val='vdd_value/2' cross=1 "
            "targ v(Q) val='vdd_value/2' cross=1") in text
    assert ("half_tt_out trig v(Q) val='vdd_value*0.3' cross=1 "
            "targ v(Q) val='vdd_value*0.7' cross=1") in text
    assert "meas_tt_out param='half_tt_out*2'" in text
    # header is a valid comment line
    assert any(ln.startswith('* CELL ') for ln in text.splitlines())
    # nothing left unresolved
    assert '$' not in text


def test_fall_direction_template_thresholds():
    """The fall-output variant drives stdvs_fall and measures 0.7 -> 0.3."""
    p = os.path.join(DELAY_DIR, 'template_common_inpin_fall_delay_fall.sp')
    txt = open(p, encoding='ascii').read()
    assert 'stdvs_fall' in txt
    assert "val='vdd_value*0.7' cross=1 targ v($PROBE_PIN_1) val='vdd_value*0.3'" in txt
    assert '.tran 1p 5000n sweep monte=1' in txt


def test_all_four_direction_templates_exist():
    for rd in ('rise', 'fall'):
        for cd in ('rise', 'fall'):
            p = os.path.join(DELAY_DIR,
                             f'template_common_inpin_{rd}_delay_{cd}.sp')
            assert os.path.isfile(p), f"missing {p}"
