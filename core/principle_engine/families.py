"""
families.py -- Template family registry for the principle engine.

Each family is a TemplateFamily dataclass with optional hspice_template_path
and spectre_template_path.  Selection is backend-agnostic; the caller
requests a backend after selection via TemplateFamily.assert_backend_available().

Architectural note (2026-05-11 correction):
  Spectre is a parallel output format for the same logical family, not a
  separate family registered by backend.  Before this correction, the
  registry had separate AO22-HSPICE and AO22-Spectre entries; those are
  now a single AO22 family with only spectre_template_path set (FMC has
  not shipped HSPICE AO22 delay templates as of N2P_v1.0).

Entry count: 12 entries -> 14 entries after correction:
  - AO22 rise/fall: unchanged count (2), but backend field removed and
    hspice_template_path=None (was backend=SPECTRE + template_path)
  - latch delay rise/fall: +2 new entries (dual-backend, Patch 6a)
    E.3 finding: latch=25 is the largest Spectre cell family; adding
    dual-backend latch validates the dual-path mechanism.

Family key format:
  Non-delay: "{arc_type}/{topology}/{rel_dir}_{constr_dir}"
  Delay/slew: "{arc_type}/{topology}/{rel_dir}"

Source: spec_draft.md SS2 SS4, E2_sampling_results.md, E3_sampling_results.md.
"""

from typing import Dict, Optional

from core.principle_engine.family_types import (
    InitStyle,
    TemplateFamily,
    TranStyle,
)

# ---------------------------------------------------------------------------
# Bootstrap registry
# ---------------------------------------------------------------------------
# MVP families (spec_draft.md SS4):
#   Family 1: HSPICE hold, common topology (rise/fall + fall/rise)
#   Family 2: HSPICE hold, latch topology
#   Family 3: HSPICE hold, MB topology
#   Family 4: HSPICE hold, SLH topology
#   Family 5: HSPICE min_pulse_width, common (CP clock)
#   Family 6: HSPICE nochange, CKG
#   Family 7: HSPICE delay, common (rise + fall)
#   Family 8: Dual-backend delay, latch (HSPICE + Spectre)  [Patch 6a: was AO22-Spectre-only]
#
# Additional entries:
#   AO22 delay (rise + fall): Spectre-only; validates single-backend path

