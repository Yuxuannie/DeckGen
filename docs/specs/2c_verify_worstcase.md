# Verify the Worst-Case Side-Pin Timing (Design)

**Status:** DRAFT -- awaiting review. No code until this is approved (superpowers:
spec first, then test-first). One logical step per turn; this document is Step 1.
**Branch:** child of `feat/phase-2c-charge-resolve`
**Demo target:** `SDFSYNC4RPQSXGMZD1BWP130HPNPN3P48CPD` (pins CD/CP/D/SE/SI/Q),
N2P v1.0 collateral, corner `ssgnp_0p450v_m40c_cworst_CCworst_T`,
arc `hold(CP rise, D fall)`.
**Goal:** close the verify/sim loop so the Topology stage trace ends with
`S5 verify = PASS` (not STUB), reporting (a) the P2 initial state CONFIRMED by
sim and (b) the worst-case side-pin timing offset with its measured `cp2q_del1`
degrade -- DERIVED from physics and CONFIRMED by sim, not guessed from two decks.

A note on naming: the prompts write `cp2q_dell`; the real measurement in the
sync4 template (line 95) is `.meas cp2q_del1`. This spec uses `cp2q_del1`
throughout and treats `cp2q_dell` as a typo for it. No assertion or measure name
is renamed to fit.

---

## 1. The problem the demo attacks

The incumbent method hand-builds two decks that differ in WHEN the static
side pins (CD/SE/SI) settle to their biased values relative to the capture clock
edge, simulates both, and PICKS THE WORSE `cp2q_del1`. The team does this because
they know side-pin settle time relative to the D-pin / capture edge can shift the
measured timing by 10%+. But two decks are two guessed points on a curve; they do
not PROVE the worst case -- a third offset between or beyond them can be worse and
go unseen.

The engine's claim: it (i) DERIVES the side-pin bias and the internal-node
initial state from charge/topology (already done -- P1 PASS, CD=0/SE=0/SI=1, the
S0-S5 trace), (ii) CONFIRMS that initial state against silicon differentially
(`run_p2`, already built), and (iii) PROVES the worst case by SWEEPING the
side-pin timing offset and reporting the offset that maximizes the degrade, with
the full curve retained. This document defines (ii)+(iii) wiring and (iii)'s
sweep.

## 2. What "side-pin timing offset" means here (normative)

Define `sidepin_offset` (ns) = the time by which the static side pins (the pins
in `sens.side_biases` -- here CD, SE, SI) reach their biased value BEFORE the
capture edge (CP cross=10 in the sync4 deck). It is realized as a delay on the
side-pin bias sources' transition into the held value:

- `sidepin_offset` LARGE  -> side pins settle long before capture -> least
  interference -> baseline (clean) `cp2q_del1`;
- `sidepin_offset` SMALL  -> side pins still settling near the capture edge ->
  maximal interference -> degraded (larger) `cp2q_del1`.

The capture path stays the P1-derived live path (D -> mux -> master -> slave ->
Q under bias CD=0/SE=0/SI=1); only the side-pin settle TIME moves. The scan path
(SI) stays masked. This is the one knob the two-deck method varies by hand.

Degrade is reported both ways:
```
degrade_abs(off)  = cp2q_del1(off) - cp2q_del1_baseline
degrade_pct(off)  = 100 * degrade_abs(off) / cp2q_del1_baseline
```
where `cp2q_del1_baseline` = the value at the LARGEST swept offset (cleanest).
WORST CASE = the offset maximizing `cp2q_del1` (equivalently `degrade_abs`).

## 3. The sweep set

Two-tier, so we can both reproduce the two-deck points AND show whether a finer
search finds a worse one:

