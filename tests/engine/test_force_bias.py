"""--force-bias: the override is a CONSTRAINT inside Stage 2's search space, so a
wrong forced bias yields a genuinely DERIVED P1 FAIL that names the competing
capture path (SI when SE is forced to 1), and a forced-but-correct bias still
proves P1 (forcing is orthogonal to correctness). Spec:
docs/superpowers/specs/2026-06-09-force-bias-demo-design.md
"""
import os

import pytest

from engine.config import ENGINE_DIR
from engine.pipeline import run_pipeline_src
from engine.run import parse_force_bias
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine.types import Arc, PStatus


def _setup(force_bias=None):
    with open(os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt"),
              "r", encoding="ascii") as fh:
        src = fh.read()
    g = stage0_parse.parse(src, "SDFX_LPE_PLACEHOLDER")
    ccc = stage1_ccc.decompose(g)
    raw = {"force_bias": force_bias} if force_bias else {}
    arc = Arc(cell="SDFX_LPE_PLACEHOLDER", arc_type="hold",
              rel_pin="CP", rel_dir="rise", constr_pin="D", constr_dir="fall",
              when="notSE_SI", measurement="", raw=raw)
    return src, g, ccc, arc


def test_wrong_forced_bias_fails_p1_and_names_si():
    _, g, ccc, arc = _setup({"SE": 1})
    sens = stage2_sensitize.derive(g, arc, ccc)
    assert sens.proven is False
    assert "SI" in sens.p1_obligation          # the competing live path is named
    assert "FORCED" in sens.p1_obligation
    assert sens.side_biases["SE"].value == 1
    assert "FORCED by user" in sens.side_biases["SE"].reason


def test_forced_equal_to_derived_still_passes():
    _, g, ccc, arc = _setup({"SE": 0})
    sens = stage2_sensitize.derive(g, arc, ccc)
    assert sens.proven is True
    assert sens.side_biases["SE"].value == 0
    assert "FORCED by user" in sens.side_biases["SE"].reason
    assert sens.side_biases["SI"].value == 1   # still derived, still masked


def test_unforced_derivation_unchanged():
    _, g, ccc, arc = _setup()
    sens = stage2_sensitize.derive(g, arc, ccc)
    assert sens.proven is True
    assert sens.side_biases["SE"].value == 0
    assert "FORCED" not in sens.side_biases["SE"].reason


def test_forced_unknown_pin_raises():
    _, g, ccc, arc = _setup({"ZZ": 1})
    with pytest.raises(ValueError) as ei:
        stage2_sensitize.derive(g, arc, ccc)
    assert "ZZ" in str(ei.value)


def test_parse_force_bias():
    assert parse_force_bias(["SE=1", "SI=0"]) == {"SE": 1, "SI": 0}
    assert parse_force_bias(None) == {}
    for bad in ("SE=2", "SE", "=1"):
        with pytest.raises(ValueError):
            parse_force_bias([bad])


def test_end_to_end_verdict_marks_forced_and_fails():
    src, _, _, _ = _setup()
    record = {"cell": "SDFX_LPE_PLACEHOLDER", "arc_type": "hold",
              "rel_pin": "CP", "rel_dir": "rise",
              "constr_pin": "D", "constr_dir": "fall",
              "when": "notSE_SI", "measurement": "",
              "force_bias": {"SE": 1}}
    result = run_pipeline_src(record, src, "* meas placeholder", "* model", "test")
    assert result.verdict.p1.status is PStatus.FAIL
    assert any("FORCED" in line for line in result.verdict.p1.detail)
    assert any("SI" in line for line in result.verdict.p1.detail)
    # the (bad) deck is still assembled, with the forced bias driven
    assert "VSE SE 0 'vdd_value'" in result.deck.text
