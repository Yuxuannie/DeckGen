"""
P2 differential simulation path: .mt0 parsing, deck generation, and the
master-tracks-D / slave-holds-prior verdict (evaluated via existing .mt0 pairs so
no hspice is needed in CI).
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
    assert abs(d["p2_ml_a_1"] - 0.44) < 1e-6 and abs(d["p2_ml_b_1"] - 0.01) < 1e-6


def test_mt0_failed_measure_is_none():
    assert parse_mt0("  p2_x  alter#\n  failed  1.0\n")["p2_x"] is None


# ---- deck ----
def test_p2_deck_reuses_golden_and_varies_d():
    g, ccc, arc, sens, init = _setup()
    cap_text, mmap = build_p2(arc, sens, init, init.probes, final_d=1)
    inv_text, _ = build_p2(arc, sens, init, init.probes, final_d=0)
    assert ".hold.inc" in cap_text and "VSE SE 0" in cap_text
    assert cap_text != inv_text                       # D@settle differs
    assert all(f".meas tran {nm}" in cap_text for nm in mmap.values())


# ---- differential verdict via existing mt0 pairs ----
def _mt0(tmp, name, vals):
    p = os.path.join(tmp, name)
    hdr = " ".join(k for k, _ in vals) + " alter#"
    row = " ".join(str(v) for _, v in vals) + " 1.0"
    with open(p, "w") as fh:
        fh.write(f"$DATA1\n  {hdr}\n  {row}\n")
    return p


def test_p2_pass_master_tracks_slave_holds(tmp_path):
    g, ccc, arc, sens, init = _setup()
    t = str(tmp_path)
    # cap run: ml tracks (a=1,b=0), sl holds (a=0,b=1)
    cap = _mt0(t, "c.mt0", [("p2_ml_a_1", 0.44), ("p2_ml_b_1", 0.01),
                            ("p2_sl_a_1", 0.01), ("p2_sl_b_1", 0.44)])
    # inv run: master FLIPS, slave SAME
    inv = _mt0(t, "i.mt0", [("p2_ml_a_1", 0.01), ("p2_ml_b_1", 0.44),
                            ("p2_sl_a_1", 0.01), ("p2_sl_b_1", 0.44)])
    res = run_p2(arc, ccc, sens, init, t, mt0_path=cap, mt0_inv_path=inv)
    assert res.ran and res.passed


def test_p2_fail_when_master_does_not_track(tmp_path):
    g, ccc, arc, sens, init = _setup()
    t = str(tmp_path)
    same = [("p2_ml_a_1", 0.44), ("p2_ml_b_1", 0.01),
            ("p2_sl_a_1", 0.01), ("p2_sl_b_1", 0.44)]
    cap = _mt0(t, "c.mt0", same)
    inv = _mt0(t, "i.mt0", same)        # master did NOT flip with D
    res = run_p2(arc, ccc, sens, init, t, mt0_path=cap, mt0_inv_path=inv)
    assert res.ran and not res.passed
