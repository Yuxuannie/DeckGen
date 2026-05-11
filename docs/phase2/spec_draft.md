# Phase 2 Spec Draft: Principle-Driven Deck Generation

## 1. Architecture Decision Record

### Decision: Select + Parameterize (Architecture A)

The principle engine selects a template family from a reduced library
(~50-70 families, down from 457 individual templates), then fills it with
parameters derived from the arc specification and cell topology.

### What "select" means

A **cell topology classifier** inspects the cell's `define_cell` attributes
(from template.tcl) and cell name, then assigns it to one of ~15 topology
classes (common, latch, flop, MB, EDF, SLH, ESLH, RCB, SYNC, DET, DIV4,
DRDF, retn, basemeg, AO22/OA22). Combined with the arc signature
`(arc_type, rel_pin_dir, constr_pin_dir, measurement_type)`, this produces
a **template family key** that indexes into the reduced library.

The selection chain:

```
(cell topology, arc_type, direction, measurement) -> template family key
                                                       |
                                              template library lookup
                                                       |
                                              parameterized template
```

Source: Task B found 8 discrimination categories, of which "internal
topology" is the dominant axis (250+ rules, 15 sub-types). The classifier
replaces the 18K-line if-chain by encoding these 15 types as explicit
categories rather than name-pattern matching.
[B_rule_groupby.md SS2, F_feasibility_verdict.md SS2]

### What "parameterize" means

Once a template family is selected, these parameters are bound:

| Parameter class | Source | Examples |
|----------------|--------|---------|
| Pin names | Arc spec (from template.tcl) | `$REL_PIN`, `$CONSTR_PIN`, `$PROBE_PIN_1` |
| Directions | Arc spec | rise/fall -> waveform phase selection |
| Electrical values | Corner + LUT index | `$VDD_VALUE`, `$INDEX_1_VALUE`, `$OUTPUT_LOAD` |
| Polarity | Probe pin identity | maxq (Q probe) vs minq (QN probe) |
| Pipeline depth | Cell topology | sync2..sync6 -> timing var count = 2N+2 |
| Glitch threshold | Char.tcl cascade | `$GLITCH` from global/cell/arc override |
| Pushout percentage | Char.tcl cascade | `$PUSHOUT_PER` |
| Initialization | Cell topology + arc type | .ic/.nodeset statements |
| When-condition pins | Arc spec | Side-pin voltage sources |
| Dont-touch pins | Template header | Excluded from pin assignments |

Source: Phase 1 archaeology SS6-SS7 (timingArcInfo + spiceDeckMaker).
These are the same `$VAR` substitution and pin-biasing operations MCQC
performs, but the template they operate on is selected by principle
rather than name-pattern.

### Why emit-from-scratch was rejected

Three lines of evidence:

1. **Near-1:1 template-to-family ratio** (Task C: avg cluster size 1.11).
   Templates are already near-minimal -- there is no "common structure"
   to factor out. Generating from scratch would reconstruct these
   templates with no compression benefit.
   [C_template_path_clusters.md SS6]

2. **98.9% BNF grammar coverage** (Task C). Template names are highly
   structured, meaning they are already the principled representation.
   The structure IS the principle.
   [C_template_path_clusters.md SS1]

3. **Regression testability**. Select+parameterize can diff output against
   v1 byte-for-byte. Emit-from-scratch cannot -- any whitespace difference,
   comment difference, or line ordering change creates false diff noise
   that obscures real bugs.
   [F_feasibility_verdict.md SS5]

### The 45-55 estimate, numerically

```
Trivial side:    228 signatures -> 32 families -> ~20 principles (parameterize direction/pin)
Discriminating:  115 signatures -> 38 raw sub-principles -> ~30 compressed
  Internal topology:  15 -> ~12 (some ic_count=2 classes merge; E.2 confirmed non-compressible)
  Gate-type logic:     6 ->  3 (ckg/ckgn collapse, ckgmux2/3 collapse)
  Output polarity:     2 ->  1 (parameterize)
  Retention depth:     6 ->  1 (parameterize depth=N; but syn2/synx need IC, syn3-6 do not)
  Multi-input:         1 ->  1 (enumerate pins)
  MUX port count:      2 ->  2 (different thresholds)
  Scan/test:           4 ->  4 (irreducible)
  Per-cell override:   2 ->  ~3-5 escape-hatch entries
Delay ecosystem:  +5-10 (OPTIMIZE .tran, delay-specific topologies, Spectre parallel set)
                          ------
Subtotal:             ~50-65 principles + ~5 escape-hatch entries
```

[F_feasibility_verdict.md SS1-SS4, revised by E2_sampling_results.md]

> **E.2 revision**: Original estimate was 45-55. E.2 sampling revealed the
> `delay/` ecosystem adds 5-10 principles not captured in the original
> analysis (OPTIMIZE .tran, delay-specific cell topologies like seq_inpin,
> Spectre parallel families). Additionally, syn2 retention requires IC init
> while syn3-6 do not, adding a topology-conditional init axis. Revised
> estimate: **50-65 principles**.

### 1.X Resolved: Topology Sub-Principle Compressibility

> **RESOLVED** (2026-05-11). Task E.2 sampling completed. Verdict: **PARTIAL
> compression -- topology sub-types are structurally distinct**.

**Evidence** (from `docs/foundation/E2_sampling_results.md`):

The 899-template corpus has three mutually exclusive init styles, all
template-embedded (no runtime dispatch):

| Init style | Templates | % | Directories |
|---|---:|---:|---|
| NONE (V-source biasing only) | 604 | 67% | hold, setup, nochange, non_seq_* (majority) |
| IC (embedded `.ic`) | 169 | 19% | delay (91), hold (56), nochange (14), non_seq (7), nochange_low_high (1) |
| NODESET (embedded `.nodeset`) | 126 | 14% | mpw (63), min_pulse_width (63) |

Within `.ic`-using templates, `ic_count` is deterministic by cell topology:

