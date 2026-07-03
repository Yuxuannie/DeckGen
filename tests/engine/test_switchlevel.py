"""
Switch-level evaluator against the synthetic LPE fixture (known truth).
Checks combinational inverters resolve, and that with the latch feedback broken
the transparent master node tracks the selected mux input.
"""
import os

from engine import switchlevel
from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc

FIXTURE = os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")


def _graph():
    with open(FIXTURE, "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")


def test_inverters_resolve():
    g = _graph()
    assert switchlevel.evaluate(g, {"SE": 0, "CP": 0, "D": 0, "SI": 0})["seb"] == 1
    assert switchlevel.evaluate(g, {"SE": 1, "CP": 0, "D": 0, "SI": 0})["seb"] == 0
    assert switchlevel.evaluate(g, {"SE": 0, "CP": 0, "D": 0, "SI": 0})["clkb"] == 1
    assert switchlevel.evaluate(g, {"SE": 0, "CP": 1, "D": 0, "SI": 0})["clkb"] == 0


def _broken(g):
    core = {sn.net for sn in stage1_ccc.decompose(g).state_nodes}
    return frozenset(d.name for d in g.devices
                     if d.terminals["g"] in core and d.terminals["d"] in core)


def test_transparent_master_tracks_selected_input():
    g = _graph()
    br = _broken(g)
    # master transparent at CP=0; SE=0 selects D -> ml_a follows D
    assert switchlevel.evaluate(g, {"SE": 0, "CP": 0, "D": 1, "SI": 0}, br)["ml_a"] == 1
    assert switchlevel.evaluate(g, {"SE": 0, "CP": 0, "D": 0, "SI": 1}, br)["ml_a"] == 0
    # SE=1 selects SI -> ml_a follows SI, not D
    assert switchlevel.evaluate(g, {"SE": 1, "CP": 0, "D": 0, "SI": 1}, br)["ml_a"] == 1
