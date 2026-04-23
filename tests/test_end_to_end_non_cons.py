"""End-to-end: generate one non-cons deck from the fixture collateral.

Verifies that resolve_all_from_collateral + deck_builder produce a complete
SPICE deck using a real template (from templates/N2P_v1.0/mpw/) with
MCQC-parity substitutions.
"""
import os
import shutil
import pytest
from core.deck_builder import build_deck
from core.resolver import resolve_all_from_collateral

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
DECKGEN_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE = os.path.join(
    DECKGEN_ROOT, 'templates', 'N2P_v1.0', 'mpw',
    'template__CP__rise__fall__1.sp')


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), NODE, LIB)
    return str(dest)


def test_generates_deck_with_substitutions(collateral_root):
    """Build a combinational deck; verify no $VAR placeholders survive."""
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root,
        overrides={'index_1_index': 1, 'index_2_index': 1})

    # Inject the template path manually for this smoke test
    info['TEMPLATE_DECK_PATH'] = TEMPLATE

    lines = build_deck(info, slew=('0.05n', '0.05n'), load='0.5p',
                       when=info['WHEN'], max_slew=info['MAX_SLEW'])
    text = '\n'.join(lines)

    # No unresolved placeholders for MCQC-parity fields
    for placeholder in ('$CELL_NAME', '$VDD_VALUE', '$TEMPERATURE',
                         '$INCLUDE_FILE', '$WAVEFORM_FILE',
                         '$GLITCH', '$PUSHOUT_PER'):
        assert placeholder not in text, \
            f"{placeholder} still present in generated deck"

    # Known values are present
    assert 'DFFQ1'   in text
    assert '0.450'   in text
    assert '-40'     in text
