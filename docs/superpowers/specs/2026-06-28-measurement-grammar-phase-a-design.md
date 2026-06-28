# Measurement Grammar (Phase A) — Design Spec

Date: 2026-06-28
Status: Approved shape, pending final spec review
Owner: Yuxuan

## Context

This is **Phase A** of the "production new-MCQC / principle-driven emitter"
project (Demo 1 for the MJ production group). The end goal of that project is:
the human only places **collateral**, and the engine emits a real, runnable
SPICE deck per (cell, arc, corner) — no per-cell template curation.

Today `engine/stages/stage4_deckgen.assemble` produces a deck whose
ENGINE-DERIVED section is real (X1 instance, P1 biases, init, probes) but whose
**MEASUREMENT section is passed through unchanged** from an externally supplied
block, and whose COLLATERAL section is hardcoded placeholders. To reach
"collateral only", the engine must itself produce the measurement recipe.

The measurement recipe is **not** 854 distinct things. The 854 entries in
`config/template_rules.json` are *selection* rules (which template path). The
measurement *body* collapses into a small, parameterized grammar with two
families (verified by reading the in-repo templates):

- **Family 1 — simple-edge (delay, slew).** Single stimulus edge; measures are
  `trig rel@Vdd/2 -> targ probe@Vdd/2` plus an output transition-time measure.
  No optimization. Example (`templates/N2P_v1.0/delay/...rise_delay_fall.sp`):
  ```
  .meas tran meas_delay  trig v($REL_PIN)    val='vdd_value/2'   cross=1 \
                         targ v($PROBE_PIN_1) val='vdd_value/2'   cross=1
  .meas tran half_tt_out trig v($PROBE_PIN_1) val='vdd_value*0.7' cross=1 \
                         targ v($PROBE_PIN_1) val='vdd_value*0.3' cross=1
  .meas tran meas_tt_out param='half_tt_out*2'
  ```

- **Family 2 — constraint-optimization (hold, mpw, setup, removal, recovery).**
  Multi-phase `stdvs_mpw_*` waveform sources with timing points `t01..t04`
  parameterized by `max_slew` and `constr_pin_offset`; a `constr_pin_offset`
  optimization loop (`OPT1(opt_init,opt_lb,opt_ub)`); measures `cp2q_del1`,
  `cp2q_del2`, `cp2cp` with multi-`cross`; `MEAS_DEGRADE_PER` pushout; THANOS opt
  headers. Example (`templates/N2P_v1.0/mpw/template__CP__syncx__D__fall__rise__1.sp`):
  ```
  .meas cp2q_del1 trig v($REL_PIN) val='vdd_value/2' cross=4 \
                  targ v($PROBE_PIN_1) val='vdd_value/2' cross=1 td='related_pin_t03'
  .meas cp2cp     trig v($REL_PIN) val='vdd_value/2' cross=3 \
                  targ v($CONSTR_PIN) val='vdd_value/2' cross=4
  ```

### The airgap constraint (central design driver)

The local dev environment can only reach **delay + mpw** templates (67 files).
The real **airgapped Linux** environment holds the full corpus including all
**hold + delay** variants. The grammar must be **comprehensive there**, not just
for what is visible locally. Therefore the grammar is **not hand-authored**; it
is **mined** from whatever corpus it is pointed at, and proven complete by a
**round-trip** check. Built/tested locally on delay+mpw; run for real on the full
hold+delay corpus in airgap, where any uncovered variant is reported by diff.

Runtime invariants (inherited from the repo): **Python stdlib only, ASCII-only**
for all `.py`/`.json`/`.sp` artifacts, no network.

## Scope

### In scope (Phase A) — three deliverables

