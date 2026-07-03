"""Parallel generation must be a drop-in for serial: same rows, same order,
no arcs lost. The per-cell engine cache lives inside each worker (items are
batched by cell), so parallelism never re-parses a cell more than once per
worker and never changes a deck's contents.
"""
import os

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fixture_collateral(tmp_path):
    import shutil
    from tools.scan_collateral import build_manifest
    src = os.path.join(_REPO, "tests", "fixtures", "collateral")
    dest = tmp_path / "collateral"
    shutil.copytree(src, str(dest))
    build_manifest(str(dest), "N2P_v1.0", "test_lib")
    return str(dest)


def _strip(row):
    # deck_path embeds the out_dir, which differs between the two runs; every
    # other field is identity/outcome and must match.
    r = dict(row)
    r.pop("deck_path", None)
    return r


def test_parallel_matches_serial(tmp_path):
    from core import orchestrate
    coll = _fixture_collateral(tmp_path)
    ser = orchestrate.generate(coll, "N2P_v1.0", "test_lib",
                               str(tmp_path / "ser"), workers=1)
    par = orchestrate.generate(coll, "N2P_v1.0", "test_lib",
                               str(tmp_path / "par"), workers=4)

    assert len(par["rows"]) == len(ser["rows"]) == 50
    assert None not in par["rows"]                       # no dropped arcs
    assert [_strip(r) for r in par["rows"]] == [_strip(r) for r in ser["rows"]]


def test_parallel_preserves_no_silent_drop(tmp_path):
    # expected == generated + submitted + generation_error + skipped, on the
    # parallel path too. coverage.build_* enforces this; here we just confirm
    # every work item produced exactly one non-None row in order.
    from core import orchestrate
    coll = _fixture_collateral(tmp_path)
    res = orchestrate.generate(coll, "N2P_v1.0", "test_lib",
                               str(tmp_path / "out"), workers=4)
    rows = res["rows"]
    assert len(rows) == len(res["universe"]) == 50
    assert all(r is not None and r.get("state") for r in rows)


def test_serial_cancel_leaves_no_dropped_arc(tmp_path):
    # A cancelled run must still account for every arc: reached items get their
    # real row, unreached items become skipped/cancelled rows (never dropped).
    # This keeps coverage balanced (expected == generated + error + skipped).
    from core import orchestrate
    coll = _fixture_collateral(tmp_path)
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 5        # let a few items through, then stop

    res = orchestrate.generate(coll, "N2P_v1.0", "test_lib",
                               str(tmp_path / "out"), workers=1,
                               should_cancel=should_cancel)
    rows = res["rows"]
    assert res["cancelled"] is True
    assert len(rows) == 50
    assert None not in rows                               # no arc silently dropped
    assert all(r.get("state") for r in rows)             # every row has an outcome
    cancelled = [r for r in rows if r.get("category") == "cancelled"]
    assert cancelled                                     # some items were skipped
    assert all(r["state"] == "skipped" for r in cancelled)
