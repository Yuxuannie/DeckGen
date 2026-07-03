# Stage-A Mounting: v2 Engine as an Audit Sidecar on the v1 Flow (Design)

**Status:** draft -- awaiting user review before writing-plans
**Branch:** feat/phase-2b-engine
**Scope:** `--verify` flag on deckgen.py; data contract v1 -> engine; P3 implementation
in `engine/stages/stage5_verify.py`; verdict sidecar JSON; fixture tests
**Out of scope (FIXED):** no v1 refactoring, no extraction of engine stages into a
separate package, no changes to S0-S2, no new arc types, no GUI exposure of the flag,
no batch CSV aggregator (columns defined here; runner is a separate task)
**Constraints (FIXED):** v1 deck output byte-identical with and without `--verify`;
engine failure never breaks v1 generation; stdlib only (zero new dependencies)

---

## 1. Purpose

v1 (core/) is the production deck generator with MCQC parity. v2 (engine/) derives
sensitization and initialization from transistor topology and emits P1/P2/P3 evidence.
This spec mounts v2 onto v1 as a read-only audit layer: when `--verify` is given, every
arc v1 resolves is ALSO run through `engine.pipeline.run_pipeline_src(...)`, and a
verdict sidecar JSON is written next to the generated deck. v1's outputs are untouched;
the sidecar is pure addition.

This is an attachment point, not a framework: one new module (`core/verify_sidecar.py`),
one new engine function (`p3_property`), one flag, threaded through two call sites.

---

## 2. Architecture

```
deckgen.py --verify
  |
  |-- single-arc mode (_run_single)          batch mode (_run_batch -> core/batch.py)
  |        |                                        |
  |   write deck (UNCHANGED)                  execute_jobs._run_one: write deck (UNCHANGED)
  |        |                                        |
  |        +----------------+----------------------+
  |                         v
  |          core/verify_sidecar.py  (NEW, the only v1-side addition)
  |             build_record(arc_info, job)     -> engine `record` dict
  |             read netlist text               -> `src`
  |             extract_meas_block(deck_lines)  -> `meas`
  |             model include reference         -> `model`
  |             run_pipeline_src(...)           [try/except around EVERYTHING]
  |             build MeasContext from v1 deck lines + arc_info
  |             p3_property(ctx, init, sim=None)   (engine/stages/stage5_verify.py)
  |             write {deck_dir}/verify.json
  v
v1 deck bytes: IDENTICAL (verified by regression test 8a)
```

File changes:

| File | Change |
|------|--------|
| `core/verify_sidecar.py` | NEW (~200 lines): record mapping, meas extraction, golden-bias derivation, sidecar writer |
| `engine/stages/stage5_verify.py` | NEW function `p3_property(ctx, init, sim_data=None)` + `MeasContext` dataclass; existing `verify()`/`p2_property` untouched |
| `engine/run.py` | wire `p3_property` into the `--sim` path (evaluate P3(c) from `{simdir}/p2_wave.tr0` when present) |
| `deckgen.py` | add `--verify` flag; call sidecar writer after deck write in `_run_single`; pass `verify=` into `run_batch` |
| `core/batch.py` | `execute_jobs(..., verify=False)`: after `write_deck`, call sidecar writer inside its own try/except; result dict gains optional `sidecar` key |
| `engine/__init__.py` | add `__version__ = "2.0-2b"` (one line) |

`deckgen.py` imports `core.verify_sidecar` (and transitively `engine.*`) LAZILY, only
inside the `--verify` branch. With the flag off, no new imports execute and no code in
the deck-generation path changes -- the byte-identical guarantee holds structurally,
not just by test.

Jobs that fail v1 resolution (`job['error']` set) produce no deck and therefore no
sidecar; v1 already reports those failures. 3D constraint arcs produce 3 deck dirs and
get 3 sidecars (identical engine inputs; sidecar records its own deck path).

---

## 3. Data Contract (v1 resolved data -> four engine inputs)

`run_pipeline_src(record, src, meas, model, backend_name)` with
`backend_name = "v1-audit"`.

v1 has two per-arc shapes at the hook point:
- **collateral path** (`--node/--lib_type`): `job['arc_info']` -- the full MCQC-parity
  dict from `core/arc_info_builder.build_arc_info` (carries WHEN, LIT_WHEN, VECTOR,
  PROBE_PIN_N, NETLIST_PATH, INCLUDE_FILE, ...).
