# Prove the Worst-Case INITIALIZATION (state), reached via toggle timing (Design)

**Status:** DRAFT -- awaiting review. No code until approved (superpowers: spec
first, then test-first). One logical step per turn; this is Step 1.
**Branch:** child of `feat/phase-2c-charge-resolve`
**Supersedes:** `2c_verify_worstcase.md` (removed). That draft swept the wrong
axis -- it treated the side-pin TIMING offset as the objective. The corrected
axis below is: the objective is the worst-case prior STATE; timing is only the
operating knob that reaches it.
**Demo cell:** `SDFSYNC4RPQSXGMZD1BWP130HPNPN3P48CPD` (scan-DFF, 4-stage
synchronizer; pins CD/CP/D/SE/SI/Q), N2P v1.0, corner
`ssgnp_0p450v_m40c_cworst_CCworst_T`. Static derivation already correct in the
Topology tab: P1 PASS; side-pin bias CD=0/SE=0/SI=1; 39 CCC with storage mapping
master/stage1..6/slave; S0-S5 stage trace.
**Arc (from the live emitted deck):** REL_PIN = CD, CONSTR_PIN = CD, PROBE = Q1,
WHEN = CP&D&SE&SI (side pins held high at 0.450). This is an async-clear
min-pulse-width (MPW) arc: CD pulses (`stdvs_mpw_rise_fall_rise_fall`, shaped by
`related_pin_t01..t04`); `.meas cp2q_dell trig v(CD) cross=3 targ v(Q1) cross=1`.

A naming note kept from the live deck: the measurement is literally
`.meas cp2q_dell` here (header `OPT_RESULTS | cp2q_dell`). This spec uses
`cp2q_dell` to match the emitted deck. No measure name is renamed to fit.

---

## 1. The axis (normative -- read before anything else)

- **Sensitization (P1) is FIXED.** CD=0/SE=0/SI=1; the capture/propagation path
  is the same in every case considered here. We do not search over biases.
- **The operating variable is toggle TIMING** -- `related_pin_t01..t04`, which
  shape the `stdvs_mpw_...` CD waveform. This is the only knob the deck sweeps,
  and the only knob a hand-built deck varies.
- **The physical objective is the prior STATE** of the synchronizer's internal
  storage nodes when the measured CD edge arrives. Different toggle timing drives
  the chain into different prior states; the prior state is what sets `cp2q_dell`.
- **`cp2q_dell` is the measured degrade.** Worst = max `cp2q_dell`.
- **`.nodeset` in the deck is a convergence SEED, not a forced `.ic`.** It nudges
  hspice's DC starting point; it does NOT pin the state. The realized state is set
  by the excitation (the CD waveform + held side pins). Prong (a) below DOES use
  `.ic` to force a state -- that is a deliberate, separate mechanism, clearly
  distinguished from the seed.

So: operating variable = toggle timing [what the deck sweeps]; physical objective
= the prior state that maximizes `cp2q_dell` [what we prove]; `cp2q_dell` = the
ranking metric.

## 2. The search space is SMALL -- derive it, do not hardcode, do not 2^N

The free degrees of freedom are NOT every internal node. From the CCC storage
mapping already produced by `engine/stages/stage1_ccc.py`
(`CCCResult.state_nodes`, each `StateNode` carrying `.net` and `.role` in
{master, stage1..6, slave}), apply these structural rules:

1. **Each cross-coupled storage element = ONE free bit, not two.** A storage core
   is a feedback SCC whose members hold complementary values (`stage1_ccc` already
   identifies the >=2 gate-controlling members of each core). The complementary
   constraint collapses the pair to a single bit `s_k in {0, 1}` for storage
   element `k`. (Test in Step 2 asserts this collapse.)
2. **The element being written by the current event is FIXED, not free.** For this
   async-clear arc the CD pulse drives a reset value into the elements it clears;
   those are determined by CD, not free.
3. **Elements held steady by the P1 bias are FIXED.** With CP/D/SE/SI held at the
   WHEN condition, the latch transparency configuration pins some elements to a
   determined value (e.g. a stage whose input is statically driven). Those are not
   free.
