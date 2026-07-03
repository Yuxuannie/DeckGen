"""
Step 3 gate: the two deck-generation paths (template substitution vs the
programmatic generator) produce identical decks for every combinational arc of a
cell -- zero diff. This is the cross-validation that justifies retiring the
per-design template_*.sp files.
"""
import os
import shutil

import pytest

from tools.deck_diff import diff_cell, run

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


def test_template_and_generator_agree(collateral_root):
    rows = diff_cell(collateral_root, NODE, LIB, CORNER, 'DFFQ1')
    assert rows, "no combinational arcs found to diff"
    for r in rows:
        assert r['status'] == 'MATCH', \
            "%s: %s\n%s" % (r['arc'], r['status'], r['diff'])


def test_run_reports_match_and_exit_ok(tmp_path, collateral_root):
    out = str(tmp_path / 'diffs.txt')
    rows, ok = run(collateral_root, NODE, LIB, CORNER, ['DFFQ1'], out)
    assert ok is True                       # zero diff -> success
    assert os.path.isfile(out)
    text = open(out, encoding='ascii').read()
    assert 'MATCH' in text
    assert all(ord(c) < 128 for c in text)