- **legacy path** (raw files): the `job` dict from `core/batch.plan_jobs` plus the
  `arc_info` from `_job_to_arc_info(job, files)`; single-arc mode has the `arc_info`
  from `core.resolver.resolve_all` plus the CLI args.

The sidecar adapter normalizes both through one function, `build_record(arc_info, job)`
(`job` may be `None` in single-arc mode; CLI `args.when` is folded into `arc_info` style
fields by the caller before the call):

### 3.1 `record`

`engine.types.Arc.from_record` REQUIRES `cell, arc_type, rel_pin, rel_dir, constr_pin,
constr_dir`; everything else is optional and lands in `Arc.raw`.

| record field | collateral source | legacy source | when absent |
|---|---|---|---|
| `cell` | `arc_info['CELL_NAME']` | `job['cell']` | never absent (v1 resolved) |
| `arc_type` | `arc_info['ARC_TYPE']` | `job['arc_type']` | never absent |
| `rel_pin` / `rel_dir` | `arc_info['REL_PIN'/'REL_PIN_DIR']` | `job['rel_pin'/'rel_dir']` | never absent |
| `constr_pin` / `constr_dir` | `arc_info['CONSTR_PIN'/'CONSTR_PIN_DIR']` | `job['constr_pin'/'constr_dir']` | never absent. Note: for non-cons arcs v1 sets CONSTR_PIN = REL_PIN (MCQC parity); passed through as-is |
| `when` | `arc_info['LIT_WHEN']`, else `to_lit_when(arc_info['WHEN'])` | `to_lit_when(job['when'])` | `""` -- OPTIONAL cross-check oracle. Engine derives biases independently; `sens.arc_check` then reads "arc.when: (none supplied) -- derived independently" |
| `lit_when` | `arc_info['LIT_WHEN']` verbatim | same as `when` | `""`; raw provenance only (lands in `Arc.raw`) |
| `when_literal` | `arc_info['WHEN']` (e.g. `!SE&SI`) | `job['when']` | `""`; raw provenance only |
| `vector` | `arc_info['VECTOR']` | absent | `""` -- OPTIONAL oracle, recorded in the sidecar for the future S3-vs-vector cross-check; engine ignores it today |
| `probe_list` | `[arc_info['PROBE_PIN_1'], 'PROBE_PIN_2', ...]` (numeric order, empties dropped) | `[job['probe_pin']]` | `[]` -- engine probes structural state nodes regardless (S3 derives its own probes) |
| `measurement` | the `meas` string (3.3) | same | `""` |
| `arc_id` | `job['arc_id']` | `job['arc_id']` or synthesized from fields | sidecar identifier only |
| `corner` | `job['corner']` | `job['corner']` | `""` in single-arc mode |

**Encoding rule (the one real translation):** the engine's `whencond.parse_when`
consumes the ENCODED form (`notSE_SI`: `_`-joined tokens, `not` prefix = 0). v1's
`WHEN` is the literal boolean (`!SE&SI`). `to_lit_when` converts: split on `&`, strip
whitespace, `!X -> notX`, join with `_`; `NO_CONDITION`/empty -> `""`. The collateral
path prefers `LIT_WHEN` verbatim (it is already encoded); conversion is the fallback
and the only path for legacy/single-arc jobs.

**NO_CONDITION normalization (explicit):** `record["when"]` is normalized BEFORE the
engine call: `"" if value in ("", "NO_CONDITION") else value`. The sentinel must never
reach `parse_when` as a token (it would otherwise be at the mercy of that parser's
guard); an empty `when` deterministically takes `sens.arc_check`'s
"(none supplied) -- derived independently" branch. Covered by a unit test on
`build_record` (Section 8e).

`when` and `vector` are NEVER required: a missing oracle degrades the sidecar's
`arc_check` line to "derived-independently", it does not block the engine.

### 3.2 `src` -- LPE netlist text

`open(arc_info['NETLIST_PATH']).read()` (the same path v1 resolved and substituted into
the deck). If `NETLIST_PATH` is empty or unreadable, the engine cannot run: emit a
sidecar with `status="ERROR"` and `error.summary="no netlist text available
(NETLIST_PATH=...)"`, and continue (rule: engine failure never breaks v1).

