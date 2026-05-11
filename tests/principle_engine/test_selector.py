"""
tests/principle_engine/test_selector.py

Unit tests for core/principle_engine/selector.py.

Covers:
  - All 8 MVP families (exact key match)
  - Direction pair normalization
  - Backend filtering (HSPICE vs Spectre)
  - TranStyle inference from arc_type + backend
  - Direction-agnostic fallback
  - Common-topology fallback
  - SelectionError on no match (with diagnostic info)
  - CKG subtype -> topology key mapping
  - RETN/SYNC depth -> topology key mapping
"""

import pytest

from core.principle_engine.classifier import ClassifierResult, classify_cell
from core.principle_engine.families import get_registry
from core.principle_engine.family_types import (
    Backend,
    CellClass,
    MeasurementProfile,
    ProbeInfo,
    SelectionError,
    TemplateFamily,
    TranStyle,
)
from core.principle_engine.selector import (
    _dir_pair,
    _infer_tran_style,
    _topology_key,
    select_template_family,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def classification(cell_name: str) -> ClassifierResult:
    return classify_cell(cell_name)


def sel(
    cell_name: str,
    arc_type: str,
    rel_dir: str = "rise",
    constr_dir: str = "fall",
    backend: Backend = None,
) -> TemplateFamily:
    """Convenience wrapper for select_template_family."""
    cr = classification(cell_name)
    return select_template_family(
        classification=cr,
        arc_type=arc_type,
        rel_pin_dir=rel_dir,
        constr_pin_dir=constr_dir,
        backend=backend,
    )


# ---------------------------------------------------------------------------
# _infer_tran_style
# ---------------------------------------------------------------------------

class TestInferTranStyle:
    def test_hold_hspice(self):
        assert _infer_tran_style("hold", Backend.HSPICE) == TranStyle.MONTE_CARLO

    def test_setup_hspice(self):
        assert _infer_tran_style("setup", Backend.HSPICE) == TranStyle.MONTE_CARLO

    def test_min_pulse_width_hspice(self):
        assert _infer_tran_style("min_pulse_width", Backend.HSPICE) == TranStyle.MONTE_CARLO

    def test_delay_hspice(self):
        assert _infer_tran_style("delay", Backend.HSPICE) == TranStyle.OPTIMIZE

    def test_slew_hspice(self):
        assert _infer_tran_style("slew", Backend.HSPICE) == TranStyle.OPTIMIZE

    def test_delay_spectre(self):
        assert _infer_tran_style("delay", Backend.SPECTRE) == TranStyle.SPECTRE_TRAN_ITER

    def test_hold_spectre(self):
        # Even for non-delay arcs, Spectre overrides to SPECTRE_TRAN_ITER
        assert _infer_tran_style("hold", Backend.SPECTRE) == TranStyle.SPECTRE_TRAN_ITER


# ---------------------------------------------------------------------------
# _dir_pair
# ---------------------------------------------------------------------------

class TestDirPair:
    def test_rise_fall(self):
        assert _dir_pair("rise", "fall") == "rise_fall"

    def test_fall_rise(self):
        assert _dir_pair("fall", "rise") == "fall_rise"

    def test_case_insensitive(self):
        assert _dir_pair("Rise", "Fall") == "rise_fall"

    def test_defaults(self):
        assert _dir_pair(None, None) == "rise_fall"


# ---------------------------------------------------------------------------
# _topology_key
# ---------------------------------------------------------------------------

class TestTopologyKey:
    def _cr(self, cc, depth=None, subtype=None):
        return ClassifierResult(cc, sync_depth=depth, ckg_subtype=subtype)

    def test_common(self):
        assert _topology_key(self._cr(CellClass.COMMON), "hold", None, None) == "common"

    def test_latch(self):
        assert _topology_key(self._cr(CellClass.LATCH), "hold", None, None) == "latch"

    def test_mb(self):
        assert _topology_key(self._cr(CellClass.MB), "hold", None, None) == "mb"

    def test_ckg_basic(self):
        assert _topology_key(self._cr(CellClass.CKG, subtype="ckg"), "nochange", None, None) == "ckg"

    def test_ckg_ckgmux2(self):
        assert _topology_key(self._cr(CellClass.CKG, subtype="ckgmux2"), "nochange", None, None) == "ckgmux2"

    def test_retn_syn2(self):
        assert _topology_key(self._cr(CellClass.RETN, depth=2), "hold", None, None) == "syn2"

    def test_retn_no_depth(self):
        assert _topology_key(self._cr(CellClass.RETN), "hold", None, None) == "retn"

    def test_sync_depth(self):
        assert _topology_key(self._cr(CellClass.SYNC, depth=4), "hold", None, None) == "sync4"

    def test_ao22(self):
        assert _topology_key(self._cr(CellClass.AO22), "delay", None, None) == "ao22"


# ---------------------------------------------------------------------------
# MVP family selection -- 8 families from spec_draft.md SS4
# ---------------------------------------------------------------------------

class TestMvpFamilySelection:
    """Each test exercises one of the 8 bootstrap families."""

    def test_family1_hold_common_rise_fall(self):
        fam = sel("DFFQ1BWP", "hold", "rise", "fall")
        assert fam.key == "hold/common/rise_fall"
        assert fam.backend == Backend.HSPICE
        assert fam.tran_style == TranStyle.MONTE_CARLO

    def test_family1_hold_common_fall_rise(self):
        fam = sel("DFFQ1BWP", "hold", "fall", "rise")
        assert fam.key == "hold/common/fall_rise"

    def test_family2_hold_latch(self):
        fam = sel("LATCHD1BWP", "hold", "rise", "fall")
        assert fam.key == "hold/latch/rise_fall"
        assert fam.measurement == "glitch"

    def test_family3_hold_mb(self):
        fam = sel("MBFFD2BWP", "hold", "rise", "fall")
        assert fam.key == "hold/mb/rise_fall"
        assert fam.init_style.value == "ic"
        assert fam.ic_count == 8

    def test_family4_hold_slh(self):
        fam = sel("SLH1BWP130H", "hold", "rise", "fall")
        assert fam.key == "hold/slh/rise_fall"
        assert fam.measurement == "pushout"

    def test_family5_mpw_cp_rise_fall(self):
        # DFFQ -> FLOP -> topology="flop", no exact match -> common fallback
        fam = sel("DFFQ1BWP", "min_pulse_width", "rise", "fall")
        assert fam.key == "min_pulse_width/common/rise_fall"
        assert fam.init_style.value == "nodeset"

    def test_family5_mpw_cp_fall_rise(self):
        fam = sel("DFFQ1BWP", "min_pulse_width", "fall", "rise")
        assert fam.key == "min_pulse_width/common/fall_rise"

    def test_family6_nochange_ckg(self):
        fam = sel("CKGD1BWP", "nochange", "fall", "fall")
        assert fam.key == "nochange/ckg/fall_fall"
        assert fam.measurement == "pushout"

    def test_family7_delay_hspice_rise(self):
        fam = sel("DFFQ1BWP", "delay", "rise", "fall")
        assert fam.key == "delay/common/rise"
        assert fam.backend == Backend.HSPICE
        assert fam.tran_style == TranStyle.OPTIMIZE

    def test_family7_delay_hspice_fall(self):
        fam = sel("DFFQ1BWP", "delay", "fall", "rise")
        assert fam.key == "delay/common/fall"

    def test_family8_delay_spectre_ao22_rise(self):
        fam = sel("AO22D1BWP", "delay", "rise", "fall", backend=Backend.SPECTRE)
        assert fam.key == "delay/ao22/rise"
        assert fam.backend == Backend.SPECTRE
        assert fam.tran_style == TranStyle.SPECTRE_TRAN_ITER

    def test_family8_delay_spectre_ao22_fall(self):
        fam = sel("AO22D1BWP", "delay", "fall", "rise", backend=Backend.SPECTRE)
        assert fam.key == "delay/ao22/fall"


# ---------------------------------------------------------------------------
# SelectionError on no match
# ---------------------------------------------------------------------------

class TestSelectionError:
    def test_raises_on_unknown_arc(self):
        cr = classification("DFFQ1BWP")
        with pytest.raises(SelectionError) as exc_info:
            select_template_family(
                classification=cr,
                arc_type="nonexistent_arc",
                rel_pin_dir="rise",
                constr_pin_dir="fall",
            )
        err = exc_info.value
        assert "nonexistent_arc" in str(err)

    def test_error_contains_tried_info(self):
        cr = classification("COMPLETELY_UNKNOWN_XYZ")
        with pytest.raises(SelectionError) as exc_info:
            select_template_family(
                classification=cr,
                arc_type="hold",
                rel_pin_dir="rise",
                constr_pin_dir="fall",
            )
        err = exc_info.value
        assert err.tried  # not empty
        assert "arc_type" in err.tried

    def test_error_has_closest_matches(self):
        cr = classify_cell("DFFQ1BWP")  # FLOP, not in registry
        with pytest.raises(SelectionError) as exc_info:
            select_template_family(
                classification=cr,
                arc_type="hold",
                rel_pin_dir="rise",
                constr_pin_dir="rise",  # neither rise_fall nor fall_rise
            )
        err = exc_info.value
        # closest should suggest hold/* families
        assert isinstance(err.closest, list)

    def test_backend_mismatch_falls_back_to_common(self):
        # AO22 with HSPICE backend: no exact AO22/HSPICE family exists, so the
        # selector falls back to delay/common/rise (HSPICE).  Phase 2C can add
        # stricter topology-backend enforcement when AO22-specific HSPICE
        # templates are confirmed absent.
        cr = classify_cell("AO22D1BWP")
        fam = select_template_family(
            classification=cr,
            arc_type="delay",
            rel_pin_dir="rise",
            constr_pin_dir="fall",
            backend=Backend.HSPICE,
        )
        assert fam.backend == Backend.HSPICE
        assert "delay" in fam.key


# ---------------------------------------------------------------------------
# Registry consistency
# ---------------------------------------------------------------------------

class TestRegistryConsistency:
    def test_all_families_have_unique_keys(self):
        registry = get_registry()
        keys = list(registry.keys())
        assert len(keys) == len(set(keys)), "Duplicate family keys in registry"

    def test_all_families_have_template_path(self):
        for key, fam in get_registry().items():
            assert fam.template_path, f"Family {key!r} has empty template_path"

    def test_spectre_families_have_thanos_extension(self):
        for key, fam in get_registry().items():
            if fam.backend == Backend.SPECTRE:
                assert fam.template_path.endswith(".thanos.sp"), (
                    f"Spectre family {key!r} template path does not end in .thanos.sp: "
                    f"{fam.template_path!r}"
                )

    def test_hspice_families_end_in_sp(self):
        for key, fam in get_registry().items():
            if fam.backend == Backend.HSPICE:
                assert fam.template_path.endswith(".sp"), (
                    f"HSPICE family {key!r} template path does not end in .sp: "
                    f"{fam.template_path!r}"
                )

    def test_ic_style_families_have_ic_count(self):
        from core.principle_engine.family_types import InitStyle
        for key, fam in get_registry().items():
            if fam.init_style == InitStyle.IC:
                assert fam.ic_count > 0, (
                    f"Family {key!r} has InitStyle.IC but ic_count=0"
                )
