# Phase B3 -- Sequential Deck Emitter (hold + mpw) (Design)

**Status:** design of record for B3 (the runnable sequential deck emitter).
**Branch:** claude/lucid-noether-cat8lr. Base: point2a-non-cons.
**Depends on:** B2 (structural classification `classify()`), B1 (`assemble_combinational`
pattern + `collateral_section`/`engine_bias_section`), Phase A (`emit()`/`select_entry`).
**Absorbs:** the already-written "B3 step 1" precycle wiring (kept, reviewed as a task).

## 1. Goal

Produce a **runnable SPICE deck for a sequential arc** -- the analog of B1's
combinational emitter -- so a sequential cell can actually be simulated in the
airgap. Two deck flavors, selected by arc semantics:

- **hold deck**  -- the D-vs-CP timing constraint (`.meas cp2q_del1 cp2q_del2 cp2cp`).
- **mpw deck**   -- the CP minimum-pulse-width (`.meas cp2q_del1 cp2cp`).

Both are one function, `assemble_sequential`, sharing the entire deck scaffold;
they differ only in which grammar cluster-tag family is selected from a
structural depth.

## 2. Entry point

`core/deck_assemble.py`:

```
assemble_sequential(arc_info: dict, netlist_src: str, grammar: dict) -> dict
```

Mirrors `assemble_combinational`'s contract exactly:
- **Never raises.** A bad or unsupported arc is a named `_err(...)` row (status
  "ERROR", `deck_text=None`, `error=<reason>`), never a silent drop. This feeds
  B4's coverage report.
- Success returns `{"status":"OK","deck_text":<str>, "bias":<dict>,
  "verdict":<str>, "depth":<int>, "cluster_tag":<str>, "family":<"hold"|"mpw">,
  "error":None}`.
- Replaces the sequential DEFER currently at `deck_assemble.py:104`
  (`assemble_combinational` keeps returning its ERROR for sequential arcs; the
  new function is what the sequential path calls instead).

## 3. Pipeline (mirrors B1, folds in the kept precycle wiring)

1. `stage0_parse.parse` -> `stage1_ccc.decompose`. Parse failure -> `_err`.
2. `classify(graph, cell)` (B2, never raises) -> `verdict`, per-bit `ff_depth`.
3. **Depth:** `ff_chain` -> `bits[0].ff_depth`; `multibit` -> `max(ff_depth)`;
   `latch` -> 0. (Same rule the precycle wiring uses; single source of truth.)
4. **Gate (never silent):**
   - `ff_chain` / `multibit` -> proceed.
   - `latch` (depth 0) -> `_err("latch mpw/hold not yet supported (transparent;
     different methodology family) -- <reason>")`.
   - `combinational` / `recognized_unsupported` -> `_err` carrying
     `classify().reason`.
5. **Family + depth -> cluster_tag** (Section 4). Out-of-range depth -> `_err`.
6. `select_entry(grammar, arc_type="mpw", rel_dir=<f>, other_dir=<o>,
   cluster_tag=<tag>)`. `SelectionError` -> `_err("no grammar entry: ...")`.
7. `emit(entry, arc_info, fill_values=True)`, then resolve `$HEADER_INFO` with the
   same targeted `.replace` B1 uses (never a blanket strip -- any other unresolved
   `$` must survive so the check catches it). The recipe already carries its own
   `.nodeset` init, `.meas`, `.tran`, `.end`.
8. **Bias:** the P1-proven sequential side-pin assignment (e.g. `SE=0`, `SI=1`)
   the engine already derives for a sequential arc. Emitted via the existing
   `engine_bias_section(bias)`. (The plan pins the exact pipeline attribute that
   exposes this bias; it is the same assignment stage4 emits today.)
9. **Deck assembly** (same section order as B1):
   `collateral_section(arc_info)` + `["* ===== INSTANCE =====",
   "X1 <NETLIST_PINS> <cell>"]` + `engine_bias_section(bias)` + `recipe`.
   `deck_text = "\n".join(lines) + "\n"`.

## 4. Depth -> cluster_tag mapping (grounded in the mined recipes)

Selected by `arc_info["ARC_TYPE"]`: `hold` -> hold family; `mpw` /
`min_pulse_width` -> mpw family.

**hold family (`CP.sync{N}.D`, fall->rise only):**

