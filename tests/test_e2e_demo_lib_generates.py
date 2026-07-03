"""e2e proof that core.orchestrate.generate() writes a real, runnable deck.

The N2P_v1.0/test_lib fixture used elsewhere has a stub DFFQ1 netlist ("* body
omitted"), so its orchestrate tests only exercise refusal paths -- generate()
never actually produces a deck there. demo_lib pairs the same collateral
layout with the real, engine-proven AOI22 transistor-level netlist (see
tests/test_deck_assemble.py) so this test can assert on an actual generated
deck on disk.
"""
import os
import shutil

from tools.scan_collateral import build_manifest
from core.orchestrate import generate

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'demo_lib'


def _setup(dest):
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    os.path.join(dest, NODE, LIB))
    build_manifest(dest, NODE, LIB)
    return dest


def test_generate_over_demo_lib_writes_real_deck(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = generate(root, NODE, LIB, out, workers=1,
                   scope={'table_points': [(1, 1)]})

    cov = res['coverage']['summary']
    assert cov['balanced'] is True
    assert cov['generated'] >= 1

    deck_paths = []
    decks_dir = os.path.join(out, 'decks')
    for dirpath, _dirnames, filenames in os.walk(decks_dir):
        for fname in filenames:
            if fname == 'nominal_sim.sp':
                deck_paths.append(os.path.join(dirpath, fname))
    assert deck_paths, 'expected at least one nominal_sim.sp under out/decks/'

    deck_text = open(deck_paths[0], encoding='ascii').read()
    assert 'X1 ' in deck_text
    assert '.end' in deck_text
    assert "CZN ZN 0 'cl'" in deck_text
    assert '$' not in deck_text
