import os
from core.measurement.mine import mine, validate

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _check(subdir, n):
    d = os.path.join(_REPO, "templates/N2P_v1.0", subdir)
    g = mine(d)
    rep = validate(d, g)
    assert rep["total"] == n
    assert rep["reproduced"] == n, rep["mismatches"][:2]
    assert rep["coverage"] == 100.0
    assert rep["mismatches"] == []


def test_roundtrip_delay():
    _check("delay", 4)


def test_roundtrip_mpw():
    _check("mpw", 63)
