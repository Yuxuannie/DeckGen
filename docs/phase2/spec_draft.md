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
  Internal topology:  15 -> 15 (not compressible)
  Gate-type logic:     6 ->  3 (ckg/ckgn collapse, ckgmux2/3 collapse)
  Output polarity:     2 ->  1 (parameterize)
  Retention depth:     6 ->  1 (parameterize depth=N)
  Multi-input:         1 ->  1 (enumerate pins)
  MUX port count:      2 ->  2 (different thresholds)
  Scan/test:           4 ->  4 (irreducible)
  Per-cell override:   2 ->  ~3-5 escape-hatch entries
                          ------
Subtotal:             ~50 principles + ~5 escape-hatch entries
```

[F_feasibility_verdict.md SS1-SS4]

### 1.X Open Architectural Question: Topology Sub-Principle Compressibility

> **This is the central uncertainty in the architecture.** It determines
> whether the engine has 35 or 55 principles, and whether some topology
> classes can be merged.

**The 15 internal-topology sub-principles are the least validated axis.**
We know they are structurally different from template *names* (Task C), but
we have not confirmed they are structurally different in template *contents*
for any directory except MPW (Task D). Specifically:

- **Verified** (Task D): All 63 shipped MPW templates use `.nodeset` (16
  lines each), zero `.ic`, `stdvs_mpw_*` waveform. Structural fingerprints
  collapse into 5 families. The principle hypothesis holds for MPW.
- **Unverified**: Hold, setup, nochange, non_seq_hold, non_seq_setup, delay
  templates are NOT shipped locally. We do not know whether `hold/common`,
  `hold/latch`, and `hold/MB` templates differ structurally (different init
  blocks? different `.meas` counts? different waveform models?) or only in
  parameterizable values.

**Task E sampling must complete before Phase 2A begins.** The 10 template
samples requested in `docs/foundation/E_sampling_request.md` are designed
to resolve this question with binary outcomes:
- If templates within the same arc-type directory share structural
  fingerprints (same `.meas` count, same timing var count, same init style),
  topology sub-types can be merged and the count drops toward 35.
- If they genuinely differ (e.g., `hold/latch` has `.ic` while `hold/common`
  has `.nodeset`), each needs its own template family and the count stays
  near 55.

**Phase 2A is explicitly blocked on Task E results.** Do not begin
classifier implementation until the structural hypothesis is validated.

---

## 2. Module Boundaries

### 2.1 New modules (Phase 2)

```
core/principle_engine/
    __init__.py
    classifier.py       Cell topology classifier
    selector.py         Template family selector
    param_binder.py     Parameter binding and value resolution
    init_strategy.py    Initialization strategy dispatcher
    measurement.py      Measurement profile dispatcher
    families.py         Template family registry (reduced library)
    engine.py           Top-level orchestrator (public API)
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

#### `core/principle_engine/selector.py`

**Responsibility**: Given (cell_class, arc_type, direction, measurement_type,
probe_info), select the correct template family from the registry.

```python
def select_template_family(
    cell_class: CellClass,
    arc_type: str,
    rel_pin_dir: str,
    constr_pin_dir: str,
    measurement: MeasurementProfile,
    probe_info: ProbeInfo,
    gate_type: str = None,         # for CKG sub-typing
    sync_depth: int = None,        # for SYNC parameterization
) -> TemplateFamily:
    """Select template family. Returns TemplateFamily or raises
    SelectionError with what was tried and closest matches."""
```

**Inputs**: Classification result + arc electrical characteristics.
**Outputs**: `TemplateFamily` (contains template path, parameter schema,
init strategy).
**Depends on**: `classifier.py`, `families.py`.
**Replaces**: `core/template_rules.py` (688-rule JSON lookup) and
`core/template_map.py` (if-chain port).

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
class InitStrategy(Enum):
    NODESET_STANDARD = "nodeset"         # .nodeset for Q/QN (16 lines, verified in all 63 shipped MPW templates)
    NODESET_EXTENDED = "nodeset_extended" # .nodeset with additional internal latch/bank state (PREDICTED, not verified -- Task E pending)
    IC_RETENTION = "ic_retention"         # .ic for retention mode entry/exit (PREDICTED, not verified -- Task E pending)
    TEMPLATE_EMBEDDED = "template_embedded" # Init is fully embedded in the template file; no runtime dispatch needed. Dominant case: 100% of shipped MPW templates use this -- .nodeset block is part of the template, not generated by the engine

def get_init_strategy(cell_class: CellClass, arc_type: str) -> InitStrategy:
    """Determine initialization approach."""
