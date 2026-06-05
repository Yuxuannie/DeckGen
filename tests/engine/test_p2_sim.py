"""
P2 simulation path: .mt0 parsing, deck generation, and the measured-vs-derived
verdict (run via an existing .mt0 so no hspice is needed in CI).
"""
import os

from engine.config import ENGINE_DIR
from engine.mt0 import parse_mt0
from engine.p2_deck import build as build_p2
from engine.sim import run_p2
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize, stage3_initialize
from engine.types import Arc


def _setup():
    with open(os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt"),
              "r", encoding="ascii") as fh:
        g = stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")
    ccc = stage1_ccc.decompose(g)
    arc = Arc("SDFX_LPE_PLACEHOLDER", "hold", "CP", "rise", "D", "fall", "notSE_SI", "")
    sens = stage2_sensitize.derive(g, arc, ccc)
    init = stage3_initialize.derive(g, ccc, arc, sens)
    return g, ccc, arc, sens, init


# ---- mt0 parser ----
def test_mt0_skips_title_and_aligns():
    txt = ("$DATA1 SOURCE='HSPICE'\n.TITLE 'x'\n"
           "   p2_ml_a_1   p2_ml_b_1   alter#\n"
           "   4.4000E-01  1.0000E-02  1.0000E+00\n")
    d = parse_mt0(txt)
    assert abs(d["p2_ml_a_1"] - 0.44) < 1e-6
    assert abs(d["p2_ml_b_1"] - 0.01) < 1e-6


def test_mt0_failed_measure_is_none():
    txt = "  p2_x  alter#\n  failed  1.0\n"
    assert parse_mt0(txt)["p2_x"] is None


# ---- deck ----
def test_p2_deck_reuses_golden_inc_and_probes():
    g, ccc, arc, sens, init = _setup()
    text, mmap = build_p2(arc, sens, init, init.probes)
    assert ".hold.inc" in text and "std_wv_c651.spi" in text   # golden collateral
    assert "VSE SE 0" in text and "VSI SI 0" in text            # sensitization
    assert all(f".meas tran {nm}" in text for nm in mmap.values())


# ---- verdict via existing mt0 ----
def _write_mt0(tmp, vals):
    names = " ".join(v.split("=")[0] for v in vals) + " alter#"
    row = " ".join(v.split("=")[1] for v in vals) + " 1.0"
    p = os.path.join(tmp, "x.mt0")
    with open(p, "w") as fh:
        fh.write(f"$DATA1\n  {names}\n  {row}\n")
    return p


def test_p2_pass(tmp_path):
    g, ccc, arc, sens, init = _setup()
    # required: ml_a=1, ml_b=0, sl_a=0, sl_b=1 -> voltages above/below 0.225
    mt0 = _write_mt0(str(tmp_path), ["p2_ml_a_1=0.44", "p2_ml_b_1=0.01",
                                     "p2_sl_a_1=0.01", "p2_sl_b_1=0.44"])
    res = run_p2(arc, ccc, sens, init, str(tmp_path), mt0_path=mt0)
    assert res.ran and res.passed


def test_p2_fail_on_wrong_node(tmp_path):
    g, ccc, arc, sens, init = _setup()
    mt0 = _write_mt0(str(tmp_path), ["p2_ml_a_1=0.01", "p2_ml_b_1=0.01",  # ml_a wrong
                                     "p2_sl_a_1=0.01", "p2_sl_b_1=0.44"])
    res = run_p2(arc, ccc, sens, init, str(tmp_path), mt0_path=mt0)
    assert res.ran and not res.passed