1. **Miner** — `core/measurement/mine.py`
   - Scans a template directory; for each `.sp`, isolates the measurement-recipe
     region and **templatizes** it: replaces concrete pin names and corner/slew/
     load values back into placeholders (`$REL_PIN`, `$PROBE_PIN_1`,
     `$CONSTR_PIN`, `$VDD_VALUE`, `$INDEX_1_VALUE`, `$INDEX_2_VALUE`,
     `$MAX_SLEW`, `$PUSHOUT_PER`, ...).
   - **Clusters** templatized recipes by a key (arc_type family, directions,
     structural features) and emits `config/measurement_grammar.json`.
   - Comprehensive-by-construction: the grammar is the set of distinct patterns
     present in the pointed-at corpus.

2. **Emitter** — `core/measurement/emit.py`
   - `emit(arc_type, rel_pin, rel_dir, constr_pin, constr_dir, probe_pin,
     params) -> list[str]` returns the measurement-recipe lines for one arc by
     selecting a grammar entry and filling placeholders.
   - stdlib + ASCII; pure function; consumes `measurement_grammar.json`.
   - This is the seam Phase B's `stage4` calls instead of pass-through.

3. **Round-trip validation** — CLI `mine.py validate` + `tests/measurement/`
   - For every template in the corpus: re-emit its measurement recipe from the
     grammar and **diff byte-for-byte** against the original region.
   - Reports: coverage % , per-arc-type counts, and an explicit list of any
     templates whose recipe is **not** reproduced (the airgap probe for missing
     hold/slew variants). Exit non-zero if any mismatch, so it gates CI/airgap runs.

Families/arc_types to cover: **delay, slew, hold, mpw** (slew and the other
constraint arcs — setup/removal/recovery — fall into the two families above and
are covered automatically when their templates are present in the corpus).

### Recipe region boundary (what the grammar owns)

The "measurement recipe" = the full arc-type-specific **methodology body** of the
deck — stimulus, **initialization**, and measurement — everything that is fixed by
the three-party (TSMC/EDA/customer) methodology rather than derived per cell.
This is broader than just `.meas`; correcting the earlier draft, the grammar owns
the **initialization design** too. Concretely the grammar owns:

- waveform timestamp params (`related_pin_t0x`, `constrained_pin_t0x`) and the
  family-specific `max_slew` / `search_window` wiring (mpw: `max_slew='0.1u'` +
  `search_window=$MAX_SLEW`; delay: `max_slew=$MAX_SLEW`)
- the toggling-pin source **model-name** selection (`stdvs_rise`,
  `stdvs_mpw_fall_rise_fall_rise`, ...) keyed by family + directions — the model
  *name*, not the waveform file
- **initialization**: `.option ptran_nodeset=...` and the **pattern-based
  `.nodeset` block** (`v(X1.ml*_a)=vdd_value`, `sl*`, `bl*`, `Q*/QN*/Z*/ZN*`, ...).
  These are wildcard node-name conventions with fixed vdd/vss values — methodology,
  reproducible verbatim, **not** per-cell derived. Presence/content varies per
  cluster (delay has none; mpw has the full block) — captured by mining.
- **which-cycle-measured / precycle structure**: encoded by `cross=N` in the
  measures and the `t0x` timing points
- the optimization block (`opt_init/lb/ub`, `constr_pin_offset`, `OPT1(...)`,
  optmod) for Family 2
- the `.options` line, the `.meas` statements, the `.tran` command
- THANOS/opt header comments that drive constraint search; `$PUSHOUT_PER` as a
  fixed constant (default `0.4`)

It does **not** own (Phase B / collateral):
- **collateral/config**: the waveform `.inc` files (two by default: a `std_wv*`
  and `$WAVEFORM_FILE`) and the hardcoded `/CAD/...` path (must become a
  config/collateral placeholder for airgap), model `.inc`, netlist `.inc`, corner
  (`vdd/temp`), load (`cl`)
- the `X1 $NETLIST_PINS $CELL_NAME` instance (pin order from collateral)
- the **per-arc static WHEN / side-pin biases** filled into the "Unspecified pins"
  / "Pin definitions" section — this is the engine-derived sensitization seam, the
  only genuinely cell/arc-specific structural piece, and it stays in Phase B.

