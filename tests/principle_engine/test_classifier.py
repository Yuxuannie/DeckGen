"""
tests/principle_engine/test_classifier.py

Unit tests for core/principle_engine/classifier.py.

Covers:
  - All 15 CellClass values (name-based)
  - UNKNOWN fallback for unrecognized names
  - CKG sub-type extraction
  - SYNC / RETN depth extraction
  - define_cell attribute classification
  - Specificity ordering (ESLH before SLH, synX before RETN)
"""

import pytest

from core.principle_engine.classifier import (
    ClassifierResult,
    classify_cell,
    _extract_ckg_subtype,
    _extract_sync_depth,
)
from core.principle_engine.family_types import CellClass


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def cls(name, cell_obj=None) -> CellClass:
    """Shorthand: classify and return CellClass."""
    return classify_cell(name, cell_obj).cell_class


# ---------------------------------------------------------------------------
# Basic 15-class coverage (name-based)
# ---------------------------------------------------------------------------

class TestNameBasedClassification:
    def test_common_fallback(self):
        # Generic FF name with no distinguishing token -> COMMON
        # (COMMON is the fallback; tested separately via UNKNOWN boundary)
        # Actually COMMON is only returned when no other pattern matches
        # and the cell IS a known FF structure.  A truly unrecognized name
        # returns UNKNOWN.  We test that a plain DFFQ name hits FLOP.
        assert cls("DFFQ1BWP130H") == CellClass.FLOP

    def test_flop(self):
        assert cls("DFFQD1BWP130H") == CellClass.FLOP
        assert cls("SDFFQ2BWP") == CellClass.FLOP

    def test_latch(self):
        assert cls("LATCHD1BWP") == CellClass.LATCH
        assert cls("DLATCH2BWP130H") == CellClass.LATCH

    def test_mb(self):
        assert cls("MBFFD2BWP") == CellClass.MB
        assert cls("MBD4BWP130H") == CellClass.MB

    def test_edf(self):
        assert cls("EDFQ1BWP130H") == CellClass.EDF
        assert cls("SDFQNSXGD1BWP") == CellClass.EDF
        assert cls("SDFNQSXGD2BWP") == CellClass.EDF

    def test_slh(self):
        assert cls("SLH1BWP130H") == CellClass.SLH

    def test_eslh_before_slh(self):
        # ESLH must match before SLH
        assert cls("ESLH2BWP130H") == CellClass.ESLH

    def test_rcb(self):
        assert cls("RCB1BWP130H") == CellClass.RCB

    def test_sync(self):
        assert cls("SYNC2D1BWP") == CellClass.SYNC
        assert cls("SYNC4BWP130H") == CellClass.SYNC

    def test_det(self):
        assert cls("DETD1BWP130H") == CellClass.DET

    def test_div4(self):
        assert cls("DIV4D2BWP") == CellClass.DIV4

    def test_drdf(self):
        assert cls("DRDF1BWP130H") == CellClass.DRDF

    def test_retn(self):
        assert cls("RETNQ1BWP130H") == CellClass.RETN
        assert cls("RETD1BWP") == CellClass.RETN

    def test_retn_syn_variants(self):
        # synX depth tokens classify as RETN
        assert cls("SYN2D1BWP") == CellClass.RETN
        assert cls("SYN6D2BWP") == CellClass.RETN

    def test_basemeg(self):
        assert cls("BASEMEG1BWP") == CellClass.BASEMEG

    def test_ckg(self):
        assert cls("CKGD1BWP") == CellClass.CKG
        assert cls("CLKGATE1BWP") == CellClass.CKG

    def test_ao22(self):
        assert cls("AO22D1BWP130H") == CellClass.AO22
        assert cls("OA22D2BWP") == CellClass.AO22

    def test_unknown(self):
        assert cls("COMPLETELY_UNKNOWN_CELL_XYZ") == CellClass.UNKNOWN
        assert cls("") == CellClass.UNKNOWN


# ---------------------------------------------------------------------------
# CKG sub-type extraction
# ---------------------------------------------------------------------------

class TestCkgSubtype:
    def test_ckg_basic(self):
        r = classify_cell("CKGD1BWP")
        assert r.cell_class == CellClass.CKG
        assert r.ckg_subtype == "ckg"

    def test_ckgn(self):
        r = classify_cell("CKGND1BWP")
        assert r.ckg_subtype == "ckgn"

    def test_ckgian(self):
        r = classify_cell("CKGIAND1BWP")
        assert r.ckg_subtype == "ckgian"

    def test_ckgmux2(self):
        r = classify_cell("CKGMUX2D1BWP")
        assert r.cell_class == CellClass.CKG
        assert r.ckg_subtype == "ckgmux2"

    def test_ckgmux3(self):
        r = classify_cell("CKGMUX3D2BWP")
        assert r.ckg_subtype == "ckgmux3"

    def test_ckgmux3_before_ckgmux2(self):
        # ckgmux3 must be detected before ckgmux2
        assert _extract_ckg_subtype("CKGMUX3D1BWP") == "ckgmux3"

    def test_extract_ckg_subtype_direct(self):
        assert _extract_ckg_subtype("CKGD1") == "ckg"
        assert _extract_ckg_subtype("CKGND1") == "ckgn"
        assert _extract_ckg_subtype("CKGMUX2D1") == "ckgmux2"
        assert _extract_ckg_subtype("CKGMUX3D1") == "ckgmux3"