| Cell topology | ic_count | Structural implication |
|---|---:|---|
| simple gates (latch_S, RCB, CKG) | 2 | slave latch only |
| EDF (edge-detect FF) | 4 | master + slave |
| MB (multi-bank) | 8 | multi-bank master + slave |
| synx retention | 14 | full pipeline chain |
| syn2 retention | 16 | asymmetric 2-stage (deepest) |
| seq_inpin | 1 | output Q only |

**Verdict**: Topology sub-types are **structurally distinct** -- they differ
in ic_count, `.ic` node patterns, `.meas` count, and `.tran` style. The 15
sub-principles cannot be compressed to fewer than ~12 (some collapse:
latch_S + RCB share ic_count=2 structure). The principle count estimate is
revised upward to **50-65** (was 45-55).

**Additional finding: `delay/` is its own ecosystem.** 91 of 169 `.ic`
files, 97% of 94 Spectre files, and all OPTIMIZE-style `.tran` lines live
in `delay/`. This was not captured in the original Phase 1.5 analysis.
Delay arcs have a fundamentally different `.tran` command (`OPTIMIZE`
instead of `monte=1`) and a parallel Spectre template set (94
`.thanos.sp` files). The classifier MUST handle delay separately.

**Impact on Phase 2A**: The blocker is now resolved. Phase 2A can begin.
The classifier must distinguish all 15 topology classes (no merging).
The `init_strategy.py` module is demoted from a runtime dispatcher to a
metadata reader -- init style is a property of the template, not a
decision made at generation time.

---

## 2. Module Boundaries

### 2.1 New modules (Phase 2)

```
core/principle_engine/
    __init__.py
    classifier.py       Cell topology classifier
    selector.py         Template family selector (backend-aware)
    param_binder.py     Parameter binding and value resolution
    init_style.py       Init style metadata reader (not a dispatcher)
    measurement.py      Measurement profile dispatcher
    families.py         Template family registry (reduced library)
    engine.py           Top-level orchestrator (public API)
    backends/
        __init__.py
        hspice.py       HSPICE-specific deck assembly
        spectre.py      Spectre-specific deck assembly
```

#### `core/principle_engine/classifier.py`

**Responsibility**: Classify a cell into one of ~15 topology classes based
on `define_cell` attributes and cell name patterns.

```python
class CellClass(Enum):
    COMMON = "common"
    LATCH = "latch"
    FLOP = "flop"
    MB = "mb"              # multi-bank
    EDF = "edf"            # edge-detect flip-flop
    SLH = "slh"            # scan latch
    ESLH = "eslh"          # extended scan latch
    RCB = "rcb"            # register-controlled buffer
    SYNC = "sync"          # synchronizer (depth parameterized)
    DET = "det"            # detector
    DIV4 = "div4"          # divider
    DRDF = "drdf"          # dual-rail dual-flop
    RETN = "retn"          # retention
    BASEMEG = "basemeg"    # memory (WWL-based)
    CKG = "ckg"            # clock gater (sub-typed by gate logic)

def classify_cell(cell_name: str, cell_obj=None) -> CellClass:
    """Classify cell by topology. Uses cell_obj attributes if available,
    falls back to name-pattern matching."""
```

**Inputs**: Cell name (str), optionally parsed `Cell` object from template.tcl.
**Outputs**: `CellClass` enum value.
**Depends on**: `core/parsers/template_tcl.py` (for `Cell` object).
**Replaces**: The cell-name pattern matching scattered across 688 rules in
`template_rules.json` / the 18K-line if-chain.

#### `core/principle_engine/backends/` (NEW -- E.2 finding)

**Responsibility**: Backend-specific deck assembly. Each backend implements
a uniform interface; `engine.py` calls backend hooks and never emits
backend-specific syntax directly.

```python
class Backend(Enum):
    """Simulator backend.
    NOT a selector parameter -- selection is backend-agnostic.
    Used in TemplateFamily.available_backends and assert_backend_available().

    E.3 clarification (2026-05-11): Spectre is a PARALLEL OUTPUT FORMAT for
    the same logical family, not a separate family registered by backend.
    A family can have both hspice_template_path and spectre_template_path.
    FMC Spectre coverage is incremental: latch=25, AO22=16, common=10, ...
    E.3 confirmed all 94 Spectre files share identical structural pattern."""
    HSPICE = "hspice"    # .sp files
    SPECTRE = "spectre"  # .thanos.sp files

class TranStyle(Enum):
    """Transient simulation command style for HSPICE.
    Stored on TemplateFamily as metadata; Spectre always uses tranIter.
    Source: E2_sampling_results.md SS A (.tran style binding table)."""
    MONTE_CARLO = "monte"      # .tran 1p 5000n sweep monte=1. Hold/setup/mpw/nochange.
    OPTIMIZE = "optimize"      # .tran 1p 5000n sweep OPTIMIZE=OPT1. HSPICE delay.
    BARE = "bare"              # .tran 1p 400ns. Simple HSPICE delay (seq_inpin).
    SPECTRE_TRAN_ITER = "spectre_tran"  # Informational; Spectre always uses tranIter.

class UnsupportedBackendError(Exception):
    """Raised by TemplateFamily.assert_backend_available() when requested
    backend has no template. Distinct from SelectionError (no family found)."""
```

**TemplateFamily dual-path shape** (2026-05-11 correction):

```python
@dataclass
class TemplateFamily:
    key: str
    hspice_template_path: Optional[str] = None   # .sp file; None if not available
    spectre_template_path: Optional[str] = None  # .thanos.sp file; None if not available
    tran_style: TranStyle = TranStyle.MONTE_CARLO  # HSPICE tran style (Spectre always tranIter)
    init_style: InitStyle = InitStyle.NONE
    ...
    @property
    def available_backends(self) -> Set[Backend]: ...

    def assert_backend_available(self, backend: Backend) -> None:
        """Raises UnsupportedBackendError if backend has no template.
        FMC Spectre rollout is incremental; many families HSPICE-only."""
```

**Files**:
- `core/principle_engine/backends/__init__.py`
- `core/principle_engine/backends/hspice.py` -- `emit_options()`,
  `emit_tran()`, `emit_simulator_directive()` for HSPICE
- `core/principle_engine/backends/spectre.py` -- same interface for Spectre
  (`simulator lang=spectre` switching, `tranIter`, Spectre `.options`)