Note: the pattern-based nodeset assumes N2P naming conventions. Reproducing it is
correct for Phase A (methodology parity). Letting the engine *derive* a nodeset
when names do not match a cluster is a later refinement, not Phase A.

### Out of scope (later phases)

- **Phase B**: wiring real collateral into `stage4`, the combinational stimulus
  path, generalizing `stage4` beyond hold/P2, validating sequential hold, calling
  `emit()` in place of pass-through.
- **Phase C**: LSF orchestration, monitoring, coverage report.
- No timing-value extraction / `.lib` assembly (downstream `Lib-Char-Certi`).
- No ML runtime prediction.

## Data model — `config/measurement_grammar.json`

```jsonc
{
  "version": 1,
  "source_corpus": "templates/N2P_v1.0",      // provenance of this grammar
  "generated_from": ["delay", "mpw"],          // arc-type families present
  "entries": [
    {
      "key": {                                 // cluster identity (match target)
        "family": "simple_edge",               // simple_edge | constraint_opt
        "arc_type": "delay",
        "rel_dir": "rise",
        "probe_dir": "fall",
        "cluster_tag": "common_inpin",         // nodeset/structure family tag
        "features": []                          // extra discriminators if needed
      },
      "placeholders": ["$REL_PIN", "$PROBE_PIN_1", "$CONSTR_PIN", "$VDD_VALUE",
                       "$INDEX_1_VALUE", "$INDEX_2_VALUE", "$MAX_SLEW",
                       "$PUSHOUT_PER"],
      // recipe_lines spans the WHOLE methodology body, ordered & verbatim:
      // .options -> waveform-timestamp params -> (optimization block) ->
      // .option ptran_nodeset + .nodeset block -> toggling sources -> .meas -> .tran
      "recipe_lines": [
        ".options runlvl=6 ... sampling_method=lhs",
        ".param max_slew = '$MAX_SLEW'",
        ".option ptran_nodeset=1", ".nodeset v(X1.ml*_a) = 'vdd_value'", "...",
        "XV$REL_PIN $REL_PIN 0 stdvs_mpw_fall_rise_fall_rise VDD='vdd_value' ...",
        ".meas cp2q_del1 trig v($REL_PIN) val='vdd_value/2' cross=4 targ v($PROBE_PIN_1) ...",
        ".tran 1p 50u sweep monte=1"
      ],
      "provenance": ["template_common_inpin_rise_delay_fall.sp"]
    }
  ]
}
```

- An entry is reproducible: `emit()` fills `recipe_lines` placeholders → exact
  original region.
- Two templates with byte-identical templatized recipes collapse to one entry
  (provenance lists both). The entry count = number of distinct recipes, which is
  the real measure of grammar size.

## Key interfaces

```python
# core/measurement/mine.py
def mine(template_dir: str) -> dict        # -> grammar dict (also writes json via CLI)
def validate(template_dir: str, grammar: dict) -> ValidationReport
# CLI:  python -m core.measurement.mine mine    <dir> -o config/measurement_grammar.json
#       python -m core.measurement.mine validate <dir> -g config/measurement_grammar.json

# core/measurement/emit.py
def load_grammar(path: str = DEFAULT) -> dict

def select_entry(grammar, *, arc_type, rel_dir, constr_dir, probe_dir,
                 cluster_tag=None) -> dict
    # Picks the grammar entry. In Phase A round-trip, cluster_tag comes from the
    # template's own provenance (we know which template -> which recipe), so
    # selection is exact. The general cell -> cluster mapping for a brand-new cell
    # is **Phase B** (it will use the engine's structural features -- CCC:
    # combinational? master/slave latch? -- or the existing 854 selection rules).
    # Typed no-match error lists tried keys + closest entries (repo "never fail
    # silently" rule).

def emit(entry, arc_info, *, fill_values=False) -> list[str]
    # Returns the recipe lines for one arc. By default fills only the ARC-IDENTITY
    # placeholders ($REL_PIN/$CONSTR_PIN/$PROBE_PIN_1) and LEAVES corner/slew/load
    # placeholders ($VDD_VALUE/$INDEX_*_VALUE/$MAX_SLEW) intact, so the EXISTING
    # deck_builder $-substitution fills them -- no duplicated substitution logic.
    # fill_values=True resolves everything from arc_info for standalone use/tests.
    # $PUSHOUT_PER defaults to '0.4' (fixed three-party constant) unless overridden.

# Signature double-check (your point 2): selection keys on (arc_type, dirs,
# cluster_tag); value substitution is delegated, not re-implemented. This is the
# refinement vs the first draft's single all-params emit().
```

