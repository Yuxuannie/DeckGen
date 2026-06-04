"""
Stage 2 sensitization against the synthetic LPE fixture. The derived bias must
match the known-correct golden bias (SE=0 selects functional D, SI held) and be
PROVEN -- but derived structurally, never read from the when-string.
"""
import os

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine.types import Arc


def _setup():
    with open(os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt"),
              "r", encoding="ascii") as fh:
        g = stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell="SDFX_LPE_PLACEHOLDER", arc_type="hold",
              rel_pin="CP", rel_dir="rise", constr_pin="D", constr_dir="fall",
              when="notSE_SI", measurement="")
    return g, ccc, arc


def test_p1_proven_and_bias_matches_golden():
    g, ccc, arc = _setup()
    sens = stage2_sensitize.derive(g, arc, ccc)
    assert sens.proven is True
    assert sens.side_biases["SE"].value == 0     # select functional D path
    assert sens.side_biases["SI"].value == 1     # scan held
    assert "CP=0" in sens.clock_phase


def test_p1_independent_of_when_string():
    # Same topology, different/empty when -> still derives SE=0 (proof is structural).
    g, ccc, arc = _setup()
    arc.when = ""
    sens = stage2_sensitize.derive(g, arc, ccc)
    assert sens.proven is True
    assert sens.side_biases["SE"].value == 0
