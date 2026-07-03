"""Missing per-cell HACK delay template -> COMMON delay template fallback.

config/delay_template_rules.get_delay_template() returns a per-cell HACK path
(e.g. delay/hack/template__SDFNQSXGD_inpin_fall_delay_rise.sp) for ~13 cells.
Those hack files do NOT exist in this repo. Before the fix, a combinational arc
on such a cell fell through to the registry resolver, which could mis-select an
MPW template. The resolver must instead fall back to the COMMON delay template
delay/template_common_inpin_{rel_dir}_delay_{constr_dir}.sp (which exists),
keeping the arc combinational.

This test synthesizes a collateral fixture whose cell name + combinational arc
pins/when trigger the SDFNQSXGD hack rule, then asserts the resolver selects the
common combinational template (not an MPW one) and that the deck is combinational.
"""
import os
import shutil

from core.deck_builder import build_deck
from core.resolver import resolve_all_from_collateral
from config.delay_template_rules import get_delay_template
from tools.scan_collateral import build_manifest

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
OLD = 'DFFQ1'
# Name matches the SDFNQSXGD* hack pattern.
NEW = 'SDFNQSXGDHACKCELL'


def _prepare(tmp_path):
    """Copy test_lib into tmp, rename cell to a hack-matching name, and rewire
    the combinational arc so it triggers the SDFNQSXGD hack rule:
    constr(=probe) pin Q/rise, rel_pin CPN/fall, when !SE&SI."""
    root = tmp_path / NEW
    src = os.path.join(FIXTURE_ROOT, NODE, LIB)
    dst = str(root / NODE / LIB)
    shutil.copytree(src, dst)

    for sub in ('Template', 'Netlist'):
        base = os.path.join(dst, sub)
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                p = os.path.join(dirpath, fn)
                txt = open(p, encoding='ascii', errors='replace').read()
                txt = txt.replace(OLD, NEW)
                if sub == 'Template':
                    # Make the combinational arc's related pin CPN/fall so the
                    # SDFNQSXGD hack rule (rel CPN/fall, when !SE&SI) fires.
                    txt = txt.replace('rel_pin      : CP;\n  rel_pin_dir  : rise;\n  when         : "!SE&SI";',
                                      'rel_pin      : CPN;\n  rel_pin_dir  : fall;\n  when         : "!SE&SI";')
                    # Cell pinlist references CP; add CPN so netlist/pin checks pass.
                    txt = txt.replace('VDD VSS CP D Q SE SI',
                                      'VDD VSS CP CPN D Q SE SI')
                open(p, 'w', encoding='ascii').write(txt)
                if OLD in fn:
                    os.rename(p, os.path.join(dirpath, fn.replace(OLD, NEW)))

    build_manifest(str(root), NODE, LIB)
    return str(root)


def test_missing_hack_falls_back_to_common_delay(tmp_path):
    # Sanity: the rule really returns a hack path, and that path is absent.
    hack_rel = get_delay_template(
        cell_name=NEW, arc_type='combinational',
        constr_pin='Q', constr_pin_dir='rise',
        rel_pin='CPN', rel_pin_dir='fall', when='!SE&SI')
    assert hack_rel == 'delay/hack/template__SDFNQSXGD_inpin_fall_delay_rise.sp'
    templates_dir = os.path.join(os.path.dirname(__file__), '..',
                                 'templates', NODE)
    assert not os.path.isfile(os.path.join(templates_dir, hack_rel)), \
        "fixture assumption broken: hack template now exists on disk"

    root = _prepare(tmp_path)
    info = resolve_all_from_collateral(
        cell_name=NEW, arc_type='combinational',
        rel_pin='CPN', rel_dir='fall', constr_pin='Q', constr_dir='rise',
        probe_pin='Q', node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=root)
    info = info[0] if isinstance(info, list) else info

    deck_path = info['TEMPLATE_DECK_PATH']
    assert deck_path, "no template selected"
    assert os.path.basename(deck_path) == \
        'template_common_inpin_fall_delay_rise.sp', \
        f"expected common delay template, got {deck_path}"
    assert os.path.isfile(deck_path)
    assert 'mpw' not in deck_path.lower(), \
        f"mis-selected an MPW template: {deck_path}"

    lines = build_deck(info, slew=('0', '0'), load='0',
                       when=info.get('WHEN'),
                       max_slew=info.get('MAX_SLEW') or '1n')
    text = ''.join(lines)
    assert '.tran 1p 5000n sweep monte=1' in text, \
        "deck is not combinational FMC -- common delay template not used"
