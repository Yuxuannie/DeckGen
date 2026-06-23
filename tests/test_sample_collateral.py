"""
The shipped example collateral (examples/sample_collateral) must stay runnable:
it is the template users copy. This guards against rot -- the inverter's two
combinational arcs generate and cross-validate (generator == template).
"""
import os

import pytest

from tools.deck_diff import run as diff_run

ROOT = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'examples', 'sample_collateral'))
NODE = 'N2P_v1.0'
LIB = 'demo_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
CELL = 'INVD1'


@pytest.fixture(autouse=True)
def _clean_manifest():
    yield
    m = os.path.join(ROOT, NODE, LIB, 'manifest.json')
    if os.path.isfile(m):
        os.remove(m)


def test_sample_inverter_cross_validates():
    rows, ok = diff_run(ROOT, NODE, LIB, CORNER, [CELL], out_path=None)
    assert ok, [r for r in rows if r['status'] != 'MATCH']
    assert len(rows) == 2                      # FR and RF arcs
    assert all(r['status'] == 'MATCH' for r in rows)
