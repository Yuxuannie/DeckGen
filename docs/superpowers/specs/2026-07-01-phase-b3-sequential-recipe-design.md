# Phase B3 -- Sequential Recipe Wiring (precycle from structural depth) (Design)

**Status:** design of record for B3 step 1 (the precycle-count fix).
**Branch:** claude/lucid-noether-cat8lr. Base: point2a-non-cons.
**Depends on:** B2 (structural sequential classification) -- ready to merge.
**Fixes:** stage3's hardcoded `precycle_count = 1`.

## 1. Goal

B2 delivered `classify(graph, cell_name) -> SequentialClass` but left it
unwired: nothing in the stage0->stage5 pipeline consumes it, and
`stage3_initialize.derive` still emits `precycle_count = Derivation(1, ...)` for
every cell. That is correct only for a depth-1 DFF; a sync-depth-N flop chain
needs N pre-cycles to push the datum through N master/slave stages before the
capturing edge, and P3 (stage5) checks exactly that count against the waveform
edge schedule. B3 step 1 wires `classify()` into the pipeline and derives
`precycle_count` from the structural class.

## 2. What precycle_count actually drives (verified in-tree)

- `stage3_initialize.derive` -> `InitializationResult.precycle_count`.
- `stage4_deckgen.assemble` emits `init.stimulus` (descriptive comment lines)
  into the deck's ENGINE section; it does **not** read `precycle_count`.
- `stage5_verify.p3_property` (the real P3(b) check, when a sim is present):
  `cycles = len(rel_edges before capture)//2; ok_b = cycles == precycle_count.value`.
  So `precycle_count` is the **expected number of full rel-pin cycles before the
  capturing edge** -- the pipeline-honest value that must equal the structural
  depth.
- `stage5_verify.verify` and `viz`/`pipeline` logs surface it for display.

Consequence: the load-bearing change is the **value** of `precycle_count`
(checked by P3). Expanding the descriptive stimulus comment to name the count is
cosmetic and included for honesty; the external waveform collateral (std_wv) is
not generated here.

## 3. Mapping: verdict -> precycle_count (B3 step 1)

| structural verdict | precycle_count | reason |
|---|---|---|
| `latch` | 0 | transparent; no clocked pre-cycle |
| `ff_chain` | `bits[0].ff_depth` | depth N -> N cycles push datum through N master/slave stages |
| `multibit` | `max(b.ff_depth for b in bits)` | deepest bit sets the count (Arc carries no probe_pin to select a single bit; the deepest bit is the safe upper bound, and typical multibit is all-depth-1 -> 1) |
| `recognized_unsupported` | 1 (flagged) | never silent: `reason` carries the structural anomaly; pre-cycle defaulted to 1 for review |
| `combinational` | 1 (flagged) | guard; a hold arc should not reach here -- reason names it |
| `seq is None` | 1 (legacy) | no class supplied (direct unit calls); preserves prior behavior |

`ff_chain` always has one bit with >=2 stages, so `ff_depth >= 1`. An odd-core
`ff_chain` (`paired_cleanly=False`) still yields `ff_depth = k//2 >= 1`.

## 4. Wiring (surgical)

- `engine/pipeline.py._run`: after stage1, call
  `seq = stage1b_classify.classify(graph, arc.cell)` (never raises), append an
  `S1b classify:` log line (verdict + depth + any name-divergence/reason), and
  pass `seq` as a 5th arg to `stage3_initialize.derive`.
- `engine/stages/stage3_initialize.derive(graph, ccc, arc, sens, seq=None)`:
  new keyword-default `seq=None` (backward compatible -- all 5 existing callers
  pass 4 positional args and keep the legacy value). A new helper
  `_precycle_from_seq(seq)` implements the table in Section 3. The pre-cycle
  stimulus comment is parameterized by the derived count (0 -> "none
  (transparent latch)").
- No change to `InitializationResult`, `PipelineResult`, `stage4`, `stage5`, or
  `stage1_ccc`. `classify` is consumed duck-typed (`.verdict`, `.bits[i].ff_depth`,
  `.reason`, `.divergence`) so `stage3` needs no new import and no import cycle.

## 5. Deliberate scope cuts (B3 step 2, not in this change)

- **Hard "emit nothing + structured error" for `recognized_unsupported`.** The
  spec's stronger contract (no deck at all, a structured error return) needs a
  `PipelineResult` error variant that also serves other stages; that is a
  separate, larger change. Here the unsupported case is **never silently
  dropped** -- it is surfaced in the `S1b classify:` log line and in the
  `precycle_count.reason`. Documented as the next step.
- **Per-bit multibit deck fan-out (N decks).** A single arc yields one deck for
  one probe pin; emitting one deck per bit is a batch/emitter concern. Here
  multibit collapses to the deepest-bit pre-cycle count.
- **Waveform (std_wv) generation for depth>1.** External collateral; not owned
  by this pipeline.

## 6. Constraints (binding)

ASCII-only, stdlib+engine only, simulator-free. `stage1_ccc.py` unchanged. No
existing test assertion weakened (SDFX is depth-1 ff_chain -> precycle stays 1,
so `test_initialize`/`test_p3` are unaffected; new assertions are net-new).
`classify` already never raises; `_precycle_from_seq` relies on B2's contract
and is duck-typed.

## 7. Testing (TDD, python3.12)

`tests/engine/test_stage3_precycle.py` (net-new):
- `_precycle_from_seq` over real `classify_cores` outputs: latch->0,
  ff_chain(2 cores)->1, sync(4 cores)->2, multibit(2 bits depth1)->1,
  dangling->recognized_unsupported->1 with reason naming it, None->1.
- end-to-end: SDFX fixture -> `classify` = ff_chain, `derive(..., seq)` ->
  precycle_count.value == 1 (regression guard that the fixture path is stable).
- pipeline smoke: the existing engine suite exercises `_run`; the new path must
  keep it green.