**Depends on**: `families.py` (TemplateFamily.hspice_template_path / spectre_template_path).
**Replaces**: Hardcoded HSPICE syntax in `core/deck_builder.py` (which
stays for v1 path; v2 uses backend dispatch).

#### `core/principle_engine/selector.py`

**Responsibility**: Given (cell_class, arc_type, direction, measurement_type,
probe_info, backend, tran_style), select the correct template family from
the registry.

```python
def select_template_family(
    classification: ClassifierResult,
    arc_type: str,
    rel_pin_dir: str,
    constr_pin_dir: str,
    measurement: MeasurementProfile = None,
    probe_info: ProbeInfo = None,
) -> TemplateFamily:
    """Select template family. Backend-agnostic -- returns TemplateFamily
    with hspice_template_path and/or spectre_template_path set.
    Caller calls family.assert_backend_available(backend) before assembly.
    Raises SelectionError with what was tried and closest matches."""
```

**Inputs**: Classification result + arc electrical characteristics.
**Outputs**: `TemplateFamily` (dual template paths, init style, param schema).
  Caller asserts backend availability after selection.
**Depends on**: `classifier.py`, `families.py`.
**Replaces**: `core/template_rules.py` (688-rule JSON lookup) and
`core/template_map.py` (if-chain port).

> **2026-05-11 correction**: `backend` parameter removed from
> `select_template_family`. Selection is backend-agnostic. Backend
> validation moves to `TemplateFamily.assert_backend_available(backend)`
> (raises `UnsupportedBackendError` if the family lacks the requested
> template). This correctly models Spectre as a parallel output format
> rather than a separate family axis.

#### `core/principle_engine/param_binder.py`

**Responsibility**: Bind concrete values to a template family's parameter
slots. Resolves slew/load from LUT indices, VDD/temp from corner, glitch/pushout
from char.tcl cascade.

```python
def bind_parameters(
    family: TemplateFamily,
    arc_info: dict,          # from arc_info_builder or template.tcl parse
    corner_info: dict,       # from corner parser
    chartcl_overrides: dict, # from chartcl parser
) -> dict:
    """Return filled parameter dict ready for deck_builder substitution."""
```

**Inputs**: Template family + arc/corner/chartcl data.
**Outputs**: `dict` with keys matching `$VAR` names in template.
**Depends on**: `core/parsers/corner.py`, `core/parsers/chartcl.py`,
`core/parsers/template_tcl.py`.
**Replaces**: The parameter assembly in `core/arc_info_builder.py`
(partially -- arc_info_builder stays for v1 path).

#### `core/principle_engine/init_strategy.py`

**Responsibility**: Determine which initialization strategy a given
(cell_class, arc_type) combination requires.

```python
class InitStyle(Enum):
    """Template-embedded init style. Metadata, not a runtime decision.
    Determined by Task E.2 sampling of 899 templates."""
    NONE = "none"         # 604 templates (67%). V-source biasing + DONT_TOUCH_PINS only.
    IC = "ic"             # 169 templates (19%). Embedded .ic statements. ic_count determined by cell topology.
    NODESET = "nodeset"   # 126 templates (14%). Embedded .nodeset statements. 100% in mpw/min_pulse_width.

def get_init_style(family: TemplateFamily) -> InitStyle:
    """Read init style from template family metadata. NOT a classifier
    decision -- init style is a property of the template file itself."""
```

**Inputs**: Template family (after selection).
**Outputs**: `InitStyle` enum (read from family metadata).
**Depends on**: `families.py` (template family registry).
**Role**: Metadata reader, not dispatcher. Task E.2 confirmed that all
three init styles are template-embedded. The Python deck-generation code
does NOT generate `.ic` or `.nodeset` statements -- it only does `$VAR`
substitution and pin biasing.

> **E.2 verification** (from `docs/foundation/E2_sampling_results.md`):
> Init style distribution: NONE (604, 67%), IC (169, 19%), NODESET (126,
> 14%). Mutually exclusive (0 templates use both). ic_count is
> deterministic by cell topology: latch/RCB/CKG=2, EDF=4, MB=8,
> synx=14, syn2=16. The module `init_strategy.py` is renamed to
> `init_style.py` to reflect its metadata-reader role.

#### `core/principle_engine/measurement.py`

**Responsibility**: Determine measurement profile (pushout-only, glitch,
or both) and probe polarity (maxq/minq).

```python
class MeasurementProfile:
    has_pushout: bool
    has_glitch: bool
    polarity: str          # "maxq" or "minq"
    glitch_threshold: str  # from chartcl cascade
    pushout_per: str       # from chartcl cascade

def get_measurement_profile(
    arc_type: str, cell_class: CellClass,
    probe_pin: str, output_pins: list,
    chartcl_overrides: dict,
) -> MeasurementProfile:
```

**Inputs**: Arc type, cell class, probe pin identity, chartcl overrides.
**Outputs**: `MeasurementProfile`.
**Depends on**: `classifier.py`, `core/parsers/chartcl.py`.
**Replaces**: The implicit glitch/pushout/polarity logic in the 18K-line
if-chain and in `spiceDeckMaker/funcs.py` glitch line substitution.

#### `core/principle_engine/families.py`

**Responsibility**: Registry of template families. Each family is a
parameterized template with metadata (init strategy, measurement profile,
parameter schema, base template path).

```python
class TemplateFamily:
    key: str               # e.g., "hold/common/rise_fall"
    template_path: str     # relative path to .sp file
    init_strategy: InitStrategy
    param_schema: list     # required $VAR names
    measurement: str       # "pushout", "glitch", "both"

def load_families(families_dir: str) -> dict[str, TemplateFamily]:
    """Load family registry from YAML or JSON config."""
```

**Inputs**: Config directory.
**Outputs**: Dict mapping family key -> TemplateFamily.
**Depends on**: Filesystem (template library at `templates/v2/`).
**Replaces**: `config/template_registry.yaml` (for v2 path).

Loads template families from `templates/v2/` directory of real `.sp` files
(Q4 decision). Pipeline-depth parameterization (e.g., SYNC depth) uses base
templates with a Python composition step where structural substitution is
required.

