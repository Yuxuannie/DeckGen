# Phase B1 — Collateral Wiring + Combinational Emitter — Design Spec

Date: 2026-06-30
Status: Approved shape, pending final spec review
Owner: Yuxuan

## Context

This is **Phase B1**, the foundation of Phase B (the principle-driven emitter) of
Demo 1 (production new-MCQC, for the MJ group). Phase A (measurement grammar:
mine/emit/round-trip) is complete: `core/measurement/emit.py` reproduces a
template's methodology recipe (options, waveform timestamps, `.option
ptran_nodeset` + `.nodeset` init, toggling model-name, optimization block, `.meas`,
`.tran`) from `config/measurement_grammar.json`.

Demo 1's end goal: the human only places **collateral**, and the engine emits a
real, runnable SPICE deck per (cell, arc, corner) — no per-cell template curation.
Phase B wires the emitter into deck assembly. The guiding principle (owner,
2026-06-30): **Demo 1's headline is "the vast majority of arcs auto-generate a
deck" — breadth over the common case first.** Sync cells are a hard bonus, not the
center. **Unsupported edge cases must be explicitly named with where the difficulty
lies** (a first-class deliverable, echoing "no silent drops / 信息全面").

### Phase B roadmap (this spec is B1)

- **B1 (this spec)** — collateral wiring + combinational delay/slew emitter. Zero
  research risk; covers the largest arc count in a real library; proves the
  collateral-only pipeline end to end.
- **B2** — structural sequential classification + depth (FF-chain vs latch vs
  recognized-unsupported; derive depth for FF-chain). The research nugget.
- **B3** — parametric sequential recipe emitter (FF-chain + latch), wire into
  `stage4`, HSPICE hold/setup in airgap; fix `stage3` `precycle_count` hardcoded 1.
- **B4** — coverage + unsupported report (derived / recognized-unsupported-why /
  unparseable).

### Today's gap (what B1 changes)

`engine/stages/stage4_deckgen.assemble` currently emits a deck whose:
- **COLLATERAL section is hardcoded placeholders** (`vdd=0.450`, `temp -40`,
  `std_wv.spi`, `cl=0.000542p`, ...).
- **MEASUREMENT section is passed through** from an externally supplied block.
- **ENGINE section uses the sequential hold/P2 path** (`stage2.derive` +
  `stage3.derive`), even for combinational arcs.

B1 replaces the first two with real collateral + `emit()`, and adds a combinational
engine-bias section. `resolve_all_from_collateral` (in `core/resolver.py`) already
produces the collateral arc_info keys (`VDD_VALUE`, `TEMPERATURE`, `INCLUDE_FILE`,
`WAVEFORM_FILE`, `NETLIST_PATH`, `NETLIST_PINS`, `PUSHOUT_PER`, `INDEX_*_VALUE` from
template.tcl), so the collateral side is **resolved, not newly built** — B1 consumes it.

### Runtime invariants (inherited)

stdlib only, ASCII-only (`.py`/`.json`/`.sp`), no network. HSPICE runs only in
airgap; local validation is simulator-free.

## Goal / success criterion

For a combinational delay/slew arc, the engine assembles a deck from **collateral +
`emit()` + engine-derived side-pin bias** — no per-cell template. Success
(owner-chosen "runs and measures"): the deck is accepted by HSPICE and produces
non-failed `.mt0` delay/slew measurements (proven in airgap); locally, the deck's
recipe+collateral sections reproduce the corresponding template byte-for-byte and
the bias section passes structural checks.

## Scope

### In scope (B1)

1. **Uniform assembler** — refactor `engine/stages/stage4_deckgen.assemble` (or a new
   `core/deck_assemble.py` that supersedes the combinational path) into:
   ```
   deck = collateral_section(arc_info)        # real values from arc_info
        + x1_instance(NETLIST_PINS, CELL)
        + engine_bias_section(comb_result)     # B1's only engine-specific section
        + emit(grammar_entry, arc_info)        # Phase A recipe (measurement+waveform+ts)
   ```
   `$`-placeholder substitution stays delegated to the existing `core/deck_builder`
   (not re-implemented).

2. **Combinational engine-bias section** — for each non-toggling input (side pin),
   a voltage source tying it to a rail at its derived sensitizing value:
   `V<pin> <pin> 0 'vdd_value'` (=1) / `V<pin> <pin> 0 'vss_value'` (=0). The value
   set comes from `stage2_sensitize.derive_combinational` (the SENSITIZING region):
   pick one sensitizing state; when the kit `-when` is present, prefer the
   sensitizing state matching it (engine is source of truth; divergence is surfaced,
   not silently overridden — feeds Demo 3 audit). The toggling pin (`rel_pin`) is
   NOT in this section — its source is the grammar recipe's `XV<rel_pin> ... stdvs_*`
   line.

3. **Grammar entry selection for a combinational arc** — select the delay/slew
   recipe via `emit.select_entry(arc_type, rel_dir, other_dir=probe_dir, ...)`. The
   probe pin + output direction come from `derive_combinational` (`output`,
   `out_dir`). (Cluster-tag selection for a brand-new combinational cell is the
   general case; B1 may key on (arc_type, dirs) since the delay grammar has one
   cluster, `common_inpin`.)

4. **Local validation (the B1 "round-trip")**:
   - recipe + collateral sections reproduce the matching template's non-bias content
     byte-for-byte (extend the Phase A region machinery: the template minus its
     `* Unspecified pins`/`* Pin definitions` bias placeholder == assembled
     recipe+collateral).
   - bias section structural checks: every non-toggling input appears exactly once,
     tied to exactly one rail; the tied values equal the engine's chosen sensitizing
     state; the toggling pin is absent from the bias section.

5. **A thin entry point** `assemble_combinational(arc_info, src, grammar) -> deck_text`
   that callers (and B4's report, Phase C) invoke. Never raises on one bad arc:
   returns a structured error (cell unparseable / no sensitizing state / no grammar
   entry) naming what failed — never a silent drop.

### Out of scope (later)

- **B2/B3**: all sequential (hold/setup/mpw/latch) deck assembly and depth derivation.
- **B4**: the library-wide coverage/unsupported report (B1 provides the per-arc
  structured error it will aggregate).
- **C**: LSF orchestration, running HSPICE at scale.
- No timing-value extraction / `.lib` assembly (downstream `Lib-Char-Certi`).
- Aligning the bias-line *syntax* to MCQC's exact convention if it differs from the
  voltage-source form — deferred to an airgap check (the deck runs regardless;
  byte-matching the bias section is explicitly NOT a B1 goal, because the templates
  leave that section empty).

## Data flow

```
(cell, comb arc, corner)
  -> resolve_all_from_collateral  -> arc_info {collateral keys + INDEX_* + pins}
  -> stage0_parse(netlist) -> graph ; stage1_ccc -> ccc
  -> stage2.derive_combinational(graph, arc, ccc) -> CombSensitizationResult
       (output, out_dir, sensitizing states, side_pins)
  -> select_entry(grammar, arc_type, dirs) -> recipe entry
  -> assemble_combinational:
       collateral_section(arc_info)
       + x1_instance
       + engine_bias_section(chosen sensitizing state)
       + emit(entry, arc_info)            # value placeholders filled by deck_builder
  -> deck_text  (ASCII)
