# Combinational Deck Recipe: teardown + programmatic generator (Design)

**Status:** DRAFT -- awaiting review. Spec first, then implement test-first
(superpowers workflow). One logical step per turn; this is Step 1.
**Branch:** child of `feat/phase-2c-charge-resolve` (`claude/lucid-noether-cat8lr`).
**Purpose:** stop depending on a folder of per-design `template_*.sp` files.
Instead, **gather every piece of a combinational FMC deck from the collaterals
and assemble it with one programmatic generator whose recipe is codified, readable
and questionable** -- so the team can learn MCQC's design method, challenge it, and
improve it on data, not faith. Combinational first (no initialization needed).
**Validation:** generate BOTH ways (legacy template substitution + the new
generator) and diff byte-for-byte; keep MCQC parity as the default. Cross-validate,
then retire the templates.

**Constraints (FIXED, from owner discussion):**
- `tt_out` and the `.meas` measurement semantics are FIXED by the char flow
  (Liberate / char.tcl); reproduce MCQC exactly -- NOT a tunable.
- index point-set / sweep packaging / num_samples / `.options` are configurable
  recipe knobs, DEFAULT = MCQC; any change is a divergence to validate by DATA
  (wall-clock + `.meas` delta vs MCQC), not by assumption.
- MCQC parity first (generator must reproduce the template deck byte-for-byte),
  divergence second.
- Name-invariant (proven for the template path; must hold for the generator).
- Repo rules: ASCII source; never weaken a test assertion; never drop an arc;
  signed commits.

---

## 1. Teardown -- where every line of a combinational deck comes from

Mapped against the real N2P references (OAI2220 / MUX4 / BUFFND, ssgnp_0p450v_m40c).
"Source": COLLATERAL (template.tcl / char.tcl / corner / netlist) vs CONVENTION
(MCQC recipe -- the part that is not a fact about the cell).

| deck section | content | source | engine-derivable | questionable / configurable |
|--------------|---------|--------|------------------|-----------------------------|
| header `* CELL ...` | provenance metadata | collateral + arc | n/a | redundant fields; cosmetic |
| `.options RUNLVL=6 ... gmindc/gmin=1e-15 autostop` | HSPICE accuracy/convergence | CONVENTION | no | RUNLVL tier vs speed -- KNOB (default MCQC) |
| `.option sampling_method=lhs` / `.save level=none` | Monte sampling / no OP save | CONVENTION | no | keep |
| `.inc waveform / model / netlist` | std_wv + corner model + LPE netlist | COLLATERAL (corner/netlist) | no | none |
| `.param vdd_value/vss_value/.temp` | PT | COLLATERAL (corner) | no | none |
| `.param cl=$INDEX_2 / rel_pin_slew=$INDEX_1` | one (slew,load) point | COLLATERAL (template.tcl index) | no | ONE deck = ONE point -> 5x5 = 25 decks/arc -- KNOB (point-set + packaging) |
| `VVDD/VVSS/VVPP/VVBB` | rails (VPP=vdd, VBB=vss) | netlist rails + CONVENTION | partly | body=rails for this PDK |
| `C<out> <out> 0 'cl'` | output load | netlist output + CONVENTION | yes (output pin) | multi-output cells |
| `X1 <pins> <cell>` | subckt instance | COLLATERAL (netlist .subckt) | yes | none |
| `.param max_slew / related_pin_t01=200ns` | input-edge timing | CONVENTION | no | magic 200ns; parameterize |
| side pins `V<pin> 'vdd/vss_value'` | hold non-measured inputs (WHEN) | COLLATERAL (template.tcl WHEN) | YES (P1 Boolean diff) | WHEN copied vs ENGINE-derived/verified -- KNOB |
| toggling `XV<in> stdvs_<dir> ... t01` | single input edge | arc + CONVENTION (stdvs) | input pin yes | waveform model is convention |
| `.meas meas_delay` (in->out @ vdd/2, cross=1) | 50% prop delay | CONVENTION (char semantics) | no | FIXED by char flow |
| `.meas half_tt_out 30->70 ; meas_tt_out=*2` | output slew | CONVENTION (char semantics) | no | **FIXED -- char.tcl/Liberate, do NOT change** |
| `.tran 1p 5000n sweep monte=1` (->monte=N) | sim window + Monte | CONVENTION | no | window bounded by `autostop`; num_samples + packaging -- KNOB |

**Reading of the table.** Only the netlist/structure rows are engine-derivable;
the **side-pin sensitization is the one place the engine genuinely adds value**
(derive + verify the WHEN). Everything else is either COLLATERAL (PT, index,
includes, pins) or a fixed CONVENTION (options/meas/tran/waveform). So the
"generator" gathers COLLATERAL + a codified CONVENTION recipe; it does not invent
physics it cannot know.

## 2. HSPICE notes that shape the knobs (from owner discussion)