4. **FREE bits = the prior values held by the synchronizer stages NOT touched by
   the current event and NOT pinned by the held side pins** -- i.e. the
   un-cleared, un-driven mid-chain stages that merely remember their prior content
   when the CD edge arrives.

Expected result for this cell: a handful of free bits (anticipate ~2-4), each a
named storage element from the mapping, enumerable as `2^(free bits)` discrete
prior states -- a small set, not the 8-element / 256-state naive space.

**Honesty about node names (Step 2 will lock these down).** The exact free-bit
node set must be COMPUTED by running `stage1_ccc` on the real LPE netlist (ground
truth). That netlist is server-side (collateral path in the live deck) and is not
in this repo; the repo's `SDFX_LPE_PLACEHOLDER` fixture is a single-stage DFF
(master `ml` + slave `sl`), useful for unit-testing the derivation rules but not
the 8-element chain. Therefore:
- this spec states the RULES (1-4) and the EXPECTED shape (a handful of free
  bits from master/stage1..6/slave);
- Step 2 implements `free_prior_states(ccc, arc, sens) -> FreeStateSet` and its
  test asserts, on the placeholder, that master+slave collapse to the right
  free/fixed split; the concrete sync-cell list is filled in (and audited) when
  the derivation runs on the live netlist.
This is not hand-waving the requirement: the free set is DERIVED from structure
every run; the spec simply cannot transcribe node names from a netlist it cannot
read.

## 3. Prong (a) -- DIRECT state enumeration (the true physical worst case)

For each discrete free prior-state `s` in the derived set:
- emit a deck variant that FORCES that state with `.ic v(<node>)=<rail>` on the
  storage nodes of the free elements (each pair set complementary), on top of the
  operating measurement deck (held side pins, CD waveform, `.meas cp2q_dell`);
- run hspice (via `run_p2` or a sibling helper) and read `cp2q_dell`;
- collect `(state -> cp2q_dell)`; `argmax` = the TRUE physical worst state.

`.ic` here is the deliberate state-forcing mechanism (SS1) -- distinct from the
deck's `.nodeset` seed. The forced state must respect the complementary and
fixed-bit constraints from SS2 (we force only the free elements; fixed elements
keep their determined value). A run whose `.meas cp2q_dell` fails to converge
yields a `None` entry that is RETAINED and flagged, never dropped (CLAUDE.md).

## 4. Prong (b) -- TIMING reachability (can the operating deck reach it?)

With the OPERATING deck (real emitted MPW deck: `related_pin_t0x` sweep, the
`.nodeset` seed as-is, NO `.ic`):
- sweep `related_pin_t0x` starting from the config offsets
  (`mpw` arc: t01..t04 = 10/20/50/50*max_slew (+constr_pin_offset), per
  `config/config.yaml`), refining per SS11 if needed;
- for each timing, read the settled internal state at the pre-CD-edge probe point
  (probe the free storage nodes, classify each to 0/1 by the existing `_bit`
  MARGIN rule) AND read `cp2q_dell`;
- record `(timing -> reached_state, cp2q_dell)`.

This shows WHICH timing drives the synchronizer into the worst state from (a), and
at which timing -- i.e. it confirms the operational deck can actually REACH the
worst case, and flags it if no single timing does.

## 5. Prong (c) -- COMPARE to the incumbent two-deck method

The incumbent hand method runs two timings and picks the worse `cp2q_dell`. We:
- take the two incumbent timings (the two `related_pin_t0x` choices a hand deck
  uses -- spec default: the two endpoints of the config offset range; confirm in
  SS11) and their worst `cp2q_dell`;
- compare to the TRUE worst from (a) and the swept worst from (b);
- if the true worst state is NOT reached by either incumbent timing, OR the swept
  worst (b) exceeds the two-timing worst, REPORT the gap. That gap is the central
  evidence that two decks do not guarantee the worst case. It is never hidden
  (SS10).

## 6. The verdict to emit

