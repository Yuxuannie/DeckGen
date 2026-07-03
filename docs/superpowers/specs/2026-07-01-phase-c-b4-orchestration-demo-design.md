# Phase C + B4 + Demo 1 -- Orchestration, Coverage, and Two Front-Ends

**Date:** 2026-07-01
**Status:** Design approved (pending written-spec review)
**Depends on:** B1 (combinational emitter), B2 (sequential classification), B3
(sequential emitter), Phase A (measurement grammar). Consumes `assemble_combinational`
and `assemble_sequential` from `core/deck_assemble.py`.
**Design input:** `.superpowers/sdd/production-flow-research.md` (8 sections, LSF /
coverage / no-drop research).

## 1. Goal

Turn the per-arc deck emitters (B1/B3) into a **production-shaped, lights-out
library run**: one command discovers every (cell, arc, corner) from the collateral
manifest, generates a deck or a reasoned refusal for each, submits the generated
decks as real LSF job-array scripts, and emits a **no-silent-drop coverage report**.

Phase C completion == Demo 1 completion. The run must *align with production MCQC
usage* -- the artifacts an engineer would actually submit and read -- while staying
**simulator-free**: no real HSPICE, no real LSF cluster. The state machine stops
honestly at `submitted` with a clear "(team runs HSPICE)" boundary; we never
fabricate sim pass/fail data.

Deliver **two front-ends over one shared core**: a CLI (`deckgen_run`) and a GUI
Run/Report tab.

## 2. Locked design decisions

These were decided during brainstorming and are binding:

1. **Mock LSF fidelity = production-shaped.** `core/lsf.py` emits the *real* `bsub`
   job-array submit scripts the team would run (`bsub -J "deckgen_<corner>[1-N]%P"
   -W <runlimit> -o .../%I.out`), plus an index->arc manifest the array task reads
   from `$LSB_JOBINDEX`. A local mock `bjobs` snapshot renders the monitor view
   without inventing completions.
2. **Outcome semantics = honest generation-only, with an operator confirm gate.**
   An arc's outcome is its *deck-generation* result. Terminal states in our scope:
   `generated` (deck emitted, resting -- awaiting operator confirm),
   `generation_error:<category>`, `skipped:<reason>`. Generation and submission are
   **two operator-gated phases**: the run generates all decks and stops; the
   operator reviews the generation coverage (no-drop ledger + triage) and explicitly
   confirms; only then does the run advance `generated -> submitted` (bsub scripts
   emitted). Deck-gen never flows straight into submission. `submitted` is the farm
   boundary. No `passed`/`failed` sim states.