1. **Discrete tier (primary).** Anchor offsets to the deck's own side-pin
   spacing. The sync4 template parameterizes the clock edges as multiples of
   `max_slew` (`related_pin_t01..t04 = 1/11/21/31 * max_slew`, line 62-65; the
   prompt's "10/20/50/50 * max_slew" is the equivalent golden_env spacing). The
   discrete sweep uses these same anchor multiples as candidate side-pin offsets:
   `offsets_discrete = {t01, t02, t03, t04}` expressed in ns. These are the
   points a hand-built deck would plausibly choose; the two-deck method is a
   2-element subset of this set.
2. **Refine tier (confirmation).** Take the discrete argmax `off*` and its two
   neighbors `[off_lo, off_hi]`, then do a finer linear sweep (N even sub-steps,
   spec default N=4) OR a 1-D bisection toward the local max across
   `[off_lo, off_hi]`. The refine tier exists to ANSWER the demo question: does a
   point between the discrete anchors degrade more than any anchor?

The returned worst case is the global argmax over `discrete UNION refine`. If the
refine tier's max exceeds the discrete tier's max by more than a reported epsilon
(default 1% of baseline), that DIVERGENCE is surfaced as the headline evidence
that the two-deck method can miss the worst case (HONEST SCOPE, SS6). It is never
hidden.

Monotonicity: `cp2q_del1` is expected to be monotone non-increasing in
`sidepin_offset` over the clean region (more settle time -> less interference),
with a single interference peak as the offset approaches the capture edge. The
sweep test (SS5) asserts the table is COMPLETE (one entry per swept offset, no
gaps, finite values) and that `argmax` is well-defined; it asserts monotonicity
only on the clean tail (offsets >= off*), not globally, because the peak is the
phenomenon we are hunting and must be allowed to exist.

## 4. The measured quantity and the deck it comes from

`cp2q_del1` comes from the FMC measurement deck for this arc/corner -- the sync4
template substituted with the golden collateral -- which already carries
`.meas cp2q_del1 ... cross=10 ... td='related_pin_t09'` (line 95) and
`.tran 1p 50u sweep monte=1` (line 100). The internal-node initialization stays
the emitted `.option ptran_nodeset=1` + `.nodeset v(X1.ml*_a)=vdd_value` /
`v(X1.bl*_ax)=vss_value` ... over the master/slave storage nodes (lines 74-90),
NOT a forced answer -- SS6 keeps the t=0 derivation honest.

Deck parameterization (decision, validated in Step 3 against the real template):
introduce a single sweep knob by templating the side-pin bias sources' settle
time on `.param sidepin_offset`, holding everything else (clock schedule, D
schedule, nodeset, measurement) fixed. One deck, one `.param`, run once per swept
offset; `cp2q_del1` parsed back from each `.mt0`. The Monte (`monte=1`) row is
read as the nominal corner point (consistent with how `run_p2` reads `.mt0`).

## 5. The verdict to emit

`stage5_verify.verify(...)` gains a `sim_result` payload (the existing signature
already takes `sim_result`; today it is ignored for P2). When present it carries:

- `p2`: a `sim.P2Result` (differential initial-state confirmation), rendered by
  the EXISTING `p2_property` -> `PStatus.PASS` iff statics green AND P2 ran AND
  passed; `PStatus.FAIL` iff it ran and failed; `PStatus.STUB` iff not run
  (no simulator) -- never PASS without a sim, never FAIL for "could not evaluate".
- `worstcase`: a new `WorstCaseResult` (SS7) -> a new `P5`-style detail block on
  the verdict (NOT a new P-number; it extends P2/P3 detail and the S5 trace line)
  reporting `worst offset = <off*> ns`, `cp2q_del1 = <v> (baseline <b>)`,
  `degrade = <abs> (<pct>%)`, and `refine vs discrete: <CONFIRMED | DIVERGES by
  <d>>`.

S5 trace line, sim present and green:
```
S5 verify   : P2 PASS (sim-confirmed) | worst side-pin offset=<off*>ns
              cp2q_del1=<v>ns degrade=<pct>% [RAN]
```
S5 trace line, hspice absent (current behavior preserved):
```
S5 verify   : overall=STUB (no simulator) [STUB]
```
STUB still shows the full static derivation in the cards -- the honest demo
state, never a faked PASS (SS6).

## 6. Honest scope (stated up front, not papered over)

- **Needs hspice in the demo env.** `hspice` is NOT on PATH in this CI/container
  (verified). There, the honest state is STUB WITH the full derivation shown.
  Tests that need a simulator SKIP with a clear reason (SS5); they never silently
  pass and never weaken a tolerance to go green.
- **t=0 + side-pin timing only.** This is worst-case initialization plus a
  side-pin settle-time sweep. It is NOT a transient RC simulator; the dynamics
  are the FMC `.tran` run's job.
- **Report divergence.** If the refine tier finds a worse offset than any
  discrete anchor, that is REPORTED as the strongest evidence the two-deck method
  can miss the worst case (SS3). Hiding it would defeat the demo.
- **Offline confirmation in CI.** As `test_p2_sim.py` already does, the sweep and
  P2 tests accept pre-captured `.mt0` fixtures so the logic (argmax, table
  completeness, degrade math, verdict mapping) is covered with NO hspice. The
  hspice-present path is exercised by a skip-guarded integration test.

## 7. Data shapes (for Step 3/4 implementation, listed now for review)

```
@dataclass
class WorstCaseRow:
    offset_ns: float
    cp2q_del1_ns: Optional[float]   # None if .meas failed -> row flagged, not dropped
    tier: str                       # "discrete" | "refine"

@dataclass
class WorstCaseResult:
    ran: bool
    rows: List[WorstCaseRow]                 # full audit table, every swept offset
    worst_offset_ns: Optional[float]
    worst_cp2q_del1_ns: Optional[float]
    baseline_cp2q_del1_ns: Optional[float]
    degrade_abs_ns: Optional[float]
    degrade_pct: Optional[float]
    diverges: bool                            # refine max > discrete max + epsilon
    divergence_note: str
    note: str                                 # why not-ran, if ran is False
```
A `None` `cp2q_del1` row is RETAINED and flagged (never silently dropped --
CLAUDE.md), and excluded from the argmax with a note.

## 8. Auditability (the point of the demo)

Every emitted verdict carries its derivation so a reviewer who cannot see inside
the cell can read WHY this is the worst case:

- side-pin bias (CD=0 / SE=0 / SI=1) WITH its charge/topology reason
  (`sens.side_biases[pin].reason`);
- internal-node initial states WITH their charge basis
  (`init.required_state[node].reason`);
- the worst-case offset `off*`;
- the full `(offset -> cp2q_del1, degrade)` table (every swept point);
- the refine-vs-discrete divergence verdict.

A test (Step 5) asserts the audit record contains all of these fields and that
the table is the complete swept set.

## 9. Module / wiring plan (for review; no code this step)

- NEW `engine/worstcase.py`: `sweep_sidepin(arc, sens, init, ccc, deck_src,
  workdir, offsets=None, hspice_cmd="hspice", mt0_paths=None) -> WorstCaseResult`.
  `mt0_paths` (offset -> .mt0) lets CI evaluate pre-captured runs (SS6) with no
  hspice. Builds one `.param sidepin_offset` deck per offset, runs/parses
  `cp2q_del1`, computes the table + argmax + divergence.
- `engine/stages/stage5_verify.py`: `verify(...)` consumes `sim_result =
  {"p2": P2Result, "worstcase": WorstCaseResult}` and extends the P2 detail +
  S5 trace; STUB path unchanged. The existing `p2_property` is reused verbatim.
- `core/engine_present.py:topology_view(...)`: when a corner/cell is analyzed and
  hspice is available, run `run_p2` + `sweep_sidepin`, pass `sim_result` into
  `verify`, surface `worst_offset_ns` / `degrade_pct` / the table as structured
  JSON fields. hspice absent -> STUB cleanly, never crash (current behavior).
- `gui.py:_engine_topology`: unchanged call site; renders the new structured
  fields if present.

## 10. Test plan (Steps 2-5, test-first; listed for review)

1. **Hand-calc / smallest-real gate (Step 2).** Drive `run_p2` on the sync cell
   (or smallest real stack): assert (a) non-STUB result when hspice is present;
   (b) the resolved internal-node initial states match a SPICE drive-and-settle
   (no forced `.nodeset`) within tolerance. hspice absent -> SKIP with reason.
   Tolerance is NOT weakened to pass.
2. **Sweep (Step 3).** With pre-captured `.mt0` fixtures (offset -> cp2q_del1),
   assert `sweep_sidepin` returns the max-degrade offset, the table is complete
   (one row per offset, no drops), `None`-measure rows are flagged not dropped,
   and the clean-tail monotonicity holds. A skip-guarded variant runs hspice.
3. **Wire verify (Step 4).** Assert sim-present -> P2 PASS + worst-case fields in
   the verdict/S5 trace; sim-absent -> STUB cleanly (no crash). Both via
   `verify(...)` directly with a synthetic `sim_result` and with `None`.
4. **Audit (Step 5).** Assert the audit record contains side-pin bias,
   internal-node initial states with charge basis, worst offset, and the full
   table.

Existing tests pass unchanged (no assertion edits -- CLAUDE.md). Non-ASCII scan
empty. Commits gpg-signed.

## 11. Open decisions for the reviewer

1. **Discrete anchor source.** Use the sync4 template's `related_pin_t01..t04`
   multiples (1/11/21/31 * max_slew) as the side-pin offset anchors, per SS3?
   (Alternative: golden_env `RELATED_T` 0/10/20/30 * max_slew.) Spec assumes the
   template values; flag if you want golden_env instead.
2. **Refine tier.** Linear N=4 sub-steps (simple, fully tabulated) vs 1-D
   bisection (fewer runs, less complete table). Spec defaults to linear N=4 for a
   complete, auditable table; bisection is the fallback if run time is a concern.
3. **Divergence epsilon.** Default 1% of baseline `cp2q_del1`. Adjust?
4. **Deck source for the sweep.** Sync4 FMC template (carries `cp2q_del1`) vs the
   engine's `p2_deck` (carries init probes only, no `cp2q_del1`). Spec chooses the
   FMC template; confirm the engine path can resolve that substituted deck for the
   Topology view, or whether the sweep should read a pre-generated deck path.
