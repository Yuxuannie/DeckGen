"""
MVP end-to-end: tools/gen_cell_report.run(cell) enumerates the cell's
combinational arcs, generates an FMC deck for each, and emits an interactive
report.html. Smallest verifiable model of the production flow.
"""
import os
import shutil

import pytest

from tools.gen_cell_report import run

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    return str(dest)


def test_mvp_cell_to_decks_and_report(tmp_path, collateral_root):
    out = str(tmp_path / 'out')
    report = run(collateral_root, NODE, LIB, CORNER, 'DFFQ1', out)

    # at least one combinational arc generated OK, none failed
    s = report['summary']
    assert s['total'] >= 1 and s['ok'] >= 1 and s['fail'] == 0

    # a deck file was written and is a combinational FMC deck
    deck_dir = os.path.join(out, 'DFFQ1')
    decks = [f for f in os.listdir(deck_dir) if f.endswith('.sp')]
    assert decks, "no deck written"
    deck = open(os.path.join(deck_dir, decks[0]), encoding='ascii').read()
    assert '.tran 1p 5000n sweep monte=1' in deck
    assert deck.lstrip().startswith('***')

    # report.html exists, is self-contained, ASCII, and embeds the result
    html_path = os.path.join(out, 'report.html')
    assert os.path.isfile(html_path)
    html = open(html_path, encoding='ascii').read()
    assert html.lstrip().startswith('<!') and html.rstrip().endswith('</html>')
    assert '<style' in html and '<script' in html
    assert 'DFFQ1' in html
    assert all(ord(c) < 128 for c in html)
