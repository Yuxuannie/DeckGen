import glob
import os
from core.measurement.mine import mine, validate
from core.measurement.regions import partition

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


def test_conservation_mpw():
    """Regression guard: every source line must land in exactly one bucket.
    This catches any future classify_line divergence or unhandled line type."""
    d = os.path.join(_REPO, "templates/N2P_v1.0/mpw")
    for path in sorted(glob.glob(os.path.join(d, "*.sp"))):
        text = open(path, encoding="ascii", errors="replace").read()
        p = partition(text)
        total = sum(len(v) for v in p.values())
        assert total == len(text.splitlines()), (
            "conservation failed for %s: %d classified != %d source lines"
            % (os.path.basename(path), total, len(text.splitlines()))
        )