- **25->1 index packaging.** Possible for combinational only (no `OPT1`
  optimizer): one deck with a `.DATA` block of the (slew,load) pairs and
  `.tran ... SWEEP DATA=idx SWEEP MONTE=N`. BUT FMC cost is dominated by
  samples x points SOLVES; merging decks saves only per-invocation OVERHEAD
  (parse / model-load / license / farm scheduling) -- modest under heavy Monte.
  The big lever is the POINT-SET (e.g. 3 of 25 -> ~8x fewer solves) which trades
  coverage/interpolation accuracy. Therefore: point-set, packaging and
  num_samples are KNOBS; the decision is made by MEASUREMENT (Step 6), not here.
  Choosing a 3-point subset is trivially supported (a 3-row `.DATA`, or 3 decks).
- **`.meas` / tt_out.** FIXED by the char flow; the recipe reproduces MCQC's exact
  `.meas` lines. char.tcl supplies the degrade % (`constraint_delay_degrade` ->
  PUSHOUT_PER) and which outputs; it does NOT supply raw HSPICE `.meas` syntax --
  that stays in the codified recipe, reproducing the char-flow semantics exactly.
- **`.options`.** Configurable, default = MCQC. Lowering RUNLVL can speed up but
  drifts `.meas` VALUES -> can fail the MCQC diff. So an options change must be
  validated against MCQC VALUES (not just wall-clock).

## 3. Generator design

`core/deck_recipe.py` (new), stdlib only, ASCII:

```
@dataclass
class RecipeOpts:
    index_points: str = "all"        # "all" | "first" | explicit list of (i1,i2)
    index_packaging: str = "per_point"   # "per_point" | "data_sweep"
    num_samples: int = 5000
    options: str = MCQC_OPTIONS      # the exact default string; overridable
    when_source: str = "collateral"  # "collateral" | "engine"
    # tt_out / .meas are NOT here -- fixed.

def build_combinational_deck(arc_info, opts=RecipeOpts()) -> list[str]:
    # assembles the deck section by section from arc_info (the resolved collateral
    # bundle the resolver already produces) + opts. One small function per
    # section, each with a docstring stating WHAT it emits, WHY (MCQC rationale),
    # and its SOURCE (collateral field or convention).
```

Section functions mirror the teardown rows: `_header`, `_options`, `_includes`,
`_lib_params`, `_slew_load`, `_voltage`, `_output_load`, `_subckt`,
`_timestamps`, `_side_pins`, `_toggling`, `_measurements`, `_tran`. The generator
consumes the SAME `arc_info` dict the existing resolver/deck_builder already
produces (CELL_NAME, REL_PIN/dir, PROBE_PIN_1, NETLIST_PINS, INDEX_1/2_VALUE,
WHEN, VDD_VALUE, TEMPERATURE, includes, PUSHOUT_PER, ...), so no new collateral
plumbing is needed -- only a different ASSEMBLER.

Default `RecipeOpts()` MUST reproduce the template-substitution deck exactly.

## 4. Cross-validation (the whole point)

- `tests/test_deck_recipe_parity.py`: for the DFFQ1 combinational arc and each of
  the 4 directions, assert `build_combinational_deck(info)` (default opts) is
  **byte-identical** to the legacy template-substitution deck. This proves the
  generator codifies the SAME recipe.
- Rename-invariance: the generator deck is name-invariant (reuse the proven
  method).
- Diff harness: extend `tools/batch_report.py` (or a new `tools/deck_diff.py`)
  with `--method template|generator|both`; in `both`, generate each arc both ways,
  diff, and surface any mismatch in the report. A test asserts zero diff on the
  real arcs.

## 5. Phasing (after approval; one step per turn, test-first)

1. (this doc) teardown + design -- review.
2. `core/deck_recipe.py` with default-MCQC recipe + byte-parity test vs templates.
3. Diff harness (`--method both`) + zero-diff test; report shows the comparison.
4. (optional) `when_source="engine"`: P1-derived side-pins + verify vs collateral
   WHEN, mismatches flagged.
5. Retire templates once the generator matches across the real cell set (templates
   kept behind a flag for comparison).
6. Benchmark harness (runs on the team's HSPICE box): per-knob wall-clock +
   `.meas` delta vs MCQC, so point-set / packaging / num_samples / options are
   decided on data. tt_out stays fixed.

## 6. Tests / scope / honesty

- Parity tests gate every step; existing 489 pass unchanged.
- Out of scope: sequential init / worst-case (combinational needs none);
  constraint-arc (MPW/hold) recipe (has the `OPT1` optimizer -- a separate later
  spec); HSPICE execution (no simulator here -- the team runs decks + benchmark).
- ASCII clean; signed commits.

## 7. Open items for the reviewer

1. Generator location: `core/deck_recipe.py` (deck-gen side) -- agree? (engine
   only enters via the optional `when_source="engine"` bridge.)
2. Diff harness: extend `batch_report.py` vs a dedicated `deck_diff.py`?
3. Step 4 (engine-derived WHEN) priority: right after parity, or after templates
   are retired?
