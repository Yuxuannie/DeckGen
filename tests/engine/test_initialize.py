"""
Stage 3 initialization (derive-only) against the synthetic LPE fixture.
Checks the master pre-edge state is evaluated + complementary, the slave is a
complementary pair, probes are real hierarchical nodes, and a pre-cycle is planned.
"""
import os

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize, stage3_initialize
from engine.types import Arc


def _setup():
    with open(os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt"),
              "r", encoding="ascii") as fh:
        g = stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell="SDFX_LPE_PLACEHOLDER", arc_type="hold",
              rel_pin="CP", rel_dir="rise", constr_pin="D", constr_dir="fall",
              when="notSE_SI", measurement="")
    sens = stage2_sensitize.derive(g, arc, ccc)
    return g, ccc, arc, sens


def test_master_state_evaluated_and_complementary():
    g, ccc, arc, sens = _setup()
    init = stage3_initialize.derive(g, ccc, arc, sens)
    ml = {sn.net: init.required_state[sn.net].value
          for sn in ccc.state_nodes if sn.role == "master"}
    assert set(ml.values()) == {0, 1}           # complementary pair, fully resolved
    assert ml["ml_a"] == 1 and ml["ml_b"] == 0  # constr_dir=fall -> captured 1 at written node


def test_slave_pair_complementary():
    g, ccc, arc, sens = _setup()
    init = stage3_initialize.derive(g, ccc, arc, sens)
    sl = {sn.net: init.required_state[sn.net].value
          for sn in ccc.state_nodes if sn.role == "slave"}
    assert set(sl.values()) == {0, 1}           # tentative but complementary


def test_probes_and_precycle():
    g, ccc, arc, sens = _setup()
    init = stage3_initialize.derive(g, ccc, arc, sens)
    assert len(init.probes) == 4
    assert all(p.startswith("x1.") for p in init.probes)
    assert init.precycle_count.value >= 1
    assert all(d.reason and d.stage == "S3.init" for d in init.required_state.values())