3. **Demo 1 scope = top-3 MVP.** No-drop ledger (#1) + failed-arc triage card (#4)
   + live dashboard (#3). Resume/rerun-failed (#2) and run-to-run diff (#5) are
   deferred to a follow-up.
4. **Arc universe = template.tcl enumeration.** The per-cell arc list for the
   coverage denominator comes from each corner's `template.tcl` (the production
   source of truth), parsed by the existing `core/parsers/template_tcl.py`.
5. **Scoped runs matching production QC granularity.** Production QC does not
   characterize the entire library, and it does not hand-pick arc-types or
   individual arcs -- that is the wrong grain. Operators select **cells**, a
   configurable **first-N-arcs-per-cell** count, and **table points** (LUT `i1/i2`
   positions, whose meaningful locations differ by arc type), across selected
   **corners**. The coverage universe (the no-drop denominator) is exactly this
   selected scope. Default (no filters) = whole library at all table points, but
   that is a choice, not the only mode. See section 5b.

## 3. Architecture -- one shared core, two thin front-ends

```
core/coverage.py      B4: outcome rows + manifest universe -> coverage matrix,
                      no-drop assertion, NDJSON + HTML
core/orchestrate.py   Phase C run loop: discover -> generate -> [operator confirm]
                      -> submit(mock) -> coverage; closed state machine + NDJSON ledger
core/lsf.py           production-shaped mock LSF: emit real bsub array scripts +
                      index->arc manifest; render a mock bjobs snapshot
deckgen_run.py        CLI front-end: `deckgen_run --collateral <dir> ...` lights-out
gui.py (+ gui view)   GUI front-end: a "Run / Report" tab (live dashboard + triage
                      cards + coverage matrix) over async _api_run_* functions
```

Rules: nothing under `core/` imports a front-end. Both front-ends call the same
`core/` units. Front-ends are presentation only -- all logic, state, and the no-drop
guarantee live in `core/`. This mirrors the existing pure-core + thin-`_api_*` seam
the GUI already uses (`core/report.py` <- `gui.py` `/api/*`).

## 4. The closed state machine (no silent drops)

Every selected work item -- a `(cell, arc, table_point i1/i2, corner)` tuple (one
item == one deck == one HSPICE job) -- reaches exactly one terminal state. The
generation phase partitions the universe into three buckets; a fourth transition
(`generated -> submitted`) happens only after the operator confirm gate.

| State | Set when |
|-------|----------|
| `generated` | `assemble_*` returned `status == "OK"`; deck written. **Resting state** -- awaiting operator confirm. |
| `submitted` | operator confirmed; bsub array script emitted for this item's corner. The farm boundary. |
| `generation_error:<category>` | `assemble_*` returned `status == "ERROR"`; category derived from the error (see 4.1). |
| `skipped:<reason>` | intentionally not generated (e.g. `mpw_skip`, arc absent from the cell's supported set). |

**No-drop invariant (machine-checkable), enforced at each phase:**

```
generation phase:  expected == generated + generation_error + skipped
after submit:      generated == submitted            (every confirmed deck submitted)
```

where `expected = |selected work items|` = the selected (cell x first-N-arcs x
table-points x corner) universe (section 5b), not necessarily the whole manifest.
If either equation does not balance, the run is flagged INCOMPLETE and the report
says so loudly. This assertion *is* demo item #1. No-drop is a promise about the
scope the operator asked for: every selected item is accounted for.

### 4.1 generation_error categories

Derived by keyword-matching the `error` string returned by `assemble_*`
(never by raising). First-cut categories:

| Category | Trigger (substring in error, case-insensitive) |
|----------|-----------------------------------------------|
| `combinational_cell` | "combinational" |
| `latch_unsupported` | "latch" |
| `p1_unproven` | "p1 not proven" / "p1 could not be proven" |
| `out_of_corpus` | "SeqScope" / "beyond depth" |
| `parse_fail` | "parse" / "no .subckt" / "port order" |
| `no_grammar` | "grammar" |
| `unsupported_arc` | fallback for any other ERROR (never dropped) |

A category never seen before still lands in `unsupported_arc` with the full
reason preserved -- unknown != dropped.

## 5. core/coverage.py (B4)

Pure functions; no I/O side effects beyond the two explicit emit helpers.

```python
def build_coverage(rows, universe):
    """rows: list[OutcomeRow dict]; universe: list[(cell, arc_type, i1, i2, corner) tuple]
    (one tuple == one work item == one deck). Returns CoverageReport dict:
      { "summary": {expected, generated, submitted, generation_error, skipped,
                    balanced: bool},
        "by_category": {category: count},
        "by_corner": {corner: {generated, submitted, error, skipped}},
        "matrix": {(cell, arc_type, i1, i2): {corner: state_str}},
        "triage": [ {arc_id, cell, arc_type, i1, i2, corner, category, reason,
                     netlist_path, deck_path} for each generation_error ],
        "unaccounted": [ (cell, arc_type, i1, i2, corner) in universe with no row ] }
    """

def coverage_ndjson(report, path):   # one line per (cell, arc_type, i1, i2, corner)
def coverage_html(report, path):     # static HTML: QA block + matrix + triage
```

`OutcomeRow` dict keys (produced by orchestrate, consumed here):
`arc_id, cell, arc_type, i1, i2, corner, state, category, reason, netlist_path,
deck_path`. `state` is one of `generated`/`submitted`/`generation_error`/`skipped`;
`submitted` appears only after the operator confirm gate.

`balanced` = generation-phase invariant holds
(`expected == generated_or_submitted + generation_error + skipped`, where a
`submitted` row also counts as generated for this sum) AND `unaccounted == []`. The
HTML/CLI headline renders green iff `balanced`.

## 5b. Run scoping / selection

The selection knobs match how production QC actually samples a library: pick
cells, cap how many arcs per cell, pick table points, pick corners. Operators do
**not** enumerate arc-types or individual arc ids. Selection is a `Scope` dict
passed into `discover`:

```python
Scope = {
    "cells":         None | [glob, ...],   # fnmatch globs against manifest cell names
    "arcs_per_cell": None | int,           # run only the first N arcs of each cell
                                           #   (template.tcl enumeration order); None = all
    "table_points":  None | int | [(i1, i2), ...],
                                           # None      = every LUT point of each arc
                                           # int N     = first N points, row-major over the
                                           #             arc's index_1 x index_2 grid
                                           # [(i1,i2)] = explicit 1-based LUT coordinates,
                                           #             clamped per-arc (positions differ
                                           #             by arc type -- an out-of-range point
                                           #             for a given arc is skipped:no_such_point)
    "corners":       None | [str, ...],    # subset of manifest corner keys
}
```

- `None` on a field means "all" for that dimension. All-`None` == whole library at
  every table point.
- The four knobs compose as an intersection filter over the template.tcl-enumerated
  universe: for each selected cell, take its first `arcs_per_cell` arcs, expand each
  to its selected `table_points`, cross with selected `corners`.
- `arcs_per_cell` and `table_points` are the QC "spot-check" knobs -- e.g.
  `arcs_per_cell=3, table_points=[(1,1)]` runs the first three arcs of each selected
  cell at the corner LUT origin. The number is the operator's to set.
- An explicit `table_points` coordinate that a given arc's LUT does not contain is
  recorded `skipped:no_such_point` (accounted, never silently dropped) -- this is how
  "positions differ by arc type" stays honest.
- A selection that matches **zero** work items is an explicit error surfaced at the
  scope gate ("selection matched 0 items; check --cells/--arcs-per-cell/--table-points/
  --corners"), not an empty successful run.

The coverage universe returned by `discover` is exactly the selected set of
`(cell, arc, table_point, corner)` items, so the no-drop invariant (section 4)
holds against what the operator asked for.

## 6. core/orchestrate.py (Phase C)

The run loop. Pure with respect to the collateral inputs; writes only into the
run directory.

```python
def discover(manifest, template_tcl_by_corner, scope=None):
    """manifest (from tools/scan_collateral.build_manifest) x per-corner template.tcl,
    filtered by scope (section 5b; None == whole library) -> universe:
    list[(cell, arc_type, i1, i2, corner)] work items (one per deck). Per-cell arcs
    from template.tcl enumeration; first arcs_per_cell of them; each expanded to the
    selected table_points. Never raises for data problems; unreadable template.tcl ->
    that corner's items recorded skipped:template_tcl_unreadable (still accounted);
    an explicit table point absent from an arc's LUT -> skipped:no_such_point. Raises
    SelectionEmpty only when a non-None scope matches zero items (surfaced at the
    scope gate, not silent)."""

def generate_one(cell, arc_type, i1, i2, corner, manifest, netlist_src, grammar):
    """Build arc_info (via core/arc_info_builder) for this table point, dispatch to
    assemble_combinational or assemble_sequential by arc family, write deck if OK.
    Returns OutcomeRow with state 'generated' or 'generation_error'."""

def generate(collateral_dir, node, lib_type, out_dir, scope=None, progress=None):
    """Phase 1: build_manifest -> discover(scope) -> generate_one each -> write
    ledger.ndjson + coverage.{ndjson,html} for the GENERATION phase. Stops at the
    resting state -- writes NO bsub, submits nothing. Returns RunResult dict
    (universe, rows, coverage, run_dir). This is the pre-confirm artifact the
    operator reviews."""

def submit(run_dir, slot_limit=50, runlimit="00:20", progress=None):
    """Phase 2, called only after operator confirm: read the generated rows from
    run_dir's ledger, lsf.emit_arrays for them, advance each 'generated' row to
    'submitted', rewrite ledger + coverage. Returns the updated RunResult. Refuses
    (named error, no partial writes) if there are no generated rows to submit."""

def run(collateral_dir, node, lib_type, out_dir, scope=None, dry_run=False,
        confirm=None, progress=None):
    """Convenience orchestration for the CLI: generate(...) then, if not dry_run,
    call confirm(RunResult) -> bool at the gate; submit(...) only if it returns True.
    dry_run stops after discover and returns the plan (item count, matrix, walltime
    estimate) without generating. confirm=None means 'generate only, do not submit'
    (the safe default). Returns the final RunResult."""
```

The **generate / submit split is the operator confirm gate**: `generate` never
emits a bsub script, `submit` is a separate call that only runs after an explicit
human yes. `run` wires them for the CLI via the `confirm` callback; the GUI calls
`generate` and `submit` as two API steps (section 9).

**Ledger** (`<out_dir>/ledger.ndjson`): append-only, one JSON line per outcome as
it completes, written atomically (temp+rename of the whole file per flush, or
append-line). Rewritten in place when `submit` advances rows to `submitted`. This is
the durable record the coverage report is built from and the substrate a future
`--rerun-failed` (deferred) will read.

**Run directory layout** (aligns with MCQC per-corner tree, reuses `core/writer`
conventions where practical):

```
<out_dir>/
  run_config.json          echoed inputs (collateral, node, lib_type, corners, caps)
  ledger.ndjson            per-arc outcomes
  coverage.ndjson          B4 machine-readable
  coverage.html            B4 human-readable (QA block + matrix + triage)
  lsf/
    deckgen_<corner>.bsub       real job-array submit script
    index_<corner>.manifest     $LSB_JOBINDEX -> arc_id -> deck path
  decks/<lib_type>/<corner>/<arc_type>/<arc_id>/nominal_sim.sp
                          (arc_id ends in _<i1>_<i2> -- the table point)
```

## 7. core/lsf.py (production-shaped mock)

```python
def emit_arrays(generated_rows, out_dir, slot_limit=50, runlimit="00:20"):
    """For each corner with generated decks, write lsf/deckgen_<corner>.bsub and
    lsf/index_<corner>.manifest. The .bsub is a real, submittable LSF job-array
    script:
        #!/bin/bash
        #BSUB -J "deckgen_<corner>[1-N]%<slot_limit>"
        #BSUB -W <runlimit>
        #BSUB -o <out_dir>/lsf/logs/<corner>.%I.out
        ARC=$(sed -n "${LSB_JOBINDEX}p" index_<corner>.manifest)
        hspice ... "$ARC"
    Returns {corner: {"script": path, "manifest": path, "n_jobs": N}}."""

def bjobs_snapshot(arrays):
    """Mock bjobs output: all array elements PEND, labeled '(awaiting farm -- team
    runs HSPICE)'. Demonstrates the monitor loop shape; invents no DONE/EXIT."""
```

ASCII-only. The `.bsub` and `.manifest` are the genuine artifacts the team submits;
only the poller is mocked, and it is mocked *honestly* (PEND only).

## 8. Front-end 1 -- CLI (deckgen_run.py)

```
python3 deckgen_run.py --collateral <dir> --node N2P_v1.0 --lib_type test_lib \
    [--cells 'DFF*,*MUX*'] [--arcs-per-cell 3] [--table-points 1,1] \
    [--corners a,b,c] [--out run_dir] [--dry-run] [--yes] [--slot-limit 50]
```

**Selection (section 5b):** `--cells` (comma-separated fnmatch globs),
`--arcs-per-cell N` (first N arcs of each cell; omit = all), `--table-points`
(either an integer "first N points", or `;`-separated `i1,i2` coordinates e.g.
`1,1;2,3`; omit = all points), `--corners` (comma-separated; omit = all). Omitting
all knobs runs the whole library at every table point. A selection matching zero
items exits non-zero at the scope gate with a message naming the filters -- never a
silent empty run.

**Two operator gates:**
1. `--dry-run` prints the scope gate -- **selected** item count, cell x corner
   matrix, walltime estimate (heuristic: pin-count bucket x corner difficulty) --
   and exits 0 without generating. Where the operator confirms scope before
   committing cores.
2. **Confirm-before-submit gate:** a normal run generates all decks, prints the
   generation no-drop ledger + triage, then **prompts** `Submit <N> array jobs to
   LSF? [y/N]`. Only `y` triggers `submit`. `--yes` pre-confirms for non-interactive
   runs; without it and without a tty, the run stops at `generated` and prints
   "decks ready, not submitted (re-run with --yes or use the GUI Submit button)".
   Deck-gen never auto-submits.

- Live progress line/table via the `progress` callback: discovered N, generated G,
  error E, skipped S, items/sec, ETA.
- After generation, the **no-drop headline**
  (`<expected> items in -> <accounted> accounted for (G generated / E error / S skip)`),
  green if balanced, a loud INCOMPLETE banner otherwise. After submit (if confirmed),
  a submission summary (K array jobs, the actual `bsub` command, "(team runs HSPICE)").
- Exit code 0 iff balanced.

Config paths relative to script location. Stdlib + core only.

## 9. Front-end 2 -- GUI (Run / Report tab in gui.py)

A new tab reusing the existing async task + polling model (`/api/generate_v2` +
`/api/generate_status` pattern with `task_id`). Pure functions form the testable
seam:

The tab opens on a **scope picker** (section 5b): multiselect cells + corners
(populated from the manifest, reusing the existing `_api_list_cells` /
`_api_list_corners` seam), an **arcs-per-cell** number input, and a **table-points**
input (count or explicit `i1,i2` list), plus a "preview scope" (dry-run) showing
the selected item count and matrix before the operator commits. `payload` carries
the chosen `scope`. The GUI's **Submit** button is the operator confirm gate
(mirrors the CLI prompt).

```python
def _api_run_generate(payload):  # payload {collateral, node, lib_type, scope};
                                 # kick off core.orchestrate.generate in a worker
                                 # thread, return {task_id}. Generates only -- no bsub.
def _api_run_status(task_id):    # live ledger snapshot: counts, rate, ETA, recent rows
def _api_run_coverage(task_id):  # CoverageReport dict for matrix + triage render
def _api_run_submit(task_id):    # operator pressed Submit -> core.orchestrate.submit;
                                 # emits bsub arrays, advances rows to 'submitted'
```

Two-step flow: **Generate** (`_api_run_generate`) -> operator reviews the no-drop
ledger + triage -> **Submit** (`_api_run_submit`). Submission never happens without
the button; there is no auto-submit path.

Rendered views (Demo 1 top-3):
- **Live dashboard** (#3): animated counts (discovered/generated/error/skipped),
  items/sec, ETA; after Submit, the submission summary (K array jobs written; the
  actual `bsub` command shown) with the honest "(team runs HSPICE)" boundary.
- **No-drop ledger** (#1): the balance headline, green when
  `expected == generated + error + skipped`.
- **Triage cards** (#4): one card per `generation_error` -- arc_id, category,
  reason, absolute netlist + attempted-deck paths, copy button.

The tab is injected the same way engine tabs are (thin view module + splice), no
rewrite of gui.py's dispatch. GUI logic stays in `_api_*`; core does the work.

## 10. Build decomposition -- two phases, each its own plan

The "two versions" map cleanly onto two build phases. Each produces working,
independently testable software.

**Phase C-1 (CLI version)** = `core/coverage.py` + `core/orchestrate.py` +
`core/lsf.py` + `deckgen_run.py`. A complete lights-out CLI run over the in-repo
fixture collateral (`tests/fixtures/collateral/N2P_v1.0/test_lib`) producing the
ledger, coverage report, bsub scripts, and decks, with a live CLI table and the
no-drop headline. This is the early prototype to test.

**Phase C-2 (GUI version)** = the Run/Report tab + `_api_run_*` over the same core.

Each phase gets its own writing-plans plan and TDD build. C-1 first (core +
CLI), then C-2 (GUI over the proven core).

## 11. Testing

- **core/coverage.py**: pure-function tests on hand-built rows + universe --
  balanced-true and balanced-false cases; matrix shape; category counting; the
  `unaccounted` path; NDJSON round-trip; HTML contains the QA block + triage.
- **core/lsf.py**: assert emitted `.bsub` shape (job array header, `%slot`, `-W`,
  `$LSB_JOBINDEX` deref), index manifest maps N arcs, ASCII-only; `bjobs_snapshot`
  is PEND-only (never DONE/EXIT).
- **core/orchestrate.py**: `generate` over the fixture collateral -> deterministic
  outcome rows, ledger NDJSON written, no-drop balances; a cell that fails to
  generate lands in a named `generation_error` category, not dropped; `dry_run`
  returns the plan without writing decks. **Confirm-gate tests**: `generate` writes
  NO bsub (lsf/ empty, all rows `generated`); `submit` after `generate` advances
  rows to `submitted` and only then emits bsub; `submit` with no generated rows
  refuses (named error, no partial writes). **Scope tests**: `discover` with
  cells/corners filters returns exactly the intersection; `arcs_per_cell=N` keeps the
  first N arcs per cell; `table_points=int` keeps the first N LUT points and
  `table_points=[(i1,i2)]` keeps exactly those, with an out-of-range coordinate ->
  `skipped:no_such_point`; a zero-match scope raises `SelectionEmpty`; no-drop
  balances against the *selected* item denominator (not the full manifest).
- **deckgen_run.py**: subprocess smoke over fixtures -- `--dry-run` prints the scope
  gate and writes nothing; a generate-only run (no `--yes`, no tty) stops at
  `generated` with "not submitted" and writes no bsub; a `--yes` run produces the
  bsub scripts and the no-drop headline; exit 0 iff balanced.
- **gui _api_run_***: pure-function tests like the existing `test_gui_api.py`.

## 12. Constraints (binding, from CLAUDE.md)

- **ASCII-only** for `.py/.yaml/.sp/.json`; verify `grep -rPn '[\x80-\xff]'` empty.
- **Never fail silently / never drop arcs**: bad/unsupported arcs -> named error
  category in the ledger, never an exception, never a silent skip. The coverage
  assertion enforces this mechanically.
- **Never change a test assertion to make a test pass** without Yuxuan's approval.
- **Config paths relative to script location** -- never hardcode absolute paths.
- **Simulator-free**: no real HSPICE, no real LSF. Mock stops honestly at
  `submitted`.
- Stdlib + existing `core/` + `engine/` only; no new external deps.

## 13. Out of scope (deferred)

- Resume / `--rerun-failed` (#2), delta-by-hash, run-to-run diff (#5).
- Real HSPICE failure categories (`convergence`, `measure-NaN`, ...) -- those need
  a simulator; our categories are generation-only.
- Timing-value extraction / `.lib` assembly (a separate downstream tool).
- Retry/backoff policy, straggler reordering, core-hour budget alarms.