```

**Inputs**: Cell class + arc type.
**Outputs**: `InitStrategy` enum.
**Depends on**: `classifier.py`.
**Replaces**: The implicit init logic embedded in each SPICE template
(made explicit as a dispatcher).

> **Verification status** (from Task D template fingerprinting):
> All 63 shipped MPW templates embed `.nodeset` (16 lines) directly in the
> template file. The Python deck-generation code (`spiceDeckMaker/funcs.py`)
> does NOT generate `.ic` or `.nodeset` statements -- it only does `$VAR`
> substitution and pin biasing. This means init is a **template-level
> property**, not a runtime decision. The `TEMPLATE_EMBEDDED` strategy
> covers the dominant case. The `NODESET_EXTENDED` and `IC_RETENTION`
> variants are predictions for hold/non_seq templates pending Task E
> verification.

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
**Depends on**: Filesystem (template library).
**Replaces**: `config/template_registry.yaml` (for v2 path).

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
(B_audit_d3_d5.md) are left unfixed in the JSON to preserve v1
behavioral parity. The fix is applied only in v2's classifier.

---

## 4. MVP Scope

### Arc types in scope

| Arc type | In MVP? | Rationale |
|----------|---------|-----------|
| **hold** | Yes | Largest rule set (255 rules), exercises all 8 discrimination categories, most complex templates |
| **setup** | Yes | Fully trivial (10 rules, all signature-determined) -- validates that trivial path works |
| **min_pulse_width** | Yes | 63 shipped templates available for structural validation (Task D), exercises SYNC scaling |
| removal | No | Uses hold templates (shares directory), defer to Phase 2B |
| nochange_* | No | 130 templates, unique waveform model, needs its own validator -- Phase 2C |
| non_seq_hold/setup | No | Async control + retention, most complex init -- Phase 2C |
| delay | No | Only 2 rules, minimal value -- Phase 2D |

**Why hold first**: It is the hardest. 255 rules, 204 unique templates, all
8 discrimination categories represented. If the architecture works for hold,
it works for everything else. Starting with the easiest (delay, setup) would
defer architectural problems.

### Cell families in scope (MVP)

| # | Cell family | Topology class | Init strategy (verified?) | Measurement | Why |
|---|-------------|---------------|--------------------------|-------------|-----|
| 1 | Standard FF (DFFQ1, SDFQ1) | COMMON | TEMPLATE_EMBEDDED for MPW; PREDICTED nodeset for hold (Task E pending) | pushout | Baseline: simplest hold arc |
| 2 | Latch (LHQD1) | LATCH | PREDICTED nodeset_extended for hold (Task E pending) | glitch (maxq/minq) | Tests glitch polarity dispatch |
| 3 | Multi-bank (MB*SRLSDF*) | MB | PREDICTED nodeset_extended for hold (Task E pending) | glitch | Tests multi-input expansion (AO22) |
| 4 | Synchronizer (SYNC2-6) | SYNC | TEMPLATE_EMBEDDED for MPW (verified: 16 .nodeset lines) | pushout | Tests depth parameterization + waveform scaling |
| 5 | Clock gater (CKGAN2*, CKGND2*) | CKG | TEMPLATE_EMBEDDED for MPW (verified: 16 .nodeset lines) | pushout | Tests gate-type sub-classification (AND vs NAND) |

These 5 families exercise:
- **1 of 4 init strategies verified**: TEMPLATE_EMBEDDED (all MPW templates).
  The other 3 strategies (NODESET_STANDARD, NODESET_EXTENDED, IC_RETENTION)
  are predictions for hold/non_seq templates pending Task E.
- Both measurement criteria (pushout + glitch)
- Output polarity dispatch (latch family)
- Depth parameterization (SYNC)
- Multi-input expansion (MB/AO22)
- Gate-type sub-classification (CKG)

> **Risk note**: MVP does NOT exercise IC_RETENTION (retention cells are
> out of scope). This means the retention init path ships untested until
> Phase 2C. This is acceptable because (a) retention cells are a small
> fraction of the total cell population, (b) Phase 2C is explicitly
> scoped to cover them, and (c) the fallback-to-v1 mechanism ensures
> retention cells still produce correct decks during MVP via the legacy
> engine. If earlier coverage is desired, add a 6th MVP family:
> `*RETN* + *RSSDF*` (retention flop, IC_RETENTION init, glitch
> measurement, non_seq_hold arcs).

### Explicit out-of-scope for MVP

- Retention cells (RETN*): complex init, deferred to Phase 2C
- DET/DRDF/DIV4: specialized topologies, low volume
- SLH/ESLH: scan-specific, deferred
- basemeg (WWL*): memory cells, specialized
- nochange waveform model: different from hold/setup
- Spectre backend: HSPICE only in Phase 2
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
| 18 | *RETN* + *RSSDF* | Retention flop | ic_retention | glitch | non_seq_hold |
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
**Mitigation**: (1) Document known v1 bugs in `ACCEPTED_DIFFS.md`.
(2) Phase 2B explicitly addresses the 37 `unknown` rules. (3) For
the OR-alternative issue, fix in `template_rules.json` is a data
change, not an architecture change.

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

---

## 7. Open Questions for Yuxuan

### Q1: MVP arc type scope [AWAITING DECISION]

**Options**:
- (A) hold + setup + mpw (recommended above): exercises the most
  architecture, but mpw templates are already validated and may feel like
  wasted effort
- (B) hold + setup only: smaller scope, faster to ship, but defers mpw
  which is the only structurally validated family
- (C) hold only: minimum viable, but setup's triviality is a good sanity
  check

**Recommendation**: (A). The mpw templates are already on disk and validated
(Task D), so they are nearly free to include. Setup is trivial and validates
the "easy path." Hold exercises the hard path.

### Q2: FMC simulation submission integration [AWAITING DECISION]

Phase 2 generates SPICE decks. The next step is submitting them to FMC for
simulation. Should Phase 2 include:
- (A) Deck generation only (current scope)
- (B) Deck generation + FMC job submission (adds `core/fmc_submit.py`)
- (C) Deck generation + FMC submission + result collection

**Recommendation**: (A). FMC integration is orthogonal to the principle
engine and can be added later without architectural changes. Yuxuan has a
separate FMC estimator project; coordinate timing.

### Q3: GUI invasiveness [AWAITING DECISION]

Phase 2 adds an engine toggle to the GUI. Beyond that:
- (A) Minimal: just the toggle, no other GUI changes
- (B) Moderate: add a "Principle Engine" tab showing classification results,
  selected family, parameter bindings (useful for debugging)
- (C) Full: redesign batch mode to show v1/v2 comparison inline

**Recommendation**: (B). The debug visibility is essential during Phase 2
development. It does not require a GUI redesign -- just a collapsible panel
under the existing arc detail view.

### Q4: Template library format [AWAITING DECISION]

The reduced template library (~50-70 families) can be stored as:
- (A) Actual `.sp` files in `templates/v2/` (easy to read, hard to
  parameterize pipeline depth)
- (B) YAML/JSON family descriptors + `.sp` base templates (more flexible,
  requires a template composition step)
- (C) Python-embedded template strings (most flexible, hardest to review)

**Recommendation**: (A) for MVP. Real `.sp` files are diffable against MCQC
originals. Parameterization that requires structural changes (e.g., SYNC
depth) can use a small set of base templates with a Python post-processor.

### Q5: Should the 37 `unknown` arc_type rules be fixed before Phase 2? [AWAITING DECISION]

B_audit_d3_d5.md diagnosed the issue and proposed a fix. Options:
- (A) Fix in `template_rules.json` now (Patch 5 on foundation-closure)
- (B) Fix only in v2 classifier (leave v1 data untouched)
- (C) Fix both: JSON for v1, classifier for v2

**Recommendation**: (C). The JSON fix is low-risk (data change, not logic)
and immediately improves v1's 5.4% false-negative rate. The classifier fix
is needed regardless for v2.

> **Updated by spec revision**: Fix 4 (KNOWN_V1_BUGS in S5) provides a
> mechanism to handle the 37 rules regardless of whether the JSON is fixed.
> If option (B) is chosen, the 37 affected cell/arc combinations are added
> to KNOWN_V1_BUGS and v2 produces correct output while v1 continues to
> silently skip them. Option (C) remains preferred because it also fixes
> v1, but (B) is now viable without regression breakage.

### Q6: Task E template samples timeline [AWAITING INPUT]

The 10 template samples from Task E are needed before Phase 2 code starts
(they validate whether topology sub-types share structure). When can you
provide these?

---

## 8. Estimated Phase 2 Phasing

### Phase 2A: Classifier + Selector + Regression Harness [M]

**Delivers**:
- `core/principle_engine/classifier.py` with 15 topology classes
- `core/principle_engine/selector.py` with family lookup
- `core/principle_engine/families.py` with initial family registry
- `tests/test_v1_v2_parity.py` regression harness (runs but expects failures
  for unimplemented families)
- `--engine principle` flag (CLI) that invokes classifier and reports
  classification result without generating decks

**Acceptance**: Classifier correctly labels all 20 regression cells.
Selector picks correct family for hold/setup/mpw arcs on the 5 MVP
cell families. No deck generation yet.

**Complexity**: M (medium). The classifier is the novel piece; selector
and families are structured lookups.

**Sequencing**: Must be first. Everything depends on correct classification.

> **BLOCKER**: Phase 2A cannot begin until Task E template samples are
> received and analyzed (see SS1.X). The classifier's topology class
> definitions depend on knowing whether topology sub-types have
> structurally different templates. Without Task E data, the classifier
> may create distinctions that don't exist or merge classes that should
> be separate.

### Phase 2B: Parameter Binder + Deck Generation for Hold [L]

**Delivers**:
- `core/principle_engine/param_binder.py`
- `core/principle_engine/init_strategy.py`
- `core/principle_engine/measurement.py`
- `core/principle_engine/engine.py` (full pipeline)
- Integration with `core/deck_builder.py` for `$VAR` substitution
- Hold arc decks byte-equal to v1 for the 5 MVP cell families
- Fix for the 37 `unknown` arc_type rules (if Q5 decision is (C))

**Acceptance**: `--engine principle --diff` reports `BYTE_EQUAL` for all
hold arcs in the 5-family MVP set across 3 corners. Fallback-to-v1 works
for cells outside MVP.

**Complexity**: L (large). Parameter binding is the most fiddly part --
matching MCQC's exact formatting, unit suffixes, cascade logic, and
dont-touch pin handling.

**Sequencing**: After 2A. Requires correct classification.

### Phase 2C: Remaining Arc Types + Retention + Nochange [L]

**Delivers**:
- Setup arc support (different timing semantics from hold, though
  structurally simpler)
- MPW arc support (63 shipped templates validated, but waveform model
  `stdvs_mpw_*` is distinct from hold's `stdvs_rise/fall`)
- Removal/recovery arcs (share hold template directory but have distinct
  measurement semantics)
- Non-seq hold/setup (async control pins CD/SDN, multi-phase stimulus,
  introduces the async-pin biasing path not exercised in 2B)
- Nochange arcs (130 templates, yet another waveform model distinct from
  both hold and MPW, embeds both hold+setup sub-arcs in filenames)
- Retention cell support (RETN*, introduces IC_RETENTION init strategy
  not present in 2B -- first time this init path is exercised)
- Expanded regression suite: 20 cells x all arc types
- `--diff` mode (CLI and GUI)

**Acceptance**: `BYTE_EQUAL` for all 20 regression cells across all arc
types. Fallback rate < 5% on a broader cell population test.

**Complexity**: L (large). Justification for upgrade from original M:
1. **Three distinct waveform models**: hold (`stdvs_rise/fall`), MPW
   (`stdvs_mpw_*`), nochange (TBD -- not yet characterized). Each may
   require different parameterization logic.
2. **IC_RETENTION init strategy**: first implementation of this path,
   previously untested and unverified (Task E pending).
3. **Nochange dual-arc embedding**: nochange templates encode both
   `hold` and `setup` sub-arcs in the filename (Task C SS2), requiring
   a mapping layer not needed for other arc types.
4. **Async pin biasing**: non_seq_hold/setup introduces CD/SDN pin
   stimulus patterns that differ from clock-data timing in hold/setup.
5. **130 nochange templates alone**: more templates than hold (204) is
   less, but each has unique pin/direction/threshold combinations.
6. **Retention state machine**: RETN cells have the deepest template
   nesting (13 tokens, Task C SS5) and the most complex per-cell
   override cascade.

**Sequencing**: After 2B. Cannot parallelize with 2D because the `--diff`
mode (delivered here) is needed for 2D's GUI integration.

### Phase 2D: GUI Integration + Documentation [S]

**Delivers**:
- GUI engine toggle
- Principle engine debug panel (classification, selected family, parameters)
- Updated `docs/design.md` with v2 architecture section
- Updated `CLAUDE.md` with v2 commands and conventions
- `docs/phase2/changelog.md` summarizing what shipped

**Acceptance**: GUI works with both engines. Documentation is complete.

**Complexity**: S (small). No new engine logic -- GUI integration and docs.

**Sequencing**: After 2C (or can start in parallel for the GUI toggle).

### Summary

| Sub-phase | Delivers | Size | Depends on |
|-----------|----------|------|------------|
| 2A | Classifier + selector + regression harness | M | Task E results (BLOCKER) |
| 2B | Param binder + hold deck generation | L | 2A |
| 2C | Remaining arcs + retention + nochange | L | 2B |
| 2D | GUI integration + documentation | S | 2C (--diff mode needed) |