_BOOTSTRAP_FAMILIES: list = [
    # --- MVP family 1: HSPICE hold, common ---
    TemplateFamily(
        key="hold/common/rise_fall",
        hspice_template_path="templates/v2/hold/template__common__rise__fall__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE hold, common FF topology, rel=rise constr=fall",
    ),
    TemplateFamily(
        key="hold/common/fall_rise",
        hspice_template_path="templates/v2/hold/template__common__fall__rise__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE hold, common FF topology, rel=fall constr=rise",
    ),
    # --- MVP family 2: HSPICE hold, latch ---
    TemplateFamily(
        key="hold/latch/rise_fall",
        hspice_template_path="templates/v2/hold/template__latch__rise__fall__glitch__minq__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD", "GLITCH"],
        measurement="glitch",
        description="HSPICE hold, latch topology, glitch measurement",
    ),
    # --- MVP family 3: HSPICE hold, MB ---
    TemplateFamily(
        key="hold/mb/rise_fall",
        hspice_template_path="templates/v2/hold/template__MB__common__rise__fall__2.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.IC,
        ic_count=8,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE hold, multi-bank topology, ic_count=8",
    ),
    # --- MVP family 4: HSPICE hold, SLH ---
    TemplateFamily(
        key="hold/slh/rise_fall",
        hspice_template_path="templates/v2/hold/template__SLH__rise__SE__rise__pushout__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD", "PUSHOUT_PER"],
        measurement="pushout",
        description="HSPICE hold, SLH scan latch topology, pushout measurement",
    ),
    # --- MVP family 5: HSPICE min_pulse_width, standard CP clock (common topology) ---
    # Key uses "common" topology because mpw family selection is uniform across
    # FF topologies for the standard CP clock pin.
    TemplateFamily(
        key="min_pulse_width/common/rise_fall",
        hspice_template_path="templates/v2/min_pulse_width/template__CP__rise__fall__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NODESET,
        param_schema=["REL_PIN", "VDD_VALUE", "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE min_pulse_width, CP-based, nodeset init",
    ),
    TemplateFamily(
        key="min_pulse_width/common/fall_rise",
        hspice_template_path="templates/v2/min_pulse_width/template__CP__fall__rise__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NODESET,
        param_schema=["REL_PIN", "VDD_VALUE", "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE min_pulse_width, CP-based fall-rise, nodeset init",
    ),
    # --- Setup arc families (Phase 2B.1 addition) ---
    # Setup uses same monte=1 .tran style and NONE init style as hold/common.
    # Source: spec_draft.md §4 (setup in MVP scope), E2_sampling_results.md SS A.
    TemplateFamily(
        key="setup/common/rise_fall",
        hspice_template_path="templates/v2/setup/template__common__rise__fall__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE setup, common FF topology, rel=rise constr=fall",
    ),
    TemplateFamily(
        key="setup/common/fall_rise",
        hspice_template_path="templates/v2/setup/template__common__fall__rise__1.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE setup, common FF topology, rel=fall constr=rise",
    ),
    # --- MVP family 6: HSPICE nochange, CKG ---
    TemplateFamily(
        key="nochange/ckg/fall_fall",
        hspice_template_path="templates/v2/nochange/template__ckg__hold__fall__en__fall__pushout__negative__0.sp",
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD", "PUSHOUT_PER"],
        measurement="pushout",
        description="HSPICE nochange, CKG gate topology, pushout measurement",
    ),
    # --- MVP family 7: HSPICE delay, common ---
    TemplateFamily(
        key="delay/common/rise",
        hspice_template_path="templates/v2/delay/template__common__rise__1.sp",
        tran_style=TranStyle.OPTIMIZE,
        init_style=InitStyle.IC,
        ic_count=4,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE delay, common topology, OPTIMIZE .tran, IC init",
    ),
    TemplateFamily(
        key="delay/common/fall",
        hspice_template_path="templates/v2/delay/template__common__fall__1.sp",
        tran_style=TranStyle.OPTIMIZE,
        init_style=InitStyle.IC,
        ic_count=4,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE delay, common topology fall, OPTIMIZE .tran, IC init",
    ),
    # --- MVP family 8: Dual-backend delay, latch (Patch 6a) ---
    # E.3 sampling: latch=25 is the largest Spectre cell family, making latch
    # the best representative for the dual-backend pattern.  Both HSPICE and
    # Spectre paths are set; validates assert_backend_available() for both.
    TemplateFamily(
        key="delay/latch/rise",
        hspice_template_path="templates/v2/delay/template__latch__rise__1.sp",
        spectre_template_path="templates/v2/delay/template__latch__rise__1.thanos.sp",
        tran_style=TranStyle.OPTIMIZE,
        init_style=InitStyle.IC,
        ic_count=2,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="Delay latch, dual-backend (HSPICE OPTIMIZE + Spectre tranIter), IC init",
    ),
    TemplateFamily(
        key="delay/latch/fall",
        hspice_template_path="templates/v2/delay/template__latch__fall__1.sp",
        spectre_template_path="templates/v2/delay/template__latch__fall__1.thanos.sp",
        tran_style=TranStyle.OPTIMIZE,
        init_style=InitStyle.IC,
        ic_count=2,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="Delay latch fall, dual-backend (HSPICE OPTIMIZE + Spectre tranIter), IC init",
    ),
    # --- AO22 delay: Spectre-only (FMC has not shipped HSPICE AO22 delay templates) ---
    # Architectural note: these are NOT a separate "AO22 backend variant" --
    # they are the same AO22 family with only spectre_template_path set.
    # If FMC ships HSPICE AO22 templates in future, hspice_template_path is
    # populated here and assert_backend_available(HSPICE) will start passing.
    TemplateFamily(
        key="delay/ao22/rise",
        spectre_template_path="templates/v2/delay/template__ao22__rise__1.thanos.sp",
        tran_style=TranStyle.OPTIMIZE,   # HSPICE tran style if/when HSPICE ships
        init_style=InitStyle.IC,
        ic_count=2,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="AO22 compound gate delay, Spectre-only (FMC rollout incomplete)",
    ),
    TemplateFamily(
        key="delay/ao22/fall",
        spectre_template_path="templates/v2/delay/template__ao22__fall__1.thanos.sp",
        tran_style=TranStyle.OPTIMIZE,   # HSPICE tran style if/when HSPICE ships
        init_style=InitStyle.IC,
        ic_count=2,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="AO22 compound gate delay fall, Spectre-only (FMC rollout incomplete)",
    ),
]


def _build_index(families: list) -> Dict[str, TemplateFamily]:
    """Build key -> TemplateFamily dict, checking for duplicate keys."""
    index: Dict[str, TemplateFamily] = {}
    for fam in families:
        if fam.key in index:
            raise ValueError(
                f"Duplicate family key in registry: {fam.key!r}. "
                "Each key must be unique."
            )
        index[fam.key] = fam
    return index


# Module-level registry (lazy-initialized singleton)
_registry: Optional[Dict[str, TemplateFamily]] = None


def get_registry() -> Dict[str, TemplateFamily]:
    """Return the loaded template family registry (lazy-initialized singleton)."""
    global _registry
    if _registry is None:
        _registry = _build_index(_BOOTSTRAP_FAMILIES)
    return _registry


def load_families(families_dir: str = None) -> Dict[str, TemplateFamily]:
    """Load family registry.

    Phase 2A: returns bootstrap hardcoded families regardless of families_dir.
    Phase 2B: will load from YAML config or templates/v2/ directory scan.
    """
    return get_registry()


def lookup_family(key: str) -> Optional[TemplateFamily]:
    """Look up a single family by key. Returns None if not found."""
    return get_registry().get(key)


def list_families() -> list:
    """Return all registered families sorted by key."""
    return sorted(get_registry().values(), key=lambda f: f.key)