#### `core/principle_engine/engine.py`

**Responsibility**: Top-level orchestrator. Public API for the principle
engine path.

```python
def generate_deck_v2(
    cell_name: str, arc_type: str,
    rel_pin: str, rel_dir: str,
    constr_pin: str, constr_dir: str,
    probe_pin: str, when: str,
    corner_info: dict,
    template_tcl_info=None,
    chartcl_info=None,
    netlist_path: str = None,
    model_path: str = None,
    waveform_path: str = None,
) -> str:
    """Generate SPICE deck using principle engine.
    Returns deck content as string, or raises with diagnostic."""
```

**Inputs**: Same as v1's `resolve_all` + `build_deck`, unified.
**Outputs**: SPICE deck string.
**Depends on**: All other principle_engine modules + `core/deck_builder.py`
(reused for `$VAR` substitution), `core/writer.py` (reused for file output).

### 2.2 Existing modules: changes

| Module | Change | Rationale |
|--------|--------|-----------|
| `core/resolver.py` | Add `engine` parameter to `resolve_all` | Routes to v1 or v2 path |
| `core/deck_builder.py` | No changes | Reused by v2 for `$VAR` substitution |
| `core/writer.py` | No changes | Reused by v2 for file output |
| `core/template_rules.py` | No changes (frozen) | v1 path preserved |
| `core/template_map.py` | No changes (frozen) | v1 path preserved |
| `core/arc_info_builder.py` | No changes (frozen) | v1 path preserved |
| `core/batch.py` | Add `engine` parameter | Passes engine choice to resolver |
| `deckgen.py` | Add `--engine` CLI flag | User selects v1/v2 |
| `gui.py` | Add engine toggle | User selects v1/v2 in GUI |

---

## 3. v1/v2 Coexistence Strategy

### Engine selection

- CLI: `--engine legacy` (default) or `--engine principle`
- GUI: Toggle in settings bar, default `legacy`
- Default stays `legacy` until the regression suite is green for the
  full 20-cell set. Switching default is a separate decision after
  Phase 3 ships.

### Fallback behavior

When `--engine principle` is active:

1. Classifier runs on the cell. If classification succeeds, proceed with v2.
2. If classifier returns `UNKNOWN` (cell does not match any known topology):
   - Log at WARNING: "Cell {name} not classified, falling back to v1 engine"
   - Route to v1 path (template_rules.json lookup)
   - Include `[FALLBACK:v1]` tag in deck header comment
3. If v2 selection succeeds but parameterization fails (e.g., missing
   char.tcl override for a required parameter):
   - Log at WARNING with the specific missing parameter
   - Fall back to v1 path
   - Include `[FALLBACK:v1:param_bind]` tag in header

No silent fallback. Every fallback is logged and tagged in output.

### Diff mode

A `--diff` flag (CLI) or "Compare engines" button (GUI) runs both v1 and
v2 on the same arc, then reports:

- `BYTE_EQUAL`: outputs are identical
- `SEMANTIC_EQUAL`: outputs differ only in comments, whitespace, or
  line ordering of equivalent blocks
- `DIFFERS`: structural difference (different template, different values,
  different pin assignments)
- For `DIFFERS`: show a unified diff with annotations on what category
  each difference falls into

### template_registry.yaml

Frozen as-is. Not deleted, not modified. v1 path continues to use it.
v2 path does not read it. It serves as a regression reference and as
the documentation of "what MCQC does" for debugging v2 mismatches.

### template_rules.json

Same: frozen, not deleted. The 37 `arc_type: "unknown"` entries
(B_audit_d3_d5.md) will be fixed via Patch 5 (see below). The v2
classifier implements the same corrections via attribute-based
classification.

### Pre-Phase-2 data fixes

A separate Patch 5 commit on feat/foundation-closure fixes:
1. The 37 `arc_type: "unknown"` entries in `template_rules.json`
   (B_audit_d3_d5.md). v1 immediately benefits from a 5.4%
   false-negative rate reduction.
2. The 4 known OR-alternative extraction diffs in
   `template_rules.json` (A_templatefilemap_check.md, R6 in SS6).

These are data fixes, not architecture changes. v2 classifier
implements the same logic via attribute-based classification, so
v2 is correct regardless of whether v1 data is fixed. Fixing v1
data is for SCLD's benefit while they remain on v1 during Phase 2
development.

The Patch 5 commit is a prerequisite for Phase 2B, not 2A.

---

## 4. MVP Scope

### Arc types in scope

| Arc type | In MVP? | Rationale |
|----------|---------|-----------|
| **hold** | Yes | Largest rule set (255 rules), exercises all 8 discrimination categories, most complex templates |
| **setup** | Yes | Fully trivial (10 rules, all signature-determined) -- validates that trivial path works |
| **min_pulse_width** | Yes | 63 shipped templates available for structural validation (Task D), exercises SYNC scaling |
| **delay** | Yes | E.2 finding: delay/ is its own ecosystem (91 .ic files, 91 Spectre files, all OPTIMIZE .tran). Cannot validate architecture without it. HSPICE delay only in MVP; Spectre delay deferred to Phase 2C |
| removal | No | Uses hold templates (shares directory), defer to Phase 2C |
| nochange_* | No | 130 templates, unique waveform model, needs its own validator -- Phase 2C |
| non_seq_hold/setup | No | Async control + retention, most complex init -- Phase 2C |

**Why hold + delay**: Hold is the hardest constraint arc (255 rules, 204
templates, all 8 discrimination categories). Delay is the hardest
non-constraint arc (its own ecosystem: OPTIMIZE .tran, .ic-heavy, Spectre
parallel set). Together they exercise the two fundamentally different
measurement paradigms (monte=1 vs OPTIMIZE). Setup validates the trivial
path. MPW validates against the 63 shipped templates.

### Cell families in scope (MVP)