### 3.3 `meas` -- the measurement block v1 passes through

v1 has no structured measurement object; the measurement block lives in the SUBSTITUTED
deck lines that v1 just built (in memory at the hook point as `nominal_lines`).
`extract_meas_block(deck_lines)` returns, as one string:

1. the contiguous block from the line containing `* Measurements` up to (excluding)
   the first subsequent line starting with `.tran`;
2. fallback if no marker: all lines starting with `.meas` (templates are TSMC-derived
   and carry the marker, but a `--template` override may not).

**An empty meas block is never silent.** If extraction yields nothing (no marker AND
no `.meas` lines):
- `meas = ""` still goes to the engine (S4 pass-through tolerates it), but
- P3 is forced to **STUB** with detail `"no measurement block found in v1 deck
  (marker '* Measurements' absent and no .meas lines)"` -- it must not evaluate
  checks (a)/(b) against a fabricated context, and
- the sidecar gains a top-level `"notes": ["meas extraction failed: ..."]` entry that
  the audit CSV surfaces in its `notes` column, so a formatting drift in templates
  shows up as a visible STUB cluster in the audit table, never as quietly-green rows.

Covered by a targeted test (Section 8e): strip the marker from a fixture deck and
assert P3 is STUB with that reason and the note is present.

### 3.4 `model` -- model include

`".inc '" + arc_info['INCLUDE_FILE'] + "'"` (a reference line, not file contents --
stage4 passes model through and never parses it; reading a multi-MB corner model into
memory buys nothing). Empty `INCLUDE_FILE` -> `model = ""`.

---

## 4. P3 Implementation -- "measurement context consistent"

New code in `engine/stages/stage5_verify.py`. P3 CONSUMES v1's already-substituted
structures (deck lines + arc_info); it never parses TCL.

### 4.1 Input: `MeasContext`

Built by `core/verify_sidecar.py` from v1's in-memory deck lines + arc_info, passed to
the engine as a small dataclass (defined next to `p3_property`):

```python
@dataclass
class MeasContext:
    rel_edges: list      # [(name, t_ns, direction)] e.g. [("t01", 0.0, "fall"), ...]
    trig_cross: int      # cross=N from the TRIG CLAUSE of the primary .meas
    trig_td_ns: float    # td= ONLY if it appears inside the trig clause (else 0.0)
    capture_t_ns: float  # edge time the meas block's trig actually selects
    vdd: float           # from arc_info['VDD_VALUE']
    notes: list          # extraction provenance lines (self-describing detail)
```

**Cross-counting convention (normative).** A `.meas` line is split at the `targ`
keyword: attributes textually before `targ` belong to the trig clause, attributes
after it belong to the targ clause. The capture edge is the `cross=N`-th crossing of
`v(REL_PIN)` through the trig `val` threshold, counted from `max(t=0, trig-clause td)`;
each stdvs edge scheduled at `t0k` contributes exactly one crossing (at `t0k + slew/2`;
the schedule uses `t0k` -- slew offsets cancel in edge ORDERING, which is all (a) and
(b) consume). A `td=` in the targ clause constrains the target search only and MUST NOT
shift the capture-edge count. This matters: in all 63 production templates, `td=`
appears exclusively in the targ clause -- a parser that naively attached any `td=` on
the line to the trigger would systematically misplace the capture edge.

**Worked example (real template `mpw/template__CP__rise__fall__1.sp`, golden corner
values from `engine/golden_env.py`, `ms = max_slew`).** The toggling-pin line is
`XVCP CP 0 stdvs_mpw_rise_fall_rise_fall ... t01..t04`, with
`related_pin_t01 = 10*ms`, `t02 = 20*ms`, `t03 = 50*ms`,
`t04 = 50*ms + constr_pin_offset`. Edge schedule:

```
#1 rise @ t01 = 10*ms      #3 rise @ t03 = 50*ms
#2 fall @ t02 = 20*ms      #4 fall @ t04 = 50*ms + offset
```