`stage5_verify.verify(..., sim_result=...)` consumes
`sim_result = {"p2": P2Result, "worststate": WorstStateResult}` (SS11 data
shapes). When present and green:
- P2 rendered by the EXISTING `p2_property` (initial state sim-confirmed);
- a worst-state block reports: worst prior STATE (named elements + bits), its
  `cp2q_dell`, the reaching TIMING, and the GAP vs the two-timing method;
- S5 status PASS only when statics green AND sim ran AND P2 passed.

S5 trace, sim present + green (illustrative):
```
S5 verify   : P2 PASS (sim-confirmed) | worst state {stageK=1,...}
              cp2q_dell=<v> reached@t0x=<...> | gap vs 2-deck=+<d> [RAN]
```
S5 trace, hspice absent (current behavior preserved):
```
S5 verify   : overall=STUB (no simulator) [STUB]
```
STUB still shows the full static derivation (free-state set + reasons) in the
cards -- the honest demo state, never a faked PASS (SS10).

## 7. Compute budget -- find cheap, confirm expensive (reviewer raised cost)

`cp2q_dell` comes from the FMC deck's `.tran 1p 50u sweep monte=1` -- one run is
EXPENSIVE. The incumbent pays for 2 such runs. Naive (a)+(b) would pay for
(free states) + (sweep points) full runs -- too many. Strategy:

- **Rank cheap, report expensive.** Prong (a) ranks the free states with a CHEAP
  variant (nominal, `monte` dropped and/or a shortened `.tran` window that still
  contains the CD edge and Q1 response) to find the argmax worst state. Only the
  WORST state then gets ONE full `monte=1 / 50u` run for the reported number.
  Same pattern for (b): cheap nominal sweep to locate the reaching timing, one
  full run to confirm.
- The audit record marks each number's fidelity (nominal-rank vs monte-confirm);
  the two-fidelity distinction is stated, not hidden (SS10).
- Net budget target: a handful of cheap runs + ~1-2 full runs -- at or below the
  incumbent's 2 full runs, while proving more points.

Default offered for review; the reviewer may raise/lower the confirm-run count
(SS11).

## 8. Honest scope (in the spec, not papered over)

- **Needs hspice.** `hspice` is NOT on PATH in this CI/container (verified). The
  honest state here is STUB WITH the full derivation shown -- never a faked PASS.
  Sim tests SKIP with a clear reason; tolerances are never weakened to go green.
- **t=0 state selection only.** This proves the worst INITIAL state; the FMC
  `.tran` computes the dynamics from it. Not a transient RC simulator.
- **Unreachable-by-single-timing is still valid evidence.** If the true worst
  state (a) is reachable only by a SEQUENCE of edges, not any single timing, SAY
  so -- it remains valid evidence about the incumbent method's blind spot (SS5).
- **Offline CI.** As `test_p2_sim.py` already does, prong tests accept
  pre-captured `.mt0` fixtures so the logic (free-state derivation, enumeration
  argmax, table completeness, degrade math, verdict mapping) is covered with NO
  hspice; the hspice path is skip-guarded.

## 9. Data shapes (for Steps 2-6; listed now for review)

```
@dataclass
class FreeBit:
    element: str            # storage role/id, e.g. "stage3"
    nodes: List[str]        # the cross-coupled member nets (>=2)
    reason: str             # why free (structural basis)

@dataclass
class FreeStateSet:
    free: List[FreeBit]                 # the handful of free bits
    fixed: Dict[str, int]               # element -> determined bit, with reason
    fixed_reason: Dict[str, str]
    def states(self) -> List[Dict[str, int]]: ...   # 2^len(free) assignments

@dataclass
class StateRow:
    state: Dict[str, int]               # element -> bit
    cp2q_dell: Optional[float]          # None if .meas failed -> flagged, kept
    fidelity: str                       # "nominal" | "monte"

@dataclass
class TimingRow:
    t0x: Dict[str, str]                 # related_pin_t0x values used
    reached_state: Dict[str, int]
    cp2q_dell: Optional[float]
    fidelity: str

@dataclass
class WorstStateResult:
    ran: bool
    free: FreeStateSet
    state_table: List[StateRow]         # prong (a), complete over free set
    worst_state: Optional[Dict[str, int]]
    worst_cp2q_dell: Optional[float]
    timing_table: List[TimingRow]       # prong (b)
    reaching_t0x: Optional[Dict[str, str]]
    reachable: bool                     # worst state reached by some single timing?
    incumbent_worst: Optional[float]    # prong (c) two-timing worst
    gap_abs: Optional[float]            # true/swept worst - incumbent worst
    gap_note: str
    note: str
```