| # | Cell family | Topology class | Init style (E.2 verified) | Measurement | Why |
|---|-------------|---------------|---------------------------|-------------|-----|
| 1 | Standard FF (DFFQ1, SDFQ1) | COMMON | NONE for hold; NODESET for mpw | pushout | Baseline: simplest hold arc |
| 2 | Latch (LHQD1) | LATCH | IC (ic_count=2) for hold; NONE for setup | glitch (maxq/minq) | Tests glitch polarity + IC init |
| 3 | Multi-bank (MB*SRLSDF*) | MB | IC (ic_count=8) for hold | glitch | Tests multi-input expansion (AO22) + deep IC init |
| 4 | Synchronizer (SYNC2-6) | SYNC | NODESET for mpw (verified: 16 lines) | pushout | Tests depth parameterization + waveform scaling |
| 5 | Clock gater (CKGAN2*, CKGND2*) | CKG | NONE for hold; IC (ic_count=2) for hold/nx variants | pushout | Tests gate-type sub-classification (AND vs NAND) |
| 6 | Retention flop (*RETN* + *RSSDF*) | RETN | IC (ic_count=4) for non_seq_hold; NONE for base retn | glitch (maxq/minq) | Smoke-tests deep IC init; same cell as regression suite #18 |
| 7 | Delay inverter / FF (HSPICE) | COMMON/EDF | IC (ic_count=1-4) for delay; OPTIMIZE .tran; HSPICE-only | delay (cp2q) | Validates delay ecosystem: OPTIMIZE .tran, .ic init, different measurement paradigm |
| 8 | Latch delay (dual-backend) | LATCH | IC (ic_count=2); both HSPICE and Spectre templates available | delay (cp2q) | Validates dual-backend path: assert_backend_available(HSPICE) and (SPECTRE) both pass; E.3: latch=25 is largest Spectre cell family |

> **2026-05-11 reframe** (Patch 6a): Family 8 was originally "AO22 delay
> (Spectre-only)" -- a single-backend Spectre smoke test. It is now "latch
> delay (dual-backend)" -- a dual-backend validation target.  Reason: E.3
> sampling confirmed latch=25 is the largest Spectre cell family, making
> latch the best representative for the dual-path mechanism. AO22 (16
> Spectre files, Spectre-only) remains in the registry as a supplementary
> entry validating the `hspice_template_path=None` / `UnsupportedBackendError`
> path; it is no longer an MVP family.

These 8 families exercise:
- **All 3 init styles** (E.2 verified): NONE (families 1/5/8), IC
  (families 2/3/5nx/6/7), NODESET (families 1/4 mpw)
- **Both backends**: HSPICE (families 1-7) and SPECTRE (family 8)
- **All 3 .tran paradigms**: monte=1 (hold/setup/mpw), OPTIMIZE (delay
  HSPICE), tranIter (delay Spectre)
- Both measurement criteria (pushout + glitch)
- Output polarity dispatch (latch family)
- Depth parameterization (SYNC)
- Multi-input expansion (MB in HSPICE)
- Dual-backend dispatch (latch family 8: both HSPICE and Spectre paths)
- Gate-type sub-classification (CKG)
- Retention IC init smoke test (family 6)
- Delay HSPICE smoke test (family 7)
- Spectre backend smoke test (family 8)

> **Risk note**: MVP includes retention via family 6, HSPICE delay via
> family 7, and Spectre delay via family 8 as smoke tests. Full retention
> coverage (multiple variants, all arc types), full delay coverage
> (seq_inpin, SDFNQSXGD families), and full Spectre coverage (non-AO22
> Spectre files) are still scoped to Phase 2C/2D.
> Family 6 uses non_seq_hold arcs only; family 8 covers one Spectre
> cell pattern only.

### Explicit out-of-scope for MVP

- Retention cells beyond family 6 smoke test: full retention coverage
  (multiple variants, all arc types) deferred to Phase 2C
- DET/DRDF/DIV4: specialized topologies, low volume
- SLH/ESLH: scan-specific, deferred
- basemeg (WWL*): memory cells, specialized
- nochange waveform model: different from hold/setup
- Spectre backend (94 `.thanos.sp` files): HSPICE only in MVP; Spectre
  delay deferred to Phase 2C
- Delay families beyond family 7 smoke test (seq_inpin, SDFNQSXGD):
  deferred to Phase 2C
- GUI code changes beyond the engine toggle

### Acceptance criteria

MVP is done when:
1. `--engine principle` produces byte-equal output to `--engine legacy` for
   all `(cell, arc_type, corner)` combinations in the 5-family MVP set,
   across all table points
2. AIOI21 12 assertions still green
3. Fallback-to-v1 triggers for cells outside the 5 families with a clear
   log message (no silent drop, no crash)
4. `--diff` mode works and reports `BYTE_EQUAL` for all MVP cells

---

## 5. Regression Strategy

### 20-cell regression suite

Selected to cover all 8 discrimination categories from Task B, all 3 init
strategies, and both measurement types. Cells chosen from names observed in
`template_rules.json` cell_pattern fields:

| # | Cell pattern | Category covered | Init | Meas | Arc types |
|---|-------------|------------------|------|------|-----------|
| 1 | DFFQ1* | Common FF (fallback) | nodeset | pushout | hold, setup, mpw |
| 2 | SDFQ1* | Common FF + scan | nodeset | pushout | hold, setup, mpw |
| 3 | LHQD1* | Latch | nodeset_latch | glitch | hold |
| 4 | AIOI21* | Combinational (ground truth) | -- | -- | delay |
| 5 | *SYNC2*Q* | Sync2 (Q1 probe) | nodeset | pushout | hold, mpw |
| 6 | *SYNC4* | Sync4 (depth scaling) | nodeset | pushout | hold, mpw |
| 7 | MB*SRLSDF* | Multi-bank | nodeset_latch | glitch | hold |
| 8 | MB2SRLSDFAO22* | Multi-bank + AO22 expansion | nodeset_latch | glitch | hold |
| 9 | *EDF*D* | Edge-detect FF | nodeset | glitch | hold |
| 10 | *SLH*QSO* | Scan latch hold | nodeset_latch | pushout | hold |
| 11 | DCCKDIV4* | Divider | nodeset | pushout | hold |
| 12 | *DRDF* | Dual-rail dual-flop | nodeset | pushout | mpw |
| 13 | *DET* | Detector | nodeset | pushout | mpw |
| 14 | CKGAN2* | Clock gater (AND) | nodeset | pushout | hold, nochange |
| 15 | *CKG*ND2* | Clock gater (NAND) | nodeset | pushout | hold, nochange |
| 16 | *CKGMUX2* | Clock gater (MUX2) | nodeset | pushout | nochange |
| 17 | DCCKSDIV2* | GCLK divider (scan variants) | nodeset | pushout | hold |
| 18 | *RETN* + *RSSDF* | Retention flop (= MVP family 6) | ic_retention | glitch | non_seq_hold |
| 19 | *RCB* | Register-controlled buffer | nodeset | pushout | hold |
| 20 | *basemeg* (WWL) | Memory cell | nodeset | glitch | hold |

