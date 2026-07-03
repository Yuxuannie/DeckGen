# --force-bias PIN=VAL: Demo Override for the Verify Layer (Design)

**Status:** approved scope (requirements fixed by Yuxuan); implement immediately after
spec commit
**Branch:** feat/phase-2b-engine
**Purpose:** live demo of the verify layer catching a wrong side-pin bias: force SE=1
on the scan-DFF hold(CP,D) arc and watch P1 FAIL with a derivation that names the SI
capture path.
**Constraints (FIXED):** override is a constraint INSIDE Stage 2's search space, not a
post-hoc edit; forced value flows to the assembled Stage 4 deck; verdict marks the bias
FORCED; stdlib only; changes confined to `engine/run.py`, `engine/stages/
stage2_sensitize.py`, and verdict plumbing; small diff.

---

## 1. CLI (`engine/run.py`)

```
python3 -m engine.run --netlist SDFX.spi --force-bias SE=1 [--force-bias SI=0] ...
```

- `--force-bias` is repeatable (`action="append"`, metavar `PIN=VAL`); a module-level
  helper `parse_force_bias(items) -> dict[str, int]` validates each item: exactly one
  `=`, VAL in `{0, 1}`; bad syntax -> `argparse` error naming the offending item.
- The parsed dict is injected as `record["force_bias"]` in BOTH paths:
  - direct path: `_direct(...)` gains a `force_bias` parameter, added to the record it
    builds;
  - config/fixture path: when the flag is present, `run.py` reads the four artifacts
    itself (`da.read_arc`/`read_netlist`/`read_measurement_block`/`read_model` -- the
    same four lines `run_pipeline` performs), injects `force_bias`, and calls
    `run_pipeline_src`. `engine/pipeline.py` stays untouched (it is outside the
    allowed-change set); the 4-line duplication is the price and is acceptable.
- Transport into Stage 2: `Arc.from_record` already copies the whole record into
  `Arc.raw`, so Stage 2 reads `arc.raw.get("force_bias")`. No `engine/types.py` change.

## 2. Stage 2: forced assignment inside the search (`stage2_sensitize.py`)

`derive()` reads `forced = dict(arc.raw.get("force_bias") or {})`. Changes:

1. **Validation.** Any forced pin not in `sides` (it is the rel/constr pin, a rail, or
   unknown) -> `ValueError` listing the valid side pins. A forced rel/constr pin is
   not a bias, it is a different arc; failing loudly beats a silently ignored flag in
   a live demo.
2. **Constrained enumeration** (the heart -- NOT a post-hoc result edit):

   ```python
   choices = [(forced[s],) if s in forced else (0, 1) for s in sides]
   for vals in product(*choices):
   ```

   The search space simply no longer contains assignments that violate the override;
   everything downstream (controls test, masked classification, obligation text) is
   genuinely derived under that constraint.
3. **FORCED marking.** After classification (both the found and not-found branches),
   every forced pin's entry is overwritten:
   `side_biases[s] = Derivation(forced[s], "FORCED by user, overriding derivation",
   STAGE)`. Stage 5's existing P1 detail line (`bias SE : 1  <= FORCED by user,
   overriding derivation`) makes the screenshot self-explanatory with ZERO verdict
   changes.
4. **Competing-path diagnostic (FAIL branch, only when `forced` is non-empty).**
   `controls_D(cp, a)` is generalized to `controls(cp, a, pin)` (same body, toggled
   pin as a parameter; `controls_D` becomes `controls(cp, a, constr)`). When the
   constrained search proves nothing, enumerate the free sides under the forced
   assignment and collect the side pins for which `controls(cp, a, s)` holds -- the
   capture paths that are LIVE instead of D. The obligation becomes:

   ```
   no static side-pin bias makes D control capture under FORCED {SE=1}
   (searched sides=['SE', 'SI'], both clock phases); competing path LIVE:
   ['SI'] controls capture instead
   ```

   This is derived (it is the same Boolean-difference test, pointed at the other
   pins), not templated text.

## 3. Flow-through to Stage 4 (no stage4 changes)

`stage4_deckgen.assemble` already emits one `V<pin>` source per `sens.side_biases`
entry. A forced pin carries its forced value even in the FAIL branch (the other,
unproven sides keep value `None` -> existing `vss_value` rendering), so the bad deck is
assembled exactly as the demo needs; `--deck` prints it, and a later simulation can
show the garbage measurement.

## 4. Tests (`tests/engine/test_force_bias.py`)

On the engine scan-DFF fixture (`SDFX_LPE_PLACEHOLDER`, the DFFQ1-class flop), arc
hold(CP, D), same `_setup()` pattern as `test_sensitize.py`:

1. `force SE=1` -> `sens.proven is False`; `"SI"` in `sens.p1_obligation`; `"FORCED"`
   in `side_biases["SE"].reason`; `side_biases["SE"].value == 1`.
2. `force SE=0` (equal to derived) -> `sens.proven is True`; SE marked FORCED; SI
   still derived masked with value 1 (forcing is orthogonal to correctness).
3. `force ZZ=1` -> `ValueError` naming the valid side pins.
4. `parse_force_bias(["SE=1", "SI=0"]) == {"SE": 1, "SI": 0}`; `"SE=2"` and `"SE"`
   rejected.
5. End-to-end: `run_pipeline_src` with `record["force_bias"] = {"SE": 1}` -> verdict
   P1 status FAIL and a detail line containing `FORCED`.

Existing tests must pass unchanged (no assertion edits). Non-ASCII scan empty.