## 10. Auditability (the point of the demo)

The verdict must let a reviewer who cannot see inside the cell read WHY a state is
worst. It carries:
- the derived FREE-state set (each free bit's nodes + structural reason; each
  fixed bit's value + reason) -- SS2;
- the `(state -> cp2q_dell)` table over the full free set -- SS3;
- the worst STATE + its charge/structural basis;
- the reaching TIMING (or the unreachable flag) -- SS4;
- the comparison GAP vs the two-timing method -- SS5.
Step 6's test asserts the audit record holds all of these.

## 11. Module / wiring plan + open decisions (for review; no code this step)

Plan:
- NEW `engine/worststate.py`: `free_prior_states(ccc, arc, sens) -> FreeStateSet`
  (Step 2); `enumerate_states(...) -> [StateRow]` emitting `.ic` decks (Step 3);
  `sweep_timing(...) -> [TimingRow]` over the operating deck (Step 4);
  `compare_incumbent(...) -> (incumbent_worst, gap)` (Step 5). `mt0_paths` hooks
  let CI evaluate pre-captured runs with no hspice.
- `engine/p2_deck.py` (or a sibling): add an `.ic`-forcing emit path for prong (a),
  distinct from the `.nodeset` seed, plus a settle-point state readout for (b).
- `engine/stages/stage5_verify.py:verify(...)`: consume the `sim_result` payload,
  extend the verdict + S5 trace; STUB path unchanged; reuse `p2_property` verbatim.
- `core/engine_present.py:topology_view(...)`: when hspice available, run
  (a)+(b)+(c), pass `sim_result` into `verify`, surface worst-state / reaching-
  timing / gap as structured JSON; hspice absent -> STUB cleanly (current).
- `gui.py:_engine_topology`: unchanged call site; render new fields if present.

Open decisions for the reviewer:
1. **Incumbent two timings (SS5).** Default = the two endpoints of the config
   offset range. Is that what the hand method actually uses, or two specific
   `related_pin_t0x` presets? (You know the team's real practice.)
2. **Confirm-run count (SS7).** Default = cheap rank + 1 full monte run at the
   worst state (and 1 at the reaching timing). Raise/lower?
3. **Cheap-rank fidelity (SS7).** Drop `monte` only, or also shorten `.tran`? If
   shortened, the window must still contain CD edge + Q1 response -- confirm
   acceptable.
4. **`.ic` granularity (SS3).** Force only the free storage nodes (recommended;
   fixed elements left to the excitation+seed) vs force the full derived state.

## 12. Test plan (Steps 2-6, test-first; listed for review)

1. **Free-state derivation (Step 2).** On the placeholder DFF: assert master+slave
   collapse to the right free/fixed split, cross-coupled pairs become one bit,
   captured/steady elements excluded. Structural, not a hardcoded list.
2. **Direct enumeration (Step 3).** With pre-captured `.mt0` per state: assert the
   `(state -> cp2q_dell)` table is complete over the free set, `None` rows flagged
   not dropped, and the worst state is the argmax. hspice path skip-guarded;
   tolerances not weakened.
3. **Timing reachability (Step 4).** Assert the `(timing -> state, cp2q_dell)`
   mapping is produced and the worst-state timing is identified, or flagged
   unreachable.
4. **Comparison + wiring (Step 5).** sim-present -> S5 PASS with worst state,
   reaching timing, gap; sim-absent -> STUB cleanly (no crash). Via `verify(...)`
   with a synthetic `sim_result` and with `None`.
5. **Audit (Step 6).** Assert the audit record holds the free set, the state
   table, the worst state + basis, the reaching timing, and the gap.

Existing tests pass unchanged (no assertion edits). Non-ASCII scan empty. Commits
gpg-signed.