### v1 baseline

For each cell in the suite, the v1 baseline is the output of
`--engine legacy` on the same `(cell, arc, corner, table_point)`.
Baselines are generated once and committed to `tests/fixtures/regression/`.

### Diff tool

Primary: byte-equal comparison (`diff -q`). If byte-equal, PASS.

If byte-different, secondary analysis:
1. Strip comment lines (`* ` prefix) and compare -> `SEMANTIC_EQUAL` if now equal
2. Normalize whitespace (collapse runs of spaces) and compare
3. Sort `.meas` blocks and compare (order may differ)
4. If still different: `DIFFERS` with unified diff output

**Acceptable diff criterion**: Only `BYTE_EQUAL` or `SEMANTIC_EQUAL` pass.
`DIFFERS` is a failure that must be investigated. If the difference is
intentional (v2 produces a provably better deck), it must be documented in
`tests/fixtures/regression/ACCEPTED_DIFFS.md` with justification.

### Known v1 bugs: exemption from byte-equal

v1 has known bugs documented in Phase 1.5:
- **37 rules with `arc_type: "unknown"`** (B_audit_d3_d5.md): extraction
  artifact causing 5.4% false-negative rate. These rules produce no output
  in v1 for affected cells/arcs.
- **13.3% OR-alternative incomplete extraction** (A_templatefilemap_check.md):
  rules with secondary pin names (e.g., `CLK` alternative for `CP`) not
  captured. Affected arcs may fail to match in v1.

These bugs mean v1 output is itself incorrect for some cell/arc combinations.
Forcing v2 to reproduce these bugs for byte-equal parity would be harmful.

**Handling**: `tests/fixtures/regression/KNOWN_V1_BUGS.md` lists cells/arcs
where v1 is known to produce wrong output. Format:

```
| Cell pattern | Arc type | Bug class | Source |
|-------------|----------|-----------|--------|
| *SYNC2* | min_pulse_width | unknown arc_type (no v1 output) | B_audit_d3_d5.md |
| *DRDF* | min_pulse_width | unknown arc_type (no v1 output) | B_audit_d3_d5.md |
| ... | | | |
```

**Regression behavior for KNOWN_V1_BUGS entries**:
- v2 output is NOT compared byte-equal to v1
- Instead: v2 output is reviewed manually and committed as a new baseline
  in `tests/fixtures/regression/v2_baselines/`
- The test reports `V2_IMPROVED` (not `PASS` or `FAIL`) for these entries
- Over time, as v1 bugs are fixed, entries are removed from KNOWN_V1_BUGS
  and the standard byte-equal comparison resumes

**Criteria for adding a cell to KNOWN_V1_BUGS**:
1. The v1 output for this cell/arc is demonstrably wrong (produces no deck,
   or produces a deck with incorrect template/parameters)
2. The wrongness traces to a documented v1 bug (B_audit, A_check, or a new
   finding with the same rigor)
3. The entry includes a reference to the source document proving the bug
4. Entries are reviewed by Yuxuan before adding (no unilateral additions)

### CI integration

- `tests/test_v1_v2_parity.py`: pytest parametrized over 20 cells x M
  corners x P table points
- Runs as part of `python -m pytest tests/`
- Requires `--engine principle` to be functional (skipped if not)
- AIOI21 assertions remain a separate, always-run test
- KNOWN_V1_BUGS entries produce `V2_IMPROVED` status, not `FAIL`

---

## 6. Risk Register

### R1: Classifier accuracy below threshold

**Description**: The 15-class topology classifier misclassifies cells,
routing them to wrong templates.
**Likelihood**: Medium. Name-pattern matching (MCQC approach) is fragile
but well-tested. Attribute-based classification is more principled but
untested.
**Impact**: Wrong deck output. Silent corruption if diff mode is not used.
**Mitigation**: (1) Hybrid classifier: try attribute-based first, fall back
to name-pattern. (2) 20-cell regression suite catches misclassification
before merge. (3) Fallback-to-v1 for unknown cells.

### R2: Missed discrimination axis

**Description**: A structural difference between templates that is not
captured by any of the 8 categories from Task B. Could surface when
processing cells outside the 20-cell regression suite.
**Likelihood**: Low-Medium. Task B analyzed all 688 rules. But the analysis
was on rule *metadata*, not template *contents* (except for the 63 shipped
MPW templates in Task D). Task E sampling is designed to catch this.
**Impact**: Wrong deck output for specific cell/arc combinations.
**Mitigation**: (1) Task E results before code starts. (2) Expand
regression suite incrementally as new cell families are onboarded.
(3) `--diff` mode allows users to spot-check any cell.

### R3: v1 baseline has bugs reproduced into v2

**Description**: MCQC itself may have bugs (e.g., the 37 `unknown`
arc_type entries, the 13.3% OR-alternative false negatives). If v2
reproduces these bugs to achieve byte-equal parity, fixing them later
creates a second migration.
**Likelihood**: Medium. Task A found 4/30 rules with extraction diffs.
B_audit found 37 rules with wrong arc_type. Some of these likely
produce wrong decks in v1.
**Impact**: Technical debt. v2 inherits v1 bugs, then must fix them
separately.
**Mitigation**: (1) Document known v1 bugs in `KNOWN_V1_BUGS.md` (SS5).
(2) Patch 5 on feat/foundation-closure fixes the 37 `unknown` rules and
4 OR-alternative diffs in `template_rules.json` before Phase 2B starts
(SS3 "Pre-Phase-2 data fixes"). (3) v2 classifier handles these correctly
regardless via attribute-based classification.