The primary measurement is
`.meas cp2q_del1 trig v(CP) val='vdd_value/2' cross=3 targ v(Q) val=... cross=1
td='related_pin_t03'`. Split at `targ`: trig clause = `cross=3`, NO td (the
`td='related_pin_t03'` is in the targ clause and is ignored for capture). Capture =
3rd CP crossing from t=0 = **rise @ t03 = 50*ms**. Check (a): direction `rise` ==
`arc.rel_dir` for a CP-rise arc -> ALIGNED. Check (b): full cycles strictly before
50*ms = the (rise@t01, fall@t02) pair = **1 pre-cycle**, == S3's derived
`precycle_count = 1` -> MATCH. (Had the parser attached the targ-clause td to the
trigger, it would count crossings only from 50*ms onward and look for a third edge
that does not exist -- the unit tests in Section 8d pin this exact case.)

Extraction (all from substituted deck text, regex on known v1 template shapes):
- the toggling-pin line `XV<REL_PIN> ... stdvs_mpw_<seq> ... t01='related_pin_t01' ...`
  gives the edge DIRECTION sequence (from the model-name suffix, e.g.
  `rise_fall_rise_fall`) and the edge-time parameter names;
- `.param related_pin_tNN = '<expr>'` and `.param max_slew/search_window = '<value>'`
  lines give the times. A deliberately tiny evaluator resolves only the forms v1
  templates use: numeric literals with units, `K * max_slew`, and
  `K * max_slew + <param>`; anything else marks the context UNRESOLVED;
- the primary measurement is the first `.meas` whose `trig` probes `v(<REL_PIN>)`
  (e.g. `cp2q_del1 trig v($REL_PIN) val='vdd_value/2' cross=3 td='related_pin_t03'`);
  `capture_t_ns` = the time of the `trig_cross`-th rel-pin crossing at or after
  `trig_td_ns`, per the edge schedule.

If extraction fails (unknown template shape, unresolved param), the context carries an
`unresolved` note and P3 reports STUB naming the offending line -- extraction problems
are visibility gaps, not engine verdicts, and must never crash the run.

### 4.2 Checks

`p3_property(ctx, init, sim_data=None) -> Property` mirrors `p2_property` style: every
detail line is `value <= reason`.

**(a) Capture-edge alignment** (static). The edge selected by the meas block
(`capture_t_ns` via cross/td) must exist in the assembled rel-pin schedule and its
direction must equal `arc.rel_dir` (the capturing direction S2/S3 reasoned about).
Detail example:

```
capture edge : t03 @ 50*max_slew (rise)  <= .meas trig cross=3 from t=0 (td is in targ clause; not counted)
arc expects  : rise  <= arc.rel_dir -- ALIGNED
```

**(b) Pre-cycle count** (static). Count full rel-pin cycles (consecutive
opposite-direction edge pairs) strictly before `capture_t_ns` in the schedule; compare
to `init.precycle_count.value` (S3 derives 1). Detail:

```
precycles    : 1 full CP cycle before capture  <= stdvs edge schedule
derived      : 1  <= S3: 1 pre-cycle loads the prior known value -- MATCH
```

**(c) State nodes settled before capture** (sim-dependent). Reuses
`engine.wave.parse_csdf` + `engine.wave.select` and the existing MARGIN logic
(`engine.sim.MARGIN`, bit test identical to `engine.sim._bit` -- exposed by importing
`_bit`, not duplicating it). For each probe node in `init.probes`: take the trace value
at the last CSDF time point `<= capture_t_ns`, apply `_bit(v, vdd)`; every node must be
a definite 0/1. Detail per node:

```
x1.ml_ax     : 0.448V -> 1 (definite)  <= within MARGIN=0.35 of rail @ t<=40.0ns
```

