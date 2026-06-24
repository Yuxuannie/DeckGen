"""core/library_audit.py -- library-scale combinational WHEN-derivation audit.

Runs the engine audit over the synthetic audit_lib fixture, which is built to
exercise every verdict class exactly once:
  AIOI21 (A1,A2,B) -> MATCH      (engine region == kit -when, incl. unconditional)
  AOI22  (A1)      -> DIVERGENCE (kit names blocked A2&B1&B2, omits A2&B1&!B2)
  AOAI   (A4)      -> UNSUPPORTED-WHEN (kit -when contains OR)
  GHOST  (A)       -> ERROR      (declared in template, no netlist .spi -> isolation)
"""
import os

import pytest

from core.library_audit import audit_from_paths

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(REPO, "tests", "fixtures", "audit_lib")
TEMPLATE = os.path.join(LIB, "template.tcl")
NETDIR = os.path.join(LIB, "netlist")


@pytest.fixture(scope="module")
def report():
    return audit_from_paths(TEMPLATE, NETDIR)


def _row(report, cell, rel):
    for r in report["rows"]:
        if r["cell"] == cell and r["rel_pin"] == rel:
            return r
    raise AssertionError("no row for %s/%s" % (cell, rel))


class TestSummary:
    def test_counts(self, report):
        s = report["summary"]
        assert s["arcs"] == 6           # AIOI21 x3 + AOI22 + AOAI + GHOST
        assert s["match"] == 3
        assert s["divergence"] == 1
        assert s["unsupported"] == 1
        assert s["error"] == 1
        assert s["flagged"] == 3

    def test_cohort_split(self, report):
        flagged = {(r["cell"], r["rel_pin"]) for r in report["cohorts"]["flagged"]}
        trust = {(r["cell"], r["rel_pin"]) for r in report["cohorts"]["trust"]}
        assert ("AOI22", "A1") in flagged
        assert ("AOAI", "A4") in flagged
        assert ("GHOST", "A") in flagged
        assert trust == {("AIOI21", "A1"), ("AIOI21", "A2"), ("AIOI21", "B")}


class TestVerdicts:
    def test_aioi21_all_match(self, report):
        for rel in ("A1", "A2", "B"):
            assert _row(report, "AIOI21", rel)["status"] == "MATCH"

    def test_aioi21_b_region_and_sig_present(self, report):
        b = _row(report, "AIOI21", "B")
        sens = {s["label"] for s in b["sensitizing"]}
        assert sens == {"!A1&!A2", "!A1&A2", "A1&!A2"}
        assert {x["label"] for x in b["blocked"]} == {"A1&A2"}
        assert all(s["sig"] for s in b["sensitizing"])     # SIG surfaced
        assert b["needs_split"] is True

    def test_aoi22_divergence_names_states(self, report):
        r = _row(report, "AOI22", "A1")
        assert r["status"] == "DIVERGENCE"
        assert "A2&B1&B2" in r["extra"]      # kit marked a blocked state
        assert "A2&B1&!B2" in r["missing"]   # kit omitted a real sensitizing state

    def test_aoai_unsupported(self, report):
        assert _row(report, "AOAI", "A4")["status"] == "UNSUPPORTED-WHEN"

    def test_ghost_error_isolated(self, report):
        r = _row(report, "GHOST", "A")
        assert r["status"] == "ERROR"
        assert "netlist" in r["detail"].lower()


class TestImportanceSort:
    def test_flagged_sorted_above_trust(self, report):
        rows = report["rows"]
        last_flagged = max(i for i, r in enumerate(rows)
                           if r["status"] != "MATCH")
        first_match = min(i for i, r in enumerate(rows)
                          if r["status"] == "MATCH")
        assert last_flagged < first_match

    def test_divergence_is_first(self, report):
        assert report["rows"][0]["status"] == "DIVERGENCE"


def test_progress_callback_fires_per_arc():
    calls = []
    audit_from_paths(TEMPLATE, NETDIR,
                     progress=lambda done, total, cell, status: calls.append((done, total, status)))
    assert calls, "progress callback never fired"
    dones = [c[0] for c in calls]
    assert dones == sorted(dones)          # monotonic increasing
    assert calls[-1][0] == calls[-1][1]    # last call: done == total
    assert calls[-1][1] == 6               # 6 arcs in the fixture
