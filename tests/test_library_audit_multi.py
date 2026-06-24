"""Multi-output correctness for the library audit: each arc is assigned to the
output its -vector says toggles, not blindly to output_pins[0].

Half-adder HA (S=A^B, C=A&B): both arcs share rel_pin A but target different
outputs. The audit must produce two rows with distinct outputs S and C, each with
the region the engine derives for THAT output.
"""
import os

import pytest

from core.library_audit import audit_from_paths, _output_from_vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(REPO, "tests", "fixtures", "audit_lib")
TEMPLATE = os.path.join(LIB, "template_multi.tcl")
NETDIR = os.path.join(LIB, "netlist")


class TestOutputFromVector:
    def test_picks_toggling_output(self):
        pinlist = ["A", "B", "S", "C"]
        outs = ["S", "C"]
        assert _output_from_vector(pinlist, "RxRx", outs) == "S"   # S toggles
        assert _output_from_vector(pinlist, "RxxR", outs) == "C"   # C toggles

    def test_none_when_undeterminable(self):
        assert _output_from_vector(["A", "B", "Z"], "", ["Z"]) is None
        assert _output_from_vector(["A", "B", "Z"], "RxR", []) is None
        # length mismatch -> None (caller falls back)
        assert _output_from_vector(["A", "B", "Z"], "RxRx", ["Z"]) is None


@pytest.fixture(scope="module")
def report():
    return audit_from_paths(TEMPLATE, NETDIR)


class TestMultiOutputGrouping:
    def test_two_rows_distinct_outputs(self, report):
        rows = [r for r in report["rows"] if r["cell"] == "HA"]
        assert len(rows) == 2
        assert {r["output"] for r in rows} == {"S", "C"}

    def test_a_to_s_unconditional_match(self, report):
        r = next(r for r in report["rows"]
                 if r["cell"] == "HA" and r["output"] == "S")
        assert r["rel_pin"] == "A"
        assert r["status"] == "MATCH"
        assert {s["label"] for s in r["sensitizing"]} == {"!B", "B"}  # full

    def test_a_to_c_conditional_match(self, report):
        r = next(r for r in report["rows"]
                 if r["cell"] == "HA" and r["output"] == "C")
        assert r["status"] == "MATCH"
        assert {s["label"] for s in r["sensitizing"]} == {"B"}        # only B=1
        assert {x["label"] for x in r["blocked"]} == {"!B"}
