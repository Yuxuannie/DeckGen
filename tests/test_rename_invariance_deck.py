"""
Deck rename-invariance: the generated deck must depend only on STRUCTURE
(template.tcl arcs/pins/WHEN + netlist), never on the cell-name pattern.

This mirrors the validation methodology: obfuscate a cell's name to a random
string (so the name carries no pattern), regenerate, and require the deck to be
identical to the original except where the cell name appears literally. A flow
that keys template selection or substitutions off the name pattern would fail.
"""
import os
import shutil

import pytest

from core.deck_builder import build_deck
from core.resolver import resolve_all_from_collateral
from tools.scan_collateral import build_manifest

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
OLD = 'DFFQ1'
NEW = 'ZQ9XRNDCELL7'          # random-looking; carries no recognizable pattern


def _prepare(tmp_path, cell_name):
    """Copy the test_lib collateral into tmp; if cell_name != OLD, obfuscate the
    cell name everywhere (template.tcl + netlist content + netlist filename)."""
    root = tmp_path / cell_name
    src = os.path.join(FIXTURE_ROOT, NODE, LIB)
    dst = str(root / NODE / LIB)
    shutil.copytree(src, dst)
    if cell_name != OLD:
        for sub in ('Template', 'Netlist'):
            base = os.path.join(dst, sub)
            for dirpath, _dirs, files in os.walk(base):
                for fn in files:
                    p = os.path.join(dirpath, fn)
                    txt = open(p, encoding='ascii', errors='replace').read()
                    if OLD in txt:
                        open(p, 'w', encoding='ascii').write(txt.replace(OLD, cell_name))
                    if OLD in fn:
                        os.rename(p, os.path.join(dirpath, fn.replace(OLD, cell_name)))
    build_manifest(str(root), NODE, LIB)
    return str(root)


def _deck(collateral_root, cell_name):
    info = resolve_all_from_collateral(
        cell_name=cell_name, arc_type='combinational',
        rel_pin='CP', rel_dir='rise', constr_pin='Q', constr_dir='rise',
        probe_pin='Q', node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root)
    info = info[0] if isinstance(info, list) else info
    lines = build_deck(info, slew=('0', '0'), load='0',
                       when=info.get('WHEN'), max_slew=info.get('MAX_SLEW') or '1n')
    return info, lines


def test_deck_is_rename_invariant(tmp_path):
    root_orig = _prepare(tmp_path, OLD)
    root_obf = _prepare(tmp_path, NEW)

    info_o, lines_o = _deck(root_orig, OLD)
    info_n, lines_n = _deck(root_obf, NEW)

    # same template selected (structure-driven, not name-driven)
    assert os.path.basename(info_o['TEMPLATE_DECK_PATH']) == \
        os.path.basename(info_n['TEMPLATE_DECK_PATH'])

    # every deck line, EXCLUDING absolute .inc paths, is identical once the cell
    # name is substituted -> the only thing the name changes is the literal name.
    def body(lines):
        return [ln for ln in lines if not ln.lstrip().startswith('.inc')]

    o = [ln.replace(OLD, NEW) for ln in body(lines_o)]
    n = body(lines_n)
    assert o == n, "deck content depends on the cell-name pattern, not just structure"

    # the renamed cell appears literally where expected; the old name is gone
    text_n = ''.join(lines_n)
    assert NEW in text_n and OLD not in text_n.replace(NEW, '')
    assert f"X1 " in text_n and text_n.count(NEW) >= 2   # X1 instance + header


def test_obfuscated_netlist_inc_only_swaps_name(tmp_path):
    """The netlist .inc differs only by the cell name in the filename."""
    root_obf = _prepare(tmp_path, NEW)
    _, lines_n = _deck(root_obf, NEW)
    inc = [ln for ln in lines_n if ln.lstrip().startswith('.inc') and 'Netlist' in ln]
    assert inc and NEW in inc[0] and OLD not in inc[0]