### R4: Parameter binding edge cases

**Description**: Some template families require parameters that are only
available in specific char.tcl configurations (e.g., `amd_glitch`,
`smc_degrade`, `constraint_glitch_peak`). If the char.tcl does not provide
these, param_binder fails.
**Likelihood**: Medium. The char.tcl override cascade is 4 levels deep
(Phase 1 archaeology SS4, SS6) and vendor-specific.
**Impact**: Deck generation failure for specific corners/cells.
**Mitigation**: (1) param_binder uses same default cascade as MCQC
(global -> vendor -> cell -> arc). (2) Missing values fall back to
MCQC defaults (`PUSHOUT_PER=0.4`, `GLITCH` from template.tcl if
available). (3) Error message lists which parameter is missing and
which sources were checked.

### R5: Spectre backend pressure

**Description**: Yuxuan or downstream users request Spectre-format output
before Phase 2 ships, forcing concurrent HSPICE + Spectre support.
**Likelihood**: Low. MCQC only supports HSPICE and THANOS (FMC). Spectre
is a future request, not an active one.
**Impact**: Doubles the template library and complicates parameterization.
**Mitigation**: (1) Architecture A cleanly separates template selection
from template content. Spectre support = new template families, not new
selection logic. (2) Defer to Phase 3 unless explicitly requested.

### R6: OR-alternative false negatives affect v2 accuracy

**Description**: Task A found 13.3% of rules have incomplete OR-alternative
extraction. If these rules are used to *train* the classifier (rather than
just validate it), the classifier may learn incomplete conditions.
**Likelihood**: Low. The classifier is based on cell topology, not on rule
conditions. The OR-alternatives affect *pin name matching*, which v2 handles
by attribute-based classification rather than name matching.
**Impact**: If the classifier does use rule data for training: some cells
may be misrouted because an alternative pin name was not captured.
**Mitigation**: (1) Classifier uses cell attributes, not rule conditions.
(2) The 4/30 diff rate is for pin *alternatives* (e.g., `CP` vs `CLK`),
not for topology classification. (3) Fix the 4 known diffs in the JSON
as a Patch 5 before Phase 2 code starts.

### R7: Backend abstraction leakage

**Description**: HSPICE-specific assumptions may leak into the principle
engine's general code path, producing valid HSPICE but invalid Spectre
output (or vice versa). For example, hardcoded `.tran` syntax, hardcoded
`.options` keywords, or hardcoded measurement statement formatting that
works in one backend but not the other.
**Likelihood**: Medium. Spectre is only 10% of the corpus but 100% of
`delay/hold/AO22*` cells; selection bugs would silently produce HSPICE
output for a cell that needs Spectre, or vice versa.
**Impact**: Silent wrong output for one backend. The deck may parse but
fail simulation, or worse, simulate with wrong results.
**Mitigation**:
1. Backend-specific deck assemblers in
   `core/principle_engine/backends/{hspice,spectre}.py`, each implementing
   a uniform interface (`emit_options()`, `emit_tran()`,
   `emit_simulator_directive()`).
2. `engine.py` shared logic calls backend hooks; never emits backend-specific
   syntax directly.
3. Regression suite includes byte-equal verification for both backends per
   MVP arc, with separate baseline files
   `tests/fixtures/regression/v1_baselines/{hspice,spectre}/`.
4. Phase 2A classifier must include backend detection test in CI.

---

## 7. Open Questions for Yuxuan

### Q1: MVP arc type scope [RESOLVED -> (A) + 6th family]

**Decision**: (A) hold + setup + mpw, with a 6th MVP cell family
(`*RETN* + *RSSDF*`) added for IC_RETENTION init path smoke-testing.
See SS4 MVP table family 6.

### Q2: FMC simulation submission integration [RESOLVED -> (A)]

**Decision**: (A) deck generation only. Yuxuan's FMC estimator project is
independent; coordinate timing later. FMC integration is orthogonal to
the principle engine and can be added without architectural changes.

### Q3: GUI invasiveness [RESOLVED -> (B)]

**Decision**: (B) moderate debug panel. Phase 2D delivers:
- Engine toggle in settings bar
- Principle Engine debug panel (collapsible) showing per-arc:
  classification result, selected template family, parameter bindings,
  init strategy used, fallback status if applicable
- Panel sits under existing arc detail view, not a new tab

### Q4: Template library format [RESOLVED -> (A)]

**Decision**: (A) real `.sp` files in `templates/v2/`. Diffable against MCQC
originals. Pipeline-depth parameterization (e.g., SYNC depth) uses base
templates with a Python composition step where structural substitution is
required.

### Q5: Should the 37 `unknown` arc_type rules be fixed before Phase 2? [RESOLVED -> (C)]

**Decision**: (C) fix both JSON for v1 and classifier for v2. The JSON fix
is low-risk (data change, not logic) and immediately improves v1's 5.4%
false-negative rate. Implementation: Patch 5 on feat/foundation-closure
(see SS3 "Pre-Phase-2 data fixes" subsection). Patch 5 is a prerequisite
for Phase 2B, not 2A.

### Q6: Task E template samples timeline [RESOLVED]

**Decision**: Task E.2 sampling completed (2026-05-08). Results in
`docs/foundation/E2_sampling_results.md`. SS1.X resolved. Phase 2A
blocker lifted.

### Q7: Spectre coverage breadth [RESOLVED -> (B)]

**Decision**: (B) Sample 3 more non-AO22 Spectre files before Phase 2C.
This is tracked as Task E.3 (in progress). E.3 is not on the critical
path for Phase 2A or 2B -- it must complete before Phase 2C starts.

Server-side command: `find . -name '*.thanos.sp' | grep -v 'AO22' | head -3`
then inspect each file's structure per the E_execution_plan.md fingerprint
extraction method.

---

## 8. Estimated Phase 2 Phasing

### Phase 2A: Classifier + Selector + Backend Abstraction [L]