| depth N | cluster_tag | rel_dir | other_dir |
|---|---|---|---|
| 1 | `CP.syncx.D` | fall | rise |
| 2..6 | `CP.sync{N}.D` | fall | rise |
| >6 | ERROR "depth N beyond mined corpus (hold max 6)" | | |

**mpw family (`CPN` / `sync{N}.CP`):**

| depth N | cluster_tag | rel_dir / other_dir |
|---|---|---|
| 1 | `CPN` | from arc `REL_PIN_DIR` (both fall/rise and rise/fall exist) |
| 2..6 | `sync{N}.CP` | from arc `REL_PIN_DIR` |
| >6 | ERROR "depth N beyond mined corpus (mpw max 6)" | |

Recipe evidence (verified in `config/measurement_grammar.json`): hold
`CP.sync{N}.D` waveform model has 2N+2 edges, `cp2cp cross=2N+2`,
`cp2q_del1 cross=2N+1`, and carries the extra `cp2q_del2` measurement that marks
the D-constraint; `CP.syncx.D` has 4 edges (= 2*1+2 -> depth 1). mpw `sync{N}.CP`
model has 4N-1 edges; `CPN` is the single-flop (depth-1) CP min-pulse-width case.

`other_dir` for the mpw family is the opposite of `rel_dir`; both variants exist
in the grammar, so selection is by the arc's `REL_PIN_DIR` (no flip logic
needed -- unlike B1's combinational output-edge flip).

## 5. Prototype wiring

`tools/lib_deckgen.py` (already present) is repointed from `res.deck.text`
(placeholder measurement) to `assemble_sequential(...)` so it writes a **real,
recipe-backed** deck per sequential cell. Its `--arc-type {hold,mpw}` selects the
family (default `hold`). Combinational / unsupported cells stay reported-with-
reason, never a deck. This is the hands-on prototype target.

## 6. Deliberate scope cuts (flagged, never silent)

- **latch** hold/mpw (transparent; distinct methodology) -> named ERROR.
- **depth > 6** -> named ERROR (beyond the mined `sync2..6` corpus).
- **`sync1p5` / `DET` / `DRDF` / `retn` / `WWL` specialized families** -> not
  mapped in B3; `classify` routes their cells to `ff_chain`/`multibit`/
  `recognized_unsupported`, and any depth that lands outside the tables above is
  a named ERROR. A future step adds these clusters.
- **per-bit multibit fan-out (N decks):** one arc -> one deck; multibit collapses
  to the deepest bit's depth (documented, matches the precycle rule).
- **the measurement block stays Liberate-owned pass-through** (as in B1): the
  engine positions the grammar recipe; it never authors or edits `.meas` bodies.

## 7. Constraints (binding)

ASCII-only (`.py`/`.json`/`.sp`/`.spi`), stdlib + engine only, simulator-free,
python3.12. `stage1_ccc.py` and the B2 classifier are consumed unchanged. No
existing test assertion weakened (changing one needs Yuxuan's explicit approval).
Config paths relative to script location. Never fail silently / never drop an arc.

## 8. Testing (TDD, python3.12)

`tests/` (net-new):
- **mapping unit tests** on `_seq_cluster_tag(family, depth, rel_dir)`:
  hold depth1->`CP.syncx.D`, depth2->`CP.sync2.D`, depth6->`CP.sync6.D`,
  depth7->error; mpw depth1->`CPN`, depth3->`sync3.CP`, depth7->error.
- **assemble_sequential success (SDFX fixture):** `ARC_TYPE="hold"` ->
  status OK, `cluster_tag=="CP.syncx.D"`, `family=="hold"`, deck contains the
  `.inc` collateral, the `X1 ... SDFX...` instance, the `V`-source bias, and the
  recipe's `cp2q_del1`; **no unresolved `$`** (reuse B1's check).
- **assemble_sequential mpw (SDFX fixture):** `ARC_TYPE="mpw"` ->
  `cluster_tag=="CPN"`, `.meas cp2cp` present, `cp2q_del2` absent.
- **never-raises gates:** a combinational fixture -> ERROR with reason; a
  latch (SYNTH_LATCH fixture) -> ERROR naming "latch"; a depth-8 synthetic
  classify -> ERROR naming the corpus limit.
- **lib_deckgen smoke:** `--arc-type hold` over `engine/fixtures` writes a deck
  for the sequential cell and reports (never drops) the combinational ones;
  the existing engine suite stays green.