```

## Key interfaces

```python
# core/deck_assemble.py   (new; combinational path of the uniform assembler)
def assemble_combinational(arc_info: dict, netlist_src: str, grammar: dict
                           ) -> AssembleResult
# AssembleResult: {status: "OK"|"ERROR", deck_text: str|None,
#                  bias: {pin: 0|1}, chosen_when: str, output: str, out_dir: str,
#                  error: str|None}   # error names what failed (no silent drop)

def collateral_section(arc_info: dict) -> list[str]      # real .inc/corner/load/VV*/CQ
def engine_bias_section(side_bias: dict, rails=("vdd_value","vss_value")) -> list[str]

# core/deck_assemble_check.py  (local, simulator-free validation)
def check_against_template(deck_text, template_path, side_pins, toggling_pin) -> dict
#  -> {recipe_collateral_byte_match: bool, bias_structural_ok: bool, detail: [...]}
```

The `engine_bias_section` writing format: `V<pin> <pin> 0 '<rail>'`, one line per
side pin, sorted by pin name for determinism.

## Error handling (never fail silently)

`assemble_combinational` returns `status=ERROR` with a `error` string for: netlist
parse failure; the arc's CCC has a state node (sequential — out of B1 scope, names
"sequential, handled by B2/B3"); empty SENSITIZING set (pin does not combinationally
drive the output); no grammar entry for the arc's (arc_type, dirs). These become B4
report rows, not exceptions.

## Testing strategy

- **Local (dev), simulator-free:**
  - `engine_bias_section`: a 2-input AND-style synthetic graph -> the side pin tied
    to the rail matching the engine's sensitizing state; toggling pin absent.
  - `assemble_combinational` on a synthetic combinational cell with a known
    delay grammar entry -> deck_text contains the collateral values from arc_info,
    one X1 line, one bias line per side pin, and the emitted recipe lines.
  - `check_against_template`: assembled recipe+collateral reproduces a delay
    template's non-bias content byte-for-byte; bias structural checks pass.
  - error paths: sequential arc -> ERROR naming B2/B3; empty sensitizing -> ERROR;
    missing grammar entry -> ERROR. Each asserts the message names what failed.
- **Airgap (real):** assemble a real combinational delay/slew arc from N2P
  collateral, run HSPICE, confirm `.mt0` has a non-failed `meas_delay` / slew value.
  (Manual / Phase C-driven; not a local unit test.)
- ASCII guard: `grep -rPn '[\x80-\xff]'` over new `.py` empty.

## Success criteria

1. `assemble_combinational` produces a deck for a combinational delay arc from
   collateral + emit + engine bias, no per-cell template.
2. Local: recipe+collateral byte-reproduce the delay template; bias structural
   checks pass; error paths return named ERRORs (no silent drop).
3. Reuses `resolve_all_from_collateral` (collateral) and `deck_builder` (`$`-subst)
   and `emit` (recipe) — no duplication of those.
4. stdlib-only, ASCII-only; HSPICE-free locally; ready for airgap HSPICE run.
5. Clean seam (`assemble_combinational` + structured error) for B4's report and for
   B3 to mirror with `assemble_sequential`.

## Open questions (resolve during planning, not blocking)

- Whether to refactor `stage4_deckgen.assemble` in place or add `core/deck_assemble.py`
  and leave `stage4` for the legacy/sequential path until B3 — leaning new module so
  B1 does not destabilize the existing sequential pipeline; B3 unifies.
- Exact `select_entry` key for combinational (the delay grammar has a single
  `common_inpin` cluster) — start with (arc_type, rel_dir, probe_dir); revisit when
  slew templates are present in the airgap corpus.
- Which sensitizing state to pick when several match the kit `-when` — deterministic
  rule (e.g. all-side-pins-non-controlling-value, or first in sorted order);
  decide in planning against a concrete AOI/OAI example.