## Templatization (miner internals)

For each template, in the recipe region, substitute concrete -> placeholder using
the arc's known pin set and corner/index values (available from the template's own
`.param` lines and the cell pin list):

1. Read `.param vdd_value`, `cl`, slew params, `max_slew`, `$PUSHOUT_PER` markers.
2. Replace whole-token pin occurrences (`v(CP)` -> `v($REL_PIN)`, etc.) using the
   arc's rel/constr/probe pins parsed from the filename + header.
3. Replace numeric corner/load/slew literals with their `$..._VALUE` placeholder.
4. Leave structural constants (`vdd_value/2`, `cross=4`, `td=...`) intact.

Round-trip is the correctness oracle: if templatize->emit does not reproduce the
original byte-for-byte, that template is reported, not silently approximated.

## Testing strategy

- **Local (dev):** unit tests on `templates/N2P_v1.0/{delay,mpw}` — miner produces
  a grammar, emitter reproduces every local template's recipe region byte-exact
  (round-trip == 100% on the local corpus). Edge cases: rise/fall variants,
  Family-2 optimization block, multi-`cross` measures.
- **Airgap (real):** operator points `mine`/`validate` at the full hold+delay
  corpus; round-trip coverage report must reach 100% (or list the exact
  uncovered templates to extend the templatizer). No code change needed to run —
  only the corpus path differs.
- ASCII guard: `grep -rPn '[\x80-\xff]'` over new `.py`/`.json` must be empty.

## Success criteria

1. `mine` over the local delay+mpw corpus emits `measurement_grammar.json`.
2. `validate` reports **100% byte-exact round-trip** over the local corpus.
3. `emit(...)` returns the correct recipe for a delay arc and an mpw/hold arc
   given pins/dirs/params, with a typed error on no-match.
4. The whole thing is stdlib-only, ASCII-only, and runs unchanged when pointed at
   the airgap full corpus (the validate report is the comprehensiveness proof).
5. Clean seam (`emit`) ready for Phase B `stage4` to call.

## Resolved during review (2026-06-28)

- **Init is recipe, not engine-derived.** The `.option ptran_nodeset` + pattern
  `.nodeset` block, precycle/cycle structure, and special syntax live in the
  grammar (reproduced verbatim). Only the per-arc WHEN/side-pin biases stay
  engine-derived (Phase B).
- **Toggling sources:** the model *name* is in the grammar (keyed by family+dirs);
  the waveform `.inc` files are collateral (two by default), the `/CAD/...` path
  becomes a config placeholder for airgap.
- **`pushout_per` fixed `0.4`** (three-party constant); **`max_slew` wiring is
  family-specific** and captured per cluster.
- **emit() signature** split into `select_entry` + `emit`; value substitution is
  delegated to the existing `deck_builder`, not re-implemented.

## Open questions (resolve during planning, not blocking)

- Exact cluster `key` discriminators beyond (family, arc_type, dirs, cluster_tag)
  — decided empirically: start minimal, let round-trip mismatches reveal needed
  features.
- The general **cell -> cluster** selection (for a brand-new cell with no template)
  is **Phase B**; Phase A round-trip selects by template provenance. Confirm in
  planning that Phase A's `select_entry` exposes the seam cleanly without
  implementing the Phase B mapping.