`sim_data` is `(times, traces)` from `parse_csdf`; callers obtain it from an existing
CSDF `.tr0` (the `--sim` path's `{simdir}/p2_wave.tr0`, or `--tr0`). Real-cell P2 has
already passed on the server, so this file exists in the `--sim` workflow.

### 4.3 Status rules

- any of (a)/(b) FAILs, or (c) ran and FAILed -> **FAIL**
- (a)+(b) pass and sim absent -> **STUB**, detail closes with
  `check : settled-before-capture -- NOT RUN (no sim; run --sim for P3(c))`
- (a)+(b) pass, (c) ran and passed -> **PASS**
- context UNRESOLVED -> **STUB** with the offending line in detail

(Static failures must surface even without a simulator; STUB is reserved for "could
not evaluate", never for "evaluated and failed".)

### 4.4 Callers

- `core/verify_sidecar.py`: builds `MeasContext` from v1 deck lines, calls
  `p3_property(ctx, result.init, sim_data=None)` and replaces `result.verdict.p3`
  before writing the sidecar (same pattern run.py uses today for P2).
- `engine/run.py --sim`: after `run_p2`, if `{simdir}/p2_wave.tr0` (or `--tr0`) exists,
  parse it and call `p3_property` with `sim_data`; replace `result.verdict.p3`. In the
  engine-only path there are no v1 deck lines, so `MeasContext` is built from the P2
  deck's own timeline (`p2_deck.build` already returns `t_cap_edge`); `rel_edges` come
  from its PWL schedule. This keeps P3 testable on the server without the v1 flow.
- `pipeline.verify()` keeps its current STUB P3 -- the pipeline signature and S0-S2 are
  untouched.

---

## 5. Verdict Sidecar Format

One JSON per generated deck directory: `{deck_dir}/verify.json`, written with
`json.dump(..., indent=2, sort_keys=True)` + trailing newline (ASCII only).

```json
{
  "schema_version": 1,
  "status": "OK",
  "arc": {
    "arc_id": "hold_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2",
    "cell": "DFFQ1",
    "arc_type": "hold",
    "corner": "ssgnp_0p450v_m40c_cworst_CCworst_T",
    "rel_pin": "CP", "rel_dir": "rise",
    "constr_pin": "D", "constr_dir": "fall",
    "when": "notSE_SI",
    "when_literal": "!SE&SI",
    "vector": "xxRxFxx"
  },
  "engine": {
    "version": "2.0-2b",
    "commit": "accb1ba"
  },
  "verdict": {
    "overall": "STUB",
    "p1": {"status": "PASS", "detail": ["obligation : ...", "bias SE : 0  <= ...", "..."]},
    "p2": {"status": "STUB", "detail": ["..."]},
    "p3": {"status": "STUB", "detail": ["capture edge : ...", "precycles : ...", "..."]}
  },
  "biases": {
    "derived": {"SE": {"value": 0, "reason": "scan path masked ..."}, "SI": {"value": 1, "reason": "..."}},
    "golden":  {"SE": 0, "SI": 1},
    "match": "MATCH"
  },
  "arc_check": "arc.when {'SE': 0, 'SI': 1} vs derived ...: AGREE",
  "deck": "nominal_sim.sp",
  "stage_log": ["S0 parse    : ...", "S1 ccc      : ...", "..."],
  "timestamps": {"started": "2026-06-09T12:00:00+00:00", "finished": "2026-06-09T12:00:01+00:00"}
}
```

Field sources:
- `verdict.*`: `PipelineResult.verdict` serialized (`Property.name/status.value/detail`),
  with `p3` replaced by the real `p3_property` result (Section 4.4).
- `biases.derived`: `result.sens.side_biases` -- `{pin: {value, reason}}` from the
  `Derivation` wrappers.
- `biases.golden`: derived from `arc_info['WHEN']` with the exact semantics of v1's
  `deck_builder._generate_when_condition_lines` (split on `&`, `!X` -> 0 else 1, SKIP
  rel/constr pins -- they are driven, not biased). If `SIDE_PIN_STATES` is non-empty it
  wins (it is the more explicit MCQC field). Empty when -> `{}`.
- `biases.match` is THREE-STATE (plus N/A), classified per pin and then aggregated.
  Per pin (only pins present on BOTH sides are classified; extra derived pins are
  listed but never counted):
  - pin in `sens.set_pins` (CRITICAL -- the derivation requires this value):
    equal -> `match`, different -> `mismatch`;
  - pin in `sens.masked_pins` (NON-CRITICAL -- the derivation holds it at a
    convenience value; ANY golden value is acceptable): always `non_critical`,
    NEVER `mismatch`, regardless of the values.
  Aggregate: `"MISMATCH: SE(derived=1 golden=0), ..."` if any critical pin disagrees;
  else `"MATCH"` if at least one critical pin was compared (non-critical differences
  appended informationally: `"MATCH (non-critical: SI derived=1 golden=0)"`);
  else `"NON_CRITICAL"` when only masked pins were comparable;
  else `"N/A (no golden biases in deck)"`.
  Rationale: a masked pin's value is by definition not load-bearing -- counting it as
  MISMATCH would flood the audit CSV with false disagreements and bury the real ones.
- `arc_check`: `result.sens.arc_check` verbatim (already self-describing: AGREE /
  DISAGREE / "(none supplied) -- derived independently").
- `engine.version`: `engine.__version__` (new constant). `engine.commit`: best-effort
  `subprocess.run(["git", "rev-parse", "--short", "HEAD"])` with `cwd` = repo root,
  1 s timeout, `null` on any failure (the air-gapped server may lack git history).
- `timestamps`: `datetime.now(timezone.utc).isoformat()` before/after the engine call.

ERROR shape (engine raised, or src unavailable):

```json
{
  "schema_version": 1,
  "status": "ERROR",
  "arc": { "... same as above ..." },
  "engine": { "version": "2.0-2b", "commit": "accb1ba" },
  "error": {
    "type": "KeyError",
    "summary": "engine/stages/stage1_ccc.py:88 in decompose: 'VDD'",
    "traceback_tail": ["last 5 lines of traceback.format_exc()"]
  },
  "deck": "nominal_sim.sp",
  "timestamps": { "...": "..." }
}
```

The try/except wraps record-building, file reads, the pipeline call, P3, and sidecar
serialization; a failure inside sidecar WRITING itself is caught one level up in the
caller and reported as a per-job warning on stderr (never an exception out of
`_run_one`). The verdict keys (`verdict`, `biases`, `arc_check`) are simply absent in
ERROR sidecars -- consumers key off `status` first.

### 5.1 Audit CSV columns (aggregator is a later task; columns fixed NOW)

One row per sidecar; a trivial loop over `**/verify.json`:

| column | source |
|--------|--------|
| `cell` | `arc.cell` |
| `arc` | `arc.arc_id` |
| `corner` | `arc.corner` (added to the requested list -- batch is N arcs x M corners, rows are ambiguous without it) |
| `P1` | `verdict.p1.status` or `ERROR` |
| `P2` | `verdict.p2.status` or `ERROR` |
| `P3` | `verdict.p3.status` or `ERROR` |
| `bias_match` | first token of `biases.match`: MATCH / MISMATCH / NON_CRITICAL / N-A |
| `arc_check` | leading classification of the `arc_check` line: AGREE / DISAGREE / INDEPENDENT |
| `notes` | `error.summary` for ERROR rows; first FAIL detail line otherwise; empty when clean |

---

## 6. CLI

```
python3 deckgen.py ... --verify
```

- Works in single-arc, legacy batch, and collateral batch modes (all three end at the
  same sidecar writer).
- Per-job stdout gains one line when the flag is on:
  `  verify: {deck_dir}/verify.json  P1=PASS P2=STUB P3=STUB bias=MATCH` (or
  `verify: ... ERROR (KeyError: 'VDD')`).
- Exit code is unchanged by sidecar outcomes: `--verify` is an observer. A FAIL or
  ERROR sidecar does not fail the run (the audit CSV is where disagreement is triaged).
- GUI: not exposed (out of scope).

---

## 7. Error Handling Summary

| failure | behavior |
|---------|----------|
| engine raises anywhere | ERROR sidecar with type + summary + tail; v1 result untouched |
| netlist text unavailable | ERROR sidecar ("no netlist text available"); no engine call |
| meas block not found | engine runs; P3=STUB "no measurement block found in v1 deck" |
| MeasContext unresolved (odd template) | P3=STUB naming the line |
| sidecar write fails (disk) | warning on stderr; job still reports success for the deck |
| unsupported topology (no state nodes, combinational cell) | whatever the engine reports (P1/P2 FAIL or exception -> ERROR sidecar); never filtered silently, per CLAUDE.md error-reporting rules |

---

## 8. Tests

New file `tests/test_verify_sidecar.py` + P3 cases in `tests/engine/test_p3.py`.
All existing tests must pass unchanged. Run with python3.12.

**(a) Byte-identical regression -- whole output tree.** Using the existing collateral
fixture (`tests/fixtures/collateral/N2P_v1.0/test_lib`, DFFQ1, both define_arc entries)
and the legacy-path fixture from `test_end_to_end.py`: run `run_batch` twice into two
tmp dirs, once with `verify=False`, once with `verify=True`. Walk BOTH trees in full
(every file, not just `*.sp`): the set of relative paths must be identical except for
added `verify.json` files, and every common file must be sha256-identical. This also
proves the sidecar writer touched no v1-maintained artifact (manifests, indexes,
anything else living under the output root). The collateral manifest.json under
`tests/fixtures/` is additionally asserted unmodified (mtime/hash) after the verify
run.

**(b) Sidecar produced and well-formed on the DFFQ1 fixture arcs.** With
`verify=True`, every successful job dir contains `verify.json`; `json.load` succeeds;
`schema_version == 1`; `status in {"OK", "ERROR"}`; arc identity fields match the job.
Note: the fixture netlist body is `* body omitted` (no transistors), so the engine will
legitimately report ERROR or FAIL on it -- the assertion is well-formedness and
identity, not verdict. A second, engine-green case reuses the engine fixture netlist
(`engine/fixtures/` synthetic LPE flop) through the single-arc path with
`--netlist`/`--template` overrides and asserts `status == "OK"` and `verdict.p1.status
== "PASS"` -- proving the record mapping feeds the engine correctly end-to-end.

**(c) Engine exception path.** Monkeypatch `core.verify_sidecar.run_pipeline_src` to
raise `RuntimeError("boom")`; run a 2-job batch with `verify=True`; assert both decks
are written, both jobs report success, both sidecars have `status == "ERROR"`,
`error.type == "RuntimeError"`, and the run exits 0.

**(d) P3 unit tests** (`tests/engine/test_p3.py`), against hand-built `MeasContext`
objects and CSDF strings in the existing `tests/engine/test_wave.py` style:
- (a)-aligned: cross/td selects an edge of the expected direction -> detail says ALIGNED;
- (a)-misaligned: cross count selects a wrong-direction edge -> FAIL;
- td clause attribution: the worked-example line (`td=` in the TARG clause) must give
  capture = rise@t03 (counted from t=0); the same line with `td=` moved INSIDE the
  trig clause must shift the count -- pins the normative convention of Section 4.2;
- (b)-match and (b)-mismatch (schedule with 1 vs 2 pre-capture cycles vs S3's 1);
- (c)-settled: all probe traces at definite rails before capture -> PASS (with (a),(b) green);
- (c)-mid-rail: one node at VDD/2 -> FAIL with the offending `value <= reason` line;
- no sim_data -> STUB, static details still present;
- unresolved param expression -> STUB naming the line.

**(e) Loud-failure and normalization unit tests** (`tests/test_verify_sidecar.py`):
- meas marker stripped from a fixture deck's lines -> P3 STUB with the "no measurement
  block found" reason AND sidecar `notes` entry present (Section 3.3);
- `build_record` with `LIT_WHEN == "NO_CONDITION"` and with `WHEN == "NO_CONDITION"`
  -> `record["when"] == ""` in both, and the resulting sidecar `arc_check` contains
  "derived independently";
- `biases.match` three-state: masked-pin disagreement -> MATCH with non-critical note
  (not MISMATCH); set-pin disagreement -> MISMATCH; only-masked-pins-compared ->
  NON_CRITICAL.

Also: the non-ASCII byte scan over all new files must return empty (CLAUDE.md), and no
test assertion may be weakened (CLAUDE.md test discipline).

---

## 9. Acceptance Criteria

1. Full test suite (existing + Section 8) passes under python3.12.
2. `--verify` off: `git diff`-level guarantee that no production code path changed
   (lazy import), plus the byte-identity regression test.
3. `--verify` on against the collateral fixture: one `verify.json` per deck dir,
   schema-valid, ERROR sidecars only where the engine genuinely cannot run.
4. `python3 -m engine.run --netlist ... --sim` on the server now reports a real P3
   (PASS/FAIL) when `p2_wave.tr0` exists, STUB otherwise.
5. Non-ASCII scan empty; commits signed per repo config.
