"""
family_types.py -- Core type definitions for the principle engine.

All enums and dataclasses used across classifier, selector, families, and
backends. No dependencies on other principle_engine modules (leaf module).

Sources:
  - CellClass: B_rule_groupby.md SS2 (15 topology classes)
  - Backend/TranStyle: E2_sampling_results.md SS D (94 Spectre files, delay/ ecosystem)
  - InitStyle: E2_sampling_results.md SS Summary (NONE 67%, IC 19%, NODESET 14%)
  - TemplateFamily/MeasurementProfile/ProbeInfo: spec_draft.md SS2
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class CellClass(Enum):
    """Cell topology class. 15 classes derived from Task B discrimination analysis.

    Each class maps to a distinct set of template families in the reduced
    library. The classifier assigns one of these values based on cell name
    patterns and optional define_cell attributes from template.tcl.

    Source: B_rule_groupby.md SS2, F_feasibility_verdict.md SS2.
    """
    COMMON = "common"       # Generic FF (fallback -- no distinguishing token)
    LATCH = "latch"         # Latch (transparent, level-sensitive)
    FLOP = "flop"           # Standard D flip-flop (non-scan, non-retention)
    MB = "mb"               # Multi-bank FF (ic_count=8)
    EDF = "edf"             # Edge-detect flip-flop (ic_count=4)
    SLH = "slh"             # Scan latch (ic_count=2)
    ESLH = "eslh"           # Extended scan latch
    RCB = "rcb"             # Register-controlled buffer (ic_count=2)
    SYNC = "sync"           # Synchronizer (pipeline depth parameterized)
    DET = "det"             # Detector cell
    DIV4 = "div4"           # Clock divider (div-by-4)
    DRDF = "drdf"           # Dual-rail dual-flop
    RETN = "retn"           # Retention cell (base + syn2..syn6 depth variants)
    BASEMEG = "basemeg"     # Memory cell (WWL-based, basemeg token)
    CKG = "ckg"             # Clock gater (sub-typed by gate logic: ckg/ckgn/ckgian/ckgmux2/3)
    AO22 = "ao22"           # AO22/OA22 compound gate (Spectre only, E.2 SS D)
    UNKNOWN = "unknown"     # Not matched -- triggers v1 fallback


class Backend(Enum):
    """Simulator backend.

    Determined by template file extension and arc_type/cell_family.
    E.2 finding: 94 Spectre .thanos.sp files exist, 97% in delay/.

    Source: E2_sampling_results.md SS D, spec_draft.md SS2.
    """
    HSPICE = "hspice"    # .sp files. Default for all non-delay arcs.
    SPECTRE = "spectre"  # .thanos.sp files. Dominant for delay arcs (91/94).


class TranStyle(Enum):
    """Transient simulation command style.

    Strongly correlated with arc_type and backend (E.2 Section A tran style
    binding). The selector uses this to pick the correct template variant
    within a family.

    Source: E2_sampling_results.md SS A (.tran style binding table).
    """
    MONTE_CARLO = "monte"           # .tran 1p 5000n sweep monte=1
                                    # Hold/setup/mpw/nochange arc types.
    OPTIMIZE = "optimize"           # .tran 1p 5000n sweep OPTIMIZE=OPT1 ...
                                    # HSPICE delay arcs (majority of delay/).
    BARE = "bare"                   # .tran 1p 400ns (no sweep, no OPTIMIZE)
                                    # Simple HSPICE delay, seq_inpin variants (~6).
    SPECTRE_TRAN_ITER = "spectre_tran"  # tranIter tran stop=5000n
                                        # Spectre delay arcs.


class InitStyle(Enum):
    """Template-embedded initialization style.

    Metadata property of the template file -- NOT a runtime decision.
    Task E.2 confirmed all three styles are template-embedded; no runtime
    dispatch is needed. The Python generation code does only $VAR substitution
    and pin biasing; .ic/.nodeset blocks are pre-embedded in the template.

    Distribution (899 templates, N2P_v1.0 corpus):
      NONE:    604 (67%) -- V-source biasing + DONT_TOUCH_PINS only
      IC:      169 (19%) -- embedded .ic statements; ic_count by cell topology
      NODESET: 126 (14%) -- embedded .nodeset; 100% in mpw/min_pulse_width

    ic_count by cell topology (when InitStyle=IC):
      latch_S / RCB / CKG: 2
      EDF:  4
      MB:   8
      synx: 14
      syn2: 16
      seq_inpin: 1

    Source: E2_sampling_results.md (full corpus), spec_draft.md SS1.X.
    """
    NONE = "none"         # V-source biasing + DONT_TOUCH_PINS only
    IC = "ic"             # Embedded .ic statements
    NODESET = "nodeset"   # Embedded .nodeset statements (mpw/min_pulse_width only)


@dataclass
class MeasurementProfile:
    """Measurement profile for a template family.

    Describes what the template measures and how probe polarity is handled.
    Derived from arc_type, cell_class, probe_pin identity, and chartcl
    overrides.

    Source: spec_draft.md SS2 (measurement.py section).
    """
    has_pushout: bool = False
    has_glitch: bool = False
    polarity: str = "maxq"         # "maxq" (Q probe) or "minq" (QN probe)
    glitch_threshold: str = ""     # from chartcl cascade; empty = not applicable
    pushout_per: str = ""          # from chartcl cascade; empty = not applicable


@dataclass
class ProbeInfo:
    """Probe pin information for template family selection.

    Captures probe pin identity and any multi-probe expansion needed (e.g.,
    AO22/OA22 cells with multiple output probes, or multi-input expansion).

    Source: spec_draft.md SS2 (selector.py section).
    """
    probe_pin: str
    probe_dir: str                      # "rise" or "fall"
    output_pins: List[str] = field(default_factory=list)  # all output pins of cell
    is_multipin: bool = False           # True if multi-input expansion applies


@dataclass
class TemplateFamily:
    """A parameterized template family in the reduced library.

    Represents one entry in the ~50-65 principle families. The selector
    returns one of these; the param_binder then fills in $VAR slots.

    key format: "{arc_type}/{topology}/{direction_pair}"
    Example: "hold/common/rise_fall"

    Source: spec_draft.md SS2 (families.py section).
    """
    key: str                               # Lookup key, e.g. "hold/common/rise_fall"
    template_path: str                     # Relative path to .sp or .thanos.sp file
    backend: Backend = Backend.HSPICE      # Simulator backend
    tran_style: TranStyle = TranStyle.MONTE_CARLO  # .tran command style
    init_style: InitStyle = InitStyle.NONE # Template-embedded init style
    param_schema: List[str] = field(default_factory=list)  # Required $VAR names
    measurement: str = "standard"          # "standard", "pushout", "glitch", "both"
    ic_count: int = 0                      # Number of .ic statements (if IC style)
    description: str = ""                  # Human-readable description


class SelectionError(Exception):
    """Raised when no template family matches the requested combination.

    Contains what was tried (cell_class, arc_type, direction) and a list
    of closest partial matches for diagnostic output.
    """
    def __init__(self, message: str, tried: dict = None, closest: list = None):
        super().__init__(message)
        self.tried = tried or {}
        self.closest = closest or []

    def __str__(self):
        base = super().__str__()
        if self.tried:
            tried_str = ", ".join(f"{k}={v}" for k, v in self.tried.items())
            base = f"{base}\n  Tried: {tried_str}"
        if self.closest:
            base = f"{base}\n  Closest matches:\n"
            for c in self.closest:
                base += f"    - {c}\n"
        return base