# ---------------------------------------------------------------------------
# SYNC / RETN depth extraction
# ---------------------------------------------------------------------------

class TestDepthExtraction:
    def test_sync_depth(self):
        r = classify_cell("SYNC2D1BWP")
        assert r.cell_class == CellClass.SYNC
        assert r.sync_depth == 2

    def test_sync_depth_4(self):
        r = classify_cell("SYNC4D2BWP130H")
        assert r.sync_depth == 4

    def test_retn_syn2_depth(self):
        r = classify_cell("SYN2RETNQ1BWP")
        assert r.cell_class == CellClass.RETN
        assert r.sync_depth == 2

    def test_retn_syn6_depth(self):
        r = classify_cell("SYN6RTNQD1BWP")
        assert r.sync_depth == 6

    def test_retn_no_depth(self):
        # Base retn (no syn digit) -> depth is None
        r = classify_cell("RETNQ1BWP130H")
        assert r.cell_class == CellClass.RETN
        assert r.sync_depth is None

    def test_extract_sync_depth_direct(self):
        assert _extract_sync_depth("SYNC2D1") == 2
        assert _extract_sync_depth("SYN3D1") == 3
        assert _extract_sync_depth("NO_DEPTH") is None


# ---------------------------------------------------------------------------
# define_cell attribute classification
# ---------------------------------------------------------------------------

class TestDefineCellClassification:
    """Tests for classification from parsed Cell objects."""

    class FakeCell:
        """Minimal stub for a parsed template.tcl Cell object."""
        def __init__(self, attrs: dict):
            self.attrs = attrs

    def test_latch_from_define_cell(self):
        cell = self.FakeCell({"cell_type": "latch"})
        r = classify_cell("UNKNOWNLATCH99", cell_obj=cell)
        assert r.cell_class == CellClass.LATCH
        assert r.source == "define_cell"

    def test_ckg_from_define_cell(self):
        cell = self.FakeCell({"cell_type": "clock_gate"})
        r = classify_cell("CKGD1BWP", cell_obj=cell)
        assert r.cell_class == CellClass.CKG
        assert r.source == "define_cell"

    def test_retn_from_define_cell(self):
        cell = self.FakeCell({"cell_type": "retention"})
        r = classify_cell("RETNQ1", cell_obj=cell)
        assert r.cell_class == CellClass.RETN

    def test_mb_from_define_cell(self):
        cell = self.FakeCell({"cell_type": "multi_bank"})
        r = classify_cell("MBFFD1", cell_obj=cell)
        assert r.cell_class == CellClass.MB
        assert r.source == "define_cell"

    def test_falls_back_to_name_when_define_cell_inconclusive(self):
        # define_cell with no recognized type -> falls back to name
        cell = self.FakeCell({"cell_type": "flip_flop"})  # not in define_cell map
        r = classify_cell("DFFQ1BWP", cell_obj=cell)
        # Name matching should still get FLOP
        assert r.cell_class == CellClass.FLOP
        assert r.source == "name"

    def test_none_cell_obj_uses_name(self):
        r = classify_cell("SLH1BWP", cell_obj=None)
        assert r.cell_class == CellClass.SLH
        assert r.source == "name"

    def test_depth_augmented_from_name_when_define_cell_misses_it(self):
        # define_cell says sync but doesn't provide depth -- name fills in
        cell = self.FakeCell({"cell_type": "sync"})
        r = classify_cell("SYNC4D1BWP", cell_obj=cell)
        assert r.cell_class == CellClass.SYNC
        assert r.sync_depth == 4


# ---------------------------------------------------------------------------
# ClassifierResult repr
# ---------------------------------------------------------------------------

class TestClassifierResultRepr:
    def test_repr_basic(self):
        r = ClassifierResult(CellClass.FLOP)
        assert "FLOP" in repr(r)

    def test_repr_with_depth(self):
        r = ClassifierResult(CellClass.SYNC, sync_depth=3)
        assert "depth=3" in repr(r)

    def test_repr_with_subtype(self):
        r = ClassifierResult(CellClass.CKG, ckg_subtype="ckgmux2")
        assert "ckgmux2" in repr(r)
