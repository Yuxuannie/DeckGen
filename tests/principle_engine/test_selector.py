"""
tests/principle_engine/test_selector.py

Unit tests for core/principle_engine/selector.py.

Architecture note (2026-05-11 correction):
  Selection is now backend-agnostic. Backend validation moves to
  TemplateFamily.assert_backend_available(). Tests updated accordingly:
  - `backend=` parameter removed from all select_template_family calls
  - Family assertions use hspice_template_path / spectre_template_path
    instead of fam.backend == Backend.HSPICE / SPECTRE
  - test_backend_mismatch_falls_back_to_common -> test_backend_mismatch_raises
    (now tests assert_backend_available() on AO22 Spectre-only family)
  - New TestDualBackendFamily class validates latch dual-path entry (Patch 6a)
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
    UnsupportedBackendError,
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
) -> TemplateFamily:
    """Convenience wrapper -- no backend parameter (selection is backend-agnostic)."""
    cr = classification(cell_name)
    return select_template_family(
        classification=cr,
        arc_type=arc_type,
        rel_pin_dir=rel_dir,
        constr_pin_dir=constr_dir,
    )


# ---------------------------------------------------------------------------
# _infer_tran_style (utility for engine.py, still tested here)
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

    def test_raises_on_none(self):
        with pytest.raises(ValueError, match="requires both directions"):
            _dir_pair(None, None)


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
# MVP family selection (all 8 MVP families + AO22)
# ---------------------------------------------------------------------------

class TestMvpFamilySelection:
    """Each test exercises one of the 8 bootstrap families.

    Architecture note: backend= removed from sel() calls.
    Family assertions now check hspice_template_path / spectre_template_path
    instead of fam.backend.
    """

    def test_family1_hold_common_rise_fall(self):
        fam = sel("DFFQ1BWP", "hold", "rise", "fall")
        assert fam.key == "hold/common/rise_fall"
        assert fam.hspice_template_path is not None
        assert fam.spectre_template_path is None
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
        # DFFQ -> FLOP -> topology="flop", falls back to common
        fam = sel("DFFQ1BWP", "delay", "rise", "fall")
        assert fam.key == "delay/common/rise"
        assert fam.hspice_template_path is not None   # HSPICE available
        assert fam.spectre_template_path is None       # Spectre not (bootstrap)
        assert fam.tran_style == TranStyle.OPTIMIZE

    def test_family7_delay_hspice_fall(self):
        fam = sel("DFFQ1BWP", "delay", "fall", "rise")
        assert fam.key == "delay/common/fall"
        assert fam.hspice_template_path is not None

    def test_family8_latch_delay_rise(self):
        # Latch delay is the dual-backend family (Patch 6a).
        fam = sel("LATCHD1BWP", "delay", "rise", "fall")
        assert fam.key == "delay/latch/rise"
        assert fam.hspice_template_path is not None    # HSPICE available
        assert fam.spectre_template_path is not None   # Spectre also available

    def test_family8_latch_delay_fall(self):
        fam = sel("LATCHD1BWP", "delay", "fall", "rise")
        assert fam.key == "delay/latch/fall"
        assert fam.hspice_template_path is not None
        assert fam.spectre_template_path is not None

    def test_setup_common_rise_fall(self):
        fam = sel("DFFQ1BWP", "setup", "rise", "fall")
        assert fam.key == "setup/common/rise_fall"
        assert fam.hspice_template_path is not None
        assert fam.tran_style == TranStyle.MONTE_CARLO

    def test_setup_common_fall_rise(self):
        fam = sel("DFFQ1BWP", "setup", "fall", "rise")
        assert fam.key == "setup/common/fall_rise"
        assert fam.hspice_template_path is not None

    def test_ao22_delay_rise(self):
        # AO22 delay: Spectre-only (HSPICE not shipped by FMC for this family)
        fam = sel("AO22D1BWP", "delay", "rise", "fall")
        assert fam.key == "delay/ao22/rise"
        assert fam.spectre_template_path is not None
        assert fam.hspice_template_path is None         # Spectre-only

    def test_ao22_delay_fall(self):
        fam = sel("AO22D1BWP", "delay", "fall", "rise")
        assert fam.key == "delay/ao22/fall"
        assert fam.spectre_template_path is not None
        assert fam.hspice_template_path is None


# ---------------------------------------------------------------------------
# Dual-backend family validation (Patch 5 + 6)
# ---------------------------------------------------------------------------

class TestDualBackendFamily:
    """Tests for assert_backend_available() and available_backends property.

    This replaces test_backend_mismatch_falls_back_to_common (which was an
    unintended consequence of backend being a selector parameter).  Backend
    mismatch is now detected at family.assert_backend_available(), not at
    selection time.
    """

    def test_latch_delay_both_backends_available(self):
        fam = sel("LATCHD1BWP", "delay", "rise", "fall")
        assert Backend.HSPICE in fam.available_backends
        assert Backend.SPECTRE in fam.available_backends

    def test_latch_assert_hspice_passes(self):
        fam = sel("LATCHD1BWP", "delay", "rise", "fall")
        fam.assert_backend_available(Backend.HSPICE)  # must not raise

    def test_latch_assert_spectre_passes(self):
        fam = sel("LATCHD1BWP", "delay", "rise", "fall")
        fam.assert_backend_available(Backend.SPECTRE)  # must not raise

    def test_backend_mismatch_raises(self):
        # AO22 is Spectre-only; requesting HSPICE must raise UnsupportedBackendError.
        # This restores the raise-on-mismatch semantics that were lost when
        # backend was removed from the selector (Patch 5).
        fam = sel("AO22D1BWP", "delay", "rise", "fall")
        assert fam.hspice_template_path is None
        with pytest.raises(UnsupportedBackendError) as exc_info:
            fam.assert_backend_available(Backend.HSPICE)
        err_str = str(exc_info.value)
        assert "delay/ao22/rise" in err_str
        assert "hspice" in err_str
        assert "spectre" in err_str  # available backend mentioned

    def test_hspice_only_family_spectre_raises(self):
        # hold/common is HSPICE-only; requesting Spectre raises.
        fam = sel("DFFQ1BWP", "hold", "rise", "fall")
        assert fam.spectre_template_path is None
        with pytest.raises(UnsupportedBackendError):
            fam.assert_backend_available(Backend.SPECTRE)

    def test_template_family_requires_at_least_one_path(self):
        # TemplateFamily without any template path must raise at construction.
        with pytest.raises(ValueError, match="at least one of"):
            TemplateFamily(key="test/empty/rise")


# ---------------------------------------------------------------------------
# Topology fallback warning
# ---------------------------------------------------------------------------

class TestTopologyFallback:
    def test_topology_fallback_emits_warning(self, caplog):
        """When the classifier returns a non-common topology that doesn't
        have a registry entry, selector falls back to common AND logs a
        warning. The fallback is intentional Phase 2A scaffolding but must
        be observable for debug."""
        import logging
        with caplog.at_level(logging.WARNING, logger="core.principle_engine.selector"):
            fam = sel("DFFQ1BWP", "delay", "rise", "fall")  # FLOP -> common
            assert fam.key == "delay/common/rise"
            assert any("Topology fallback" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# SelectionError diagnostics
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
        # UNKNOWN cell -> SelectionError immediately
        cr = classification("COMPLETELY_UNKNOWN_XYZ")
        with pytest.raises(SelectionError) as exc_info:
            select_template_family(
                classification=cr,
                arc_type="hold",
                rel_pin_dir="rise",
                constr_pin_dir="fall",
            )
        err = exc_info.value
        assert err.tried
        assert "arc_type" in err.tried

    def test_error_has_closest_matches(self):
        # FLOP, hold, rise/rise -> no hold/flop/rise_rise, no hold/common/rise_rise
        cr = classify_cell("DFFQ1BWP")  # FLOP
        with pytest.raises(SelectionError) as exc_info:
            select_template_family(
                classification=cr,
                arc_type="hold",
                rel_pin_dir="rise",
                constr_pin_dir="rise",
            )
        err = exc_info.value
        assert isinstance(err.closest, list)


# ---------------------------------------------------------------------------
# Registry consistency
# ---------------------------------------------------------------------------

class TestRegistryConsistency:
    def test_all_families_have_unique_keys(self):
        registry = get_registry()
        keys = list(registry.keys())
        assert len(keys) == len(set(keys)), "Duplicate family keys in registry"

    def test_all_families_have_at_least_one_path(self):
        # Replaces test_all_families_have_template_path (architectural correction:
        # families now use hspice_template_path / spectre_template_path, not template_path)
        for key, fam in get_registry().items():
            assert fam.hspice_template_path or fam.spectre_template_path, (
                f"Family {key!r} has neither hspice_template_path nor spectre_template_path"
            )

    def test_spectre_paths_have_thanos_extension(self):
        # Replaces test_spectre_families_have_thanos_extension
        for key, fam in get_registry().items():
            if fam.spectre_template_path:
                assert fam.spectre_template_path.endswith(".thanos.sp"), (
                    f"Family {key!r} spectre_template_path does not end in .thanos.sp: "
                    f"{fam.spectre_template_path!r}"
                )

    def test_hspice_paths_end_in_sp(self):
        # Replaces test_hspice_families_end_in_sp
        for key, fam in get_registry().items():
            if fam.hspice_template_path:
                assert fam.hspice_template_path.endswith(".sp"), (
                    f"Family {key!r} hspice_template_path does not end in .sp: "
                    f"{fam.hspice_template_path!r}"
                )
                assert not fam.hspice_template_path.endswith(".thanos.sp"), (
                    f"Family {key!r} hspice_template_path incorrectly ends in .thanos.sp"
                )

    def test_ic_style_families_have_ic_count(self):
        from core.principle_engine.family_types import InitStyle
        for key, fam in get_registry().items():
            if fam.init_style == InitStyle.IC:
                assert fam.ic_count > 0, (
                    f"Family {key!r} has InitStyle.IC but ic_count=0"
                )

    def test_registry_entry_count(self):
        # 16 entries: 14 from Phase 2A + 2 setup/common (Phase 2B.1)
        assert len(get_registry()) == 16

    def test_latch_delay_is_dual_backend(self):
        registry = get_registry()
        for direction in ("rise", "fall"):
            fam = registry[f"delay/latch/{direction}"]
            assert fam.hspice_template_path is not None
            assert fam.spectre_template_path is not None

    def test_ao22_delay_is_spectre_only(self):
        registry = get_registry()
        for direction in ("rise", "fall"):
            fam = registry[f"delay/ao22/{direction}"]
            assert fam.spectre_template_path is not None
            assert fam.hspice_template_path is None