**Delivers**:
- `core/principle_engine/classifier.py` with 15 topology classes
- `core/principle_engine/selector.py` with backend-aware family lookup
- `core/principle_engine/families.py` with initial family registry
- `core/principle_engine/backends/{hspice,spectre}.py` with uniform
  interface (`emit_options()`, `emit_tran()`, `emit_simulator_directive()`)
- `Backend` and `TranStyle` enums
- `tests/test_v1_v2_parity.py` regression harness (runs but expects
  failures for unimplemented families)
- `--engine principle` flag (CLI) that invokes classifier and reports
  classification result without generating decks

**Acceptance**: Classifier correctly labels all 8 MVP cell families
including latch dual-backend (family 8). Selector returns correct family
for hold, setup, mpw, AND delay arcs (backend-agnostic). Backend
validation via `family.assert_backend_available()` raises
`UnsupportedBackendError` for Spectre-only families when HSPICE requested.

**Complexity**: L (large -- upgraded from M). Backend abstraction is a
new architectural dimension: HSPICE vs Spectre file detection, delay-aware
classification given the high concentration of distinctive patterns in
delay/. The classifier, selector, and backend modules must all land
together for the abstraction to be testable.

**Sequencing**: Must be first. Everything depends on correct classification
and backend routing.

> **BLOCKER RESOLVED** (2026-05-11): Task E.2 sampling confirmed topology
> sub-types are structurally distinct (see SS1.X). The classifier must
> distinguish all 15 topology classes. ic_count is deterministic by
> topology. Phase 2A can begin.

### Phase 2B: Param Binder + HSPICE Hold/Setup/MPW Generation [L]

**Delivers**:
- `core/principle_engine/param_binder.py`
- `core/principle_engine/init_style.py`
- `core/principle_engine/measurement.py`
- `core/principle_engine/engine.py` (full pipeline, HSPICE path)
- Integration with `core/deck_builder.py` for `$VAR` substitution
- Hold + setup + MPW arc decks byte-equal to v1 for HSPICE MVP families
- Retention smoke test (family 6: `*RETN* + *RSSDF*`, non_seq_hold, IC init)
- Fix for the 37 `unknown` arc_type rules (Q5 decision: (C))

**Acceptance**: `--engine principle --diff` reports `BYTE_EQUAL` for all
hold/setup/mpw arcs in MVP families 1-6 across 3 corners, including the
syn2 retention smoke test (family 6). Fallback-to-v1 works for cells
outside MVP.

**Complexity**: L (large). Parameter binding is the most fiddly part --
matching MCQC's exact formatting, unit suffixes, cascade logic, and
dont-touch pin handling.

**Sequencing**: After 2A. Requires correct classification.

### Phase 2C: Delay (HSPICE) + Spectre Backend [L]

**Delivers**:
- HSPICE delay arc generation for family 7 (COMMON/EDF delay),
  including IC init handling and OPTIMIZE-style `.tran`
- Spectre backend support for family 8 (latch dual-backend) and AO22 (Spectre-only):
  - `core/principle_engine/backends/spectre.py` emission logic
  - `simulator lang=spectre` / `simulator lang=spice` switching
  - `tranIter tran stop=5000n` emission
  - Spectre-specific `.options` block
- Backend dispatch in `engine.py` based on `TemplateFamily.backend`
- `--diff` mode (CLI and GUI)

**Acceptance**: `BYTE_EQUAL` for delay arcs in HSPICE (family 7) AND
Spectre (family 8) across MVP corners. `--diff` mode functional.

**Complexity**: L (large). Three new architectural dimensions land
together: IC init for delay, OPTIMIZE `.tran`, Spectre backend. The
Spectre backend is a complete parallel deck assembler, not a patch on
HSPICE.

**Sequencing**: After 2B. Requires HSPICE param binding infrastructure.

### Phase 2D: Remaining Arc Types + Retention Expansion [L]

**Delivers**:
- Removal/recovery arcs (share hold template directory but have distinct
  measurement semantics)
- Non-seq hold/setup (async control pins CD/SDN, multi-phase stimulus)
- Nochange arcs (130 templates, distinct waveform model, embeds both
  hold+setup sub-arcs in filenames)
- Full retention diversity (multiple retention cell variants beyond
  family 6 smoke test)
- Full delay diversity (seq_inpin, SDFNQSXGD families)
- Expanded Spectre coverage (non-AO22 Spectre files if Q7 sampling
  reveals new patterns)
- Expanded regression suite: 20 cells x all arc types

**Acceptance**: `BYTE_EQUAL` for all 20 regression cells across all arc
types. Fallback rate < 5% on a broader cell population test.

**Complexity**: L (large). Nochange dual-arc embedding, async pin biasing,
130 nochange templates, and retention state machine depth all contribute.

**Sequencing**: After 2C. Requires delay and Spectre infrastructure.

### Phase 2E: GUI Integration + Documentation [S]

**Delivers**:
- GUI engine toggle in settings bar
- Principle Engine debug panel (collapsible, under existing arc detail view,
  not a new tab) showing per-arc: classification result, selected template
  family, parameter bindings, init style, backend, fallback status if
  applicable (Q3 decision)
- Updated `docs/design.md` with v2 architecture section
- Updated `CLAUDE.md` with v2 commands and conventions
- `docs/phase2/changelog.md` summarizing what shipped

**Acceptance**: GUI works with both engines. Debug panel shows correct
classification and parameter data for all 8 MVP cell families.
Documentation is complete.

**Complexity**: S (small). No new engine logic -- GUI integration and docs.

**Sequencing**: After 2D (or can start in parallel for the GUI toggle).

### Summary

| Sub-phase | Delivers | Size | Depends on |
|-----------|----------|------|------------|
| 2A | Classifier + selector + backend abstraction + delay-aware regression harness | L | Task E.2 (DONE) |
| 2B | Param binder + hold/setup/mpw generation + family 6 retention smoke test | L | 2A |
| 2C | Delay arcs (HSPICE) + Spectre backend | L | 2B |
| 2D | Nochange + non_seq_* + full retention + full delay diversity | L | 2C |
| 2E | GUI integration + documentation | S | 2D |
