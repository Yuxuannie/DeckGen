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
2. **Outcome semantics = honest generation-only.** An arc's outcome is its
   *deck-generation* result. Terminal states in our scope: `generated` (deck
   emitted, ready to submit), `generation_error:<category>`, `skipped:<reason>`.
   The state machine advances generated arcs to `submitted` (deck written + bsub
   emitted) -- that is the production boundary. No `passed`/`failed` sim states.
3. **Demo 1 scope = top-3 MVP.** No-drop ledger (#1) + failed-arc triage card (#4)
   + live dashboard (#3). Resume/rerun-failed (#2) and run-to-run diff (#5) are
   deferred to a follow-up.
4. **Arc universe = template.tcl enumeration.** The per-cell arc list for the
   coverage denominator comes from each corner's `template.tcl` (the production
   source of truth), parsed by the existing `core/parsers/template_tcl.py`.
5. **Scoped runs, not forced whole-library.** Production operators select what to
   run -- a subset of cells, arc types, and corners -- rather than always
   characterizing the entire library. The run takes selection filters; the
   coverage universe (the no-drop denominator) is the **selected** scope, not the
   full manifest. Default (no filters) = whole library, but that is a choice, not
   the only mode. See section 5b.

## 3. Architecture -- one shared core, two thin front-ends

```
core/coverage.py      B4: outcome rows + manifest universe -> coverage matrix,
                      no-drop assertion, NDJSON + HTML
core/orchestrate.py   Phase C run loop: discover -> generate -> submit(mock) ->
                      coverage; owns the closed state machine + NDJSON ledger
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

Every (cell, arc, corner) tuple in the manifest universe reaches exactly one
terminal state. The three terminal buckets partition the universe:

| State | Set when |
|-------|----------|
| `generated` -> `submitted` | `assemble_*` returned `status == "OK"`; deck written; bsub script emitted. `submitted` is the farm boundary. |
| `generation_error:<category>` | `assemble_*` returned `status == "ERROR"`; category derived from the error (see 4.1). |
| `skipped:<reason>` | intentionally not generated (e.g. `mpw_skip`, arc absent from manifest cell's supported set). |

**No-drop invariant (machine-checkable):**

```
expected == submitted + generation_error + skipped
```

where `expected = |selected-cells x selected-arc-types(from template.tcl) x
selected-corners|` -- i.e. the denominator is the **selected scope** (section 5b),
not necessarily the whole manifest. If the equation does not balance, the run is
flagged INCOMPLETE and the report says so loudly. This assertion *is* demo item #1.
No-drop is a promise about the scope the operator asked for: every selected arc is
accounted for.

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
    """rows: list[OutcomeRow dict]; universe: list[(cell, arc_type, corner) tuple].
    Returns CoverageReport dict:
      { "summary": {expected, submitted, generation_error, skipped, balanced: bool},
        "by_category": {category: count},
        "by_corner": {corner: {submitted, error, skipped}},
        "matrix": {(cell, arc_type): {corner: state_str}},
        "triage": [ {arc_id, cell, arc_type, corner, category, reason,
                     netlist_path, deck_path} for each generation_error ],
        "unaccounted": [ (cell, arc_type, corner) tuples in universe with no row ] }
    """

def coverage_ndjson(report, path):   # one line per (cell, arc_type, corner)
def coverage_html(report, path):     # static HTML: QA block + matrix + triage
```

`OutcomeRow` dict keys (produced by orchestrate, consumed here):
`arc_id, cell, arc_type, corner, state, category, reason, netlist_path, deck_path`.

`balanced = (expected == submitted + generation_error + skipped)` AND
`unaccounted == []`. The HTML/CLI headline renders green iff `balanced`.

## 5b. Run scoping / selection

An operator chooses what a run covers; the whole library is the default, not a
mandate. Selection is a `Scope` dict passed into `discover`:

```python
Scope = {
    "cells":     None | [glob, ...],   # fnmatch globs against manifest cell names
    "arc_types": None | [str, ...],    # subset of {delay, slew, hold, mpw, setup, ...}
    "corners":   None | [str, ...],    # subset of manifest corner keys
    "arcs":      None | [arc_id, ...], # explicit cell_arc_pt ids -- most precise
}
```

- `None` on a field means "all" for that dimension. All-`None` == whole library.
- `cells`/`arc_types`/`corners` compose as an intersection filter over the
  template.tcl-enumerated universe.
- `arcs` (explicit ids) short-circuits enumeration: only those exact arcs, resolved
  against the manifest; an id naming a cell/corner absent from the collateral is
  reported as `skipped:not_in_collateral` (accounted, never silently dropped).
- A selection that matches **zero** arcs is an explicit error surfaced at the scope
  gate ("selection matched 0 arcs; check --cells/--arc-types/--corners"), not an
  empty successful run.

The coverage universe returned by `discover` is exactly the selected set, so the
no-drop invariant (section 4) holds against what the operator asked for.

## 6. core/orchestrate.py (Phase C)

The run loop. Pure with respect to the collateral inputs; writes only into the
run directory.

```python
def discover(manifest, template_tcl_by_corner, scope=None):
    """manifest (from tools/scan_collateral.build_manifest) x per-corner template.tcl,
    filtered by scope (section 5b; None == whole library) -> universe:
    list[(cell, arc_type, corner)]. Arc list per cell from template.tcl enumeration.
    Never raises; unreadable template.tcl -> that corner's arcs recorded as
    skipped:template_tcl_unreadable (still accounted). Raises SelectionEmpty only when
    a non-None scope matches zero arcs (surfaced at the scope gate, not silent)."""

def generate_one(cell, arc_type, corner, manifest, netlist_src, grammar):
    """Build arc_info (via core/arc_info_builder), dispatch to assemble_combinational
    or assemble_sequential by arc family, write deck if OK. Returns OutcomeRow."""

def run(collateral_dir, node, lib_type, out_dir, scope=None, dry_run=False,
        progress=None):
    """Full loop: build_manifest -> discover(scope) -> generate each -> lsf.emit_arrays
    for generated -> build_coverage -> write ledger.ndjson + coverage.{ndjson,html}.
    scope (section 5b; None == whole library) selects which cells/arc-types/corners/arcs
    run. `progress` is an optional callback(event_dict) for live dashboards (CLI table /
    GUI poller). dry_run stops after discover and returns the plan (job count, matrix,
    walltime estimate) without generating. Returns RunResult dict."""
```

**Ledger** (`<out_dir>/ledger.ndjson`): append-only, one JSON line per outcome as
it completes, written atomically (temp+rename of the whole file per flush, or
append-line). This is the durable record the coverage report is built from and the
substrate a future `--rerun-failed` (deferred) will read.

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
    [--cells 'DFF*,*MUX*'] [--arc-types hold,mpw] [--corners a,b,c] \
    [--arcs-file arcs.txt] [--out run_dir] [--dry-run] [--slot-limit 50]
```

**Selection (section 5b):** `--cells` (comma-separated fnmatch globs), `--arc-types`
(comma-separated), `--corners` (comma-separated), or `--arcs-file` (one explicit
cell_arc_pt id per line, most precise). Any omitted dimension defaults to "all";
omitting all four runs the whole library. `--arcs-file` short-circuits enumeration.
A selection matching zero arcs exits non-zero at the scope gate with a message
naming the filters -- never a silent empty run.

- `--dry-run` prints the scope gate: **selected** job count, cell x corner matrix,
  walltime estimate (heuristic: pin-count bucket x corner difficulty); exits 0
  without generating. This is where an operator confirms scope before committing.
- A live progress line/table via the `progress` callback: discovered N, generated
  G, error E, skipped S, arcs/sec, ETA.
- On completion prints the **no-drop headline**
  (`<expected> arcs in -> <accounted> accounted for (G submitted / E error / S skip)`),
  green if balanced, a loud INCOMPLETE banner otherwise, then the run-dir path.
- Exit code 0 iff balanced.

Config paths relative to script location. Stdlib + core only.

## 9. Front-end 2 -- GUI (Run / Report tab in gui.py)

A new tab reusing the existing async task + polling model (`/api/generate_v2` +
`/api/generate_status` pattern with `task_id`). Pure functions form the testable
seam:

The tab opens on a **scope picker** (section 5b): multiselect cells / arc-types /
corners (populated from the manifest, reusing the existing `_api_list_cells` /
`_api_list_corners` seam) plus a dry-run "preview scope" showing the selected job
count and matrix before the operator commits. `payload` carries the chosen `scope`.

```python
def _api_run_start(payload):   # payload carries {collateral, node, lib_type, scope};
                               # kick off core.orchestrate.run in a worker thread,
                               # return {task_id}
def _api_run_status(task_id):  # live ledger snapshot: counts, rate, ETA, recent rows
def _api_run_coverage(task_id) # final CoverageReport dict for matrix + triage render
```

Rendered views (Demo 1 top-3):
- **Live dashboard** (#3): animated counts (discovered/generated/error/skipped),
  arcs/sec, ETA; then the submission summary (K array jobs written; the actual
  `bsub` command shown) with the honest "(team runs HSPICE)" boundary.
- **No-drop ledger** (#1): the balance headline, green when
  `expected == submitted + error + skipped`.
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
- **core/orchestrate.py**: run over the fixture collateral -> deterministic outcome
  rows, ledger NDJSON written, no-drop balances; a cell that fails to generate lands
  in a named `generation_error` category, not dropped; `dry_run` returns the plan
  without writing decks. **Scope tests**: `discover` with a cells/arc-types/corners
  filter returns exactly the intersection; an explicit `arcs` list short-circuits
  enumeration; a zero-match scope raises `SelectionEmpty`; no-drop balances against
  the *selected* denominator (not the full manifest).
- **deckgen_run.py**: subprocess smoke over fixtures -- run-dir artifacts exist,
  no-drop headline in stdout, exit 0.
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
