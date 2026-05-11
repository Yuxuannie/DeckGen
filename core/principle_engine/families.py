"""
families.py -- Template family registry for the principle engine.

Loads the reduced template family library from config/families.yaml.
Each family is a TemplateFamily dataclass mapping a key to a parameterized
template with metadata (init_style, tran_style, backend, param_schema).

In Phase 2A the registry is populated with a hardcoded bootstrap set of
families covering the 8 MVP arc families from spec_draft.md SS4.  A full
YAML-backed registry is planned for Phase 2B once the template library
structure is finalized.

Family key format: "{arc_type}/{topology}/{direction_pair}"
  Examples:
    "hold/common/rise_fall"
    "hold/latch/rise_fall"
    "delay/common/rise"
    "delay/common/fall"
    "min_pulse_width/CP/rise_fall"

Source: spec_draft.md SS2 (families.py section), SS4 (8 MVP families).
"""

import os
from typing import Dict, Optional

from core.principle_engine.family_types import (
    Backend,
    CellClass,
    InitStyle,
    TemplateFamily,
    TranStyle,
)

# ---------------------------------------------------------------------------
# Bootstrap registry -- 8 MVP families from spec_draft.md SS4
# ---------------------------------------------------------------------------
# Family 1: HSPICE hold, common topology (rise/fall)
# Family 2: HSPICE hold, latch topology (rise/fall)
# Family 3: HSPICE hold, MB topology (rise/fall)
# Family 4: HSPICE hold, SLH topology (rise/fall)
# Family 5: HSPICE min_pulse_width, CP-based
# Family 6: HSPICE nochange, CKG
# Family 7: HSPICE delay, common (rise and fall variants)
# Family 8: Spectre delay, AO22

_BOOTSTRAP_FAMILIES: list = [
    # --- MVP family 1: HSPICE hold, common ---
    TemplateFamily(
        key="hold/common/rise_fall",
        template_path="templates/v2/hold/template__common__rise__fall__1.sp",
        backend=Backend.HSPICE,
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE hold, common FF topology, rel=rise constr=fall",
    ),
    TemplateFamily(
        key="hold/common/fall_rise",
        template_path="templates/v2/hold/template__common__fall__rise__1.sp",
        backend=Backend.HSPICE,
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
        template_path="templates/v2/hold/template__latch__rise__fall__glitch__minq__1.sp",
        backend=Backend.HSPICE,
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
        template_path="templates/v2/hold/template__MB__common__rise__fall__2.sp",
        backend=Backend.HSPICE,
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
        template_path="templates/v2/hold/template__SLH__rise__SE__rise__pushout__1.sp",
        backend=Backend.HSPICE,
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NONE,
        param_schema=["REL_PIN", "CONSTR_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD", "PUSHOUT_PER"],
        measurement="pushout",
        description="HSPICE hold, SLH scan latch topology, pushout measurement",
    ),
    # --- MVP family 5: HSPICE min_pulse_width, standard CP clock (common topology) ---
    # Key uses "common" topology because mpw family selection is uniform across
    # FF topologies for the standard CP clock pin.  Selector falls through to
    # common for all non-specialized cells (FLOP, EDF, SLH, etc.).
    TemplateFamily(
        key="min_pulse_width/common/rise_fall",
        template_path="templates/v2/min_pulse_width/template__CP__rise__fall__1.sp",
        backend=Backend.HSPICE,
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NODESET,
        param_schema=["REL_PIN", "VDD_VALUE", "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE min_pulse_width, CP-based, nodeset init",
    ),
    TemplateFamily(
        key="min_pulse_width/common/fall_rise",
        template_path="templates/v2/min_pulse_width/template__CP__fall__rise__1.sp",
        backend=Backend.HSPICE,
        tran_style=TranStyle.MONTE_CARLO,
        init_style=InitStyle.NODESET,
        param_schema=["REL_PIN", "VDD_VALUE", "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE min_pulse_width, CP-based fall-rise, nodeset init",
    ),
    # --- MVP family 6: HSPICE nochange, CKG ---
    TemplateFamily(
        key="nochange/ckg/fall_fall",
        template_path="templates/v2/nochange/template__ckg__hold__fall__en__fall__pushout__negative__0.sp",
        backend=Backend.HSPICE,
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
        template_path="templates/v2/delay/template__common__rise__1.sp",
        backend=Backend.HSPICE,
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
        template_path="templates/v2/delay/template__common__fall__1.sp",
        backend=Backend.HSPICE,
        tran_style=TranStyle.OPTIMIZE,
        init_style=InitStyle.IC,
        ic_count=4,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="HSPICE delay, common topology fall, OPTIMIZE .tran, IC init",
    ),
    # --- MVP family 8: Spectre delay, AO22 ---
    TemplateFamily(
        key="delay/ao22/rise",
        template_path="templates/v2/delay/template__ao22__rise__1.thanos.sp",
        backend=Backend.SPECTRE,
        tran_style=TranStyle.SPECTRE_TRAN_ITER,
        init_style=InitStyle.IC,
        ic_count=2,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="Spectre delay, AO22 compound gate, tranIter, IC init",
    ),
    TemplateFamily(
        key="delay/ao22/fall",
        template_path="templates/v2/delay/template__ao22__fall__1.thanos.sp",
        backend=Backend.SPECTRE,
        tran_style=TranStyle.SPECTRE_TRAN_ITER,
        init_style=InitStyle.IC,
        ic_count=2,
        param_schema=["REL_PIN", "PROBE_PIN_1", "VDD_VALUE",
                      "INDEX_1_VALUE", "OUTPUT_LOAD"],
        measurement="standard",
        description="Spectre delay, AO22 compound gate fall, tranIter, IC init",
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
    """Return the loaded template family registry.

    On first call, loads from the bootstrap set (Phase 2A).
    Future Phase 2B will extend this to load additional families from
    config/families.yaml or templates/v2/ directory scan.
    """
    global _registry
    if _registry is None:
        _registry = _build_index(_BOOTSTRAP_FAMILIES)
    return _registry


def load_families(families_dir: str = None) -> Dict[str, TemplateFamily]:
    """Load family registry.

    Phase 2A: returns bootstrap hardcoded families regardless of families_dir.
    Phase 2B: will load from YAML config or templates/v2/ directory scan.

    Args:
        families_dir: Path to templates/v2/ or config dir. Ignored in Phase 2A.

    Returns:
        Dict mapping family key -> TemplateFamily.
    """
    return get_registry()


def lookup_family(key: str) -> Optional[TemplateFamily]:
    """Look up a single family by key. Returns None if not found."""
    return get_registry().get(key)


def list_families() -> list:
    """Return all registered families sorted by key."""
    return sorted(get_registry().values(), key=lambda f: f.key)
