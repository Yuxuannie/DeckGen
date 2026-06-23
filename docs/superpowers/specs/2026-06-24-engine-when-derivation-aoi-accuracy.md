# Engine WHEN-derivation accuracy on complex AND-OR-INVERT cells (Design)

**Status:** DRAFT -- awaiting review (/florin + /scld, then Yuxuan approval).
Spec first, then implement test-first (superpowers workflow). One logical step
per turn; this is Step 1.
**Branch:** `claude/lucid-noether-cat8lr`.
**Goal:** GOAL 2 (the highlight). Make the engine INDEPENDENTLY DERIVE -- from
netlist topology alone -- the side-pin sensitization of a combinational arc on
complex AND-OR-INVERT cells, expressed as a set of WHEN conditions, and VERIFY
that set against the cell's collateral WHEN (flagging divergence). Accuracy on
hard cells (AOI / OAI / deeper AND-OR) is the deliverable.

**Anchor (ground truth already in the repo, no new data):** PROJECT_NOTES.md
SS2.4/2.5 -- AIOI21 (`ZN = B * !(A1*A2)`): 10 delay arcs; A1, A2 unconditional;
B split into 3 WHEN by side-state; `A1&A2` blocked (hidden, not a timing arc).

---

## 0. Why the existing sensitizer is not enough

`engine/stages/stage2_sensitize.derive()` is a SEQUENTIAL/scan + select-mask
sensitizer. For a given arc it finds ONE static side-pin assignment under which
the measured pin controls a state-node capture, then classifies each side pin as
SET (required select) or MASKED (non-critical). It proves a single bias and
cross-checks `arc.when` (AGREE/DISAGREE). This is correct for flops, scan, and a
2:1 MUX, and is already tested.

It cannot express what an AOI/OAI arc needs:
- it derives ONE sensitizing assignment, not the FULL SET of side-pin states
  under which the related pin controls the output;
- it has no notion of a BLOCKED side-state (a state where the related pin
  provably cannot change the output -> a hidden arc, never a timing arc);
- it keys on a state-node `capture` target; a pure combinational cell has no
  cross-coupled state node, so `targets` is empty and P1 cannot be proven.

AIOI21 makes the gap concrete. For arc `B -> ZN` the side pins are `{A1,A2}` and
the sensitizing region is `!(A1*A2)` = THREE minterms (`!A1&!A2`, `A1&!A2`,
`!A1&A2`); `A1&A2` is blocked. For arc `A1 -> ZN` the side pins are `{A2,B}` and
the sensitizing region is `A2*B` = ONE minterm, which the collateral represents
as an UNCONDITIONAL arc (no `-when`). The number of sensitizing minterms is
exactly what decides unconditional-vs-split.

## 1. Scope

**In scope (combinational delay arcs only):**
- AOI (AND-OR-INVERT), e.g. AIOI21 `ZN = B*!(A1*A2)`, AOI22 `ZN=!(A1*A2 + B1*B2)`.
- OAI (OR-AND-INVERT), e.g. OAI22 `ZN=!((A1+A2)*(B1+B2))`.
- Deeper multi-level AND-OR (e.g. AOI211 / AO22-class), one cell.
- Single-output cells. Two-state side pins (0/1). Static CMOS complementary gates.

**Out of scope (unchanged, untouched):**
- Sequential / constraint arcs (hold/setup/mpw/removal/recovery) -- keep the
  existing `derive()` path; this spec ADDS a combinational path, it does not
  rewrite the sequential one.
- Multi-output cells; pass-gate / ratioed / dynamic logic; tri-state.
- Deck assembly, `.meas`/`.tran`, HSPICE execution (no simulator here).
- Real N2P collateral validation (that is GOAL 1 Step 5 / GOAL 2 final check;
  both QUEUED for the photo channel -- this spec is synthetic-anchor only).

## 2. What the engine outputs per arc

For one combinational arc `(rel_pin -> output)` on a cell, with side pins
`S = inputs \ {rel_pin}`, the engine derives via **Boolean difference over the
switch-level model** (reusing `engine.switchlevel.evaluate`, stdlib, no SAT):

For each assignment `s` of the side pins `S`, compute
`BD(s) = [ output(rel_pin=1, s) != output(rel_pin=0, s) ]`.

- **SENSITIZING set** = `{ s : BD(s) is True }` -- the related pin controls the
  output. Each `s` is a candidate WHEN minterm.
- **BLOCKED set** = `{ s : BD(s) is False }` -- related pin cannot change output;
  this side-state belongs to a hidden arc, never a timing arc.
- **Conditioning:** if `|SENSITIZING| == 1` -> the arc is UNCONDITIONAL (the
  single minterm is implied; collateral carries no `-when`). If `> 1` -> the arc
  SPLITS into one WHEN per sensitizing minterm.

The result is wrapped in `Derivation`s (value + reason + stage), per the
repo convention (every computed value carries why). Concretely, a new
`CombSensitizationResult` (sibling of `SensitizationResult`) carrying:
`rel_pin`, `output`, `side_pins`, `sensitizing` (list of minterm dicts, each a
`Derivation`), `blocked` (list of minterm dicts), `conditional: bool`,
`when_set` (the canonical set of WHEN strings the engine asserts), and
`arc_check` (the MATCH/CATCH summary, see SS3).

Worked AIOI21 expectation (the acceptance ground truth):
- `B -> ZN`: side `{A1,A2}`; sensitizing `{!A1&!A2, A1&!A2, !A1&A2}` (3),
  blocked `{A1&A2}`; conditional; `when_set == {!A1&!A2, A1&!A2, !A1&A2}`.
- `A1 -> ZN`: side `{A2,B}`; sensitizing `{A2&B}` (1), unconditional;
  `when_set == {} / NO_CONDITION`.
- `A2 -> ZN`: side `{A1,B}`; sensitizing `{A1&B}` (1), unconditional.

## 3. Validation modes -- REGION EQUIVALENCE (the accuracy machinery)

Minterm-set equality is a false-positive generator: real kits write the
sensitizing region in REDUCED form (one `-when "!A1"` covering two minterms when
the timing is identical), and set-identity would flag a correct cell. The
normative check is therefore over the explicit side-pin STATE SPACE, never by
string-comparing `-when` strings.

The check operates at the **(cell, P, dir, O)** level (P = toggling related/input
pin, in one direction, to output O), because the collateral encodes a split
region as MULTIPLE arcs (each `arc.when` is a single conjunction,
`parse_when -> {pin:int}`).

Definitions:
- `SIDE = (cell input pins) \ {P}`; `n = |SIDE|`; state space `S = {0,1}^n`.
- From Stage-1 topology (CCC + switch-level conduction), for each `s in S`:
  `SENS(s) :=` toggling P in this direction changes O (a conducting path to O is
  created/broken). `SENSITIZING = { s : SENS(s) }`; `BLOCKED = S \ SENSITIZING`.
- `cover(W_coll) =` union, over every collateral `-when` conjunction `c` for arcs
  matching `(P, dir, O)`, of `{ s in S : s |= c }`. A conjunction fixing `k` of
  `n` side pins covers `2^(n-k)` states.
- **Unconditional arc (no `-when`) -- Option A semantics (adjudicated 2026-06-24).**
  A when-less arc does NOT mean "P sensitizes O in all of `S`". It asserts "P
  sensitizes O, characterized at its natural sensitizing region" -- the kit
  delegated the condition to the characterizer (it had no need to split). So for
  an unconditional arc, `cover := SENSITIZING` by definition. Treating it as
  full-`S` would FALSE-FLAG any complex-gate input that controls O only in a
  subset of states (e.g. AIOI21 `A1`, which sensitizes only at `A2&B`). MATCH for
  an unconditional arc therefore reduces to `SENSITIZING != ∅` (the arc names a
  pin that CAN control O); DIVERGENCE only if `SENSITIZING == ∅` (a dead arc).
  Partition tie-in (still DEFERRED, SS3.5): an unconditional arc whose
  `SENSITIZING` spans `>= 2` distinct `SIG` groups is a PARTITION-WARN candidate
  (the kit arguably should have split it).

Verdicts:
- **(i) MATCH** -- `cover(W_coll) == SENSITIZING` AND
  `cover(W_coll) ∩ BLOCKED == ∅`. Reported `AGREE`. A correct collateral never
  flags, whether it spelled the region as full minterms or reduced.
- **(ii) DIVERGENCE** -- otherwise, reporting the differing STATES explicitly:
  - `cover \ SENSITIZING` -> "kit marks sensitizing where topology says blocked";
  - `SENSITIZING \ cover` -> "topology sensitizes but kit omits this region".

Split-vs-merge of timing-EQUIVALENT states is now a non-issue (packaging, not
correctness). These reuse and generalize the existing `arc_check` AGREE/DISAGREE
convention.

- **(iii) UNSUPPORTED-WHEN** (SCLD realism guard) -- real kit `-when` strings are
  NOT always conjunctions; they contain OR (e.g. `"A1 | A2"`). `parse_when`
  models a conjunction only. If a collateral `-when` for the arc is not a pure
  conjunction (contains OR / cannot be reduced to `{pin:int}`), the verdict is
  `UNSUPPORTED-WHEN`, NEVER `DIVERGENCE`. A tool that says "I can't read this one"
  keeps trust; one that mislabels a correct cell as wrong loses it permanently.
  Mandatory before any real-data run; cheap to add now (a guard in the verdict
  path + one test).

## 3.5 Partition-adequacy (DEFERRED -- NOT IMPLEMENTED THIS SESSION; the region refactor MUST NOT remove its hook)

Region-equivalence accepts ANY packaging of the sensitizing region. But merging
states whose PULL NETWORK differs (different delay) is under-characterization --
a real defect only topology can catch. We NAME it now so the region refactor
cannot design away the hook, and DEFER the verdict.

- For each `s in SENSITIZING` the engine also computes `SIG(s)` = the
  conduction-path signature: the transistors / series-parallel structure forming
  the active path to O under `s` and P's transition.
- If a SINGLE collateral `-when` conjunction covers states from `>= 2` distinct
  `SIG` groups, that is a PARTITION-WARN candidate (kit merged states whose pull
  network differs -> plausibly different delay -> under-characterized).
- This is NOT a sensitization error and is NOT gated this session. No
  partition-adequacy assertion is added to the test scope now.

**IMPLEMENTATION CONSTRAINT (applies NOW):** the engine MUST compute and surface
`SIG(s)` per sensitizing state even though only `SENS(s)` is asserted this
session. Do not collapse the per-state structure away during the region refactor
-- it is cheap (CCC already walks it) and it is the hook for the higher-value
verdict.

## 4. Module shape

- `engine/stages/stage2_sensitize.py`: add `derive_combinational(graph, arc, ccc)`
  returning `CombSensitizationResult`. **Dispatch on STRUCTURE, not label:** route
  here when the channel-connected component FEEDING THIS ARC (the CCC containing
  the path from `P` to `O`) has no state node -- no storage / feedback structure
  found by Stage 1. Do NOT dispatch on `arc_type == "combinational"`: that is a
  collateral label that can be wrong, and topology cannot lie (that is the thesis
  of this work). Scope the no-state-node check to the ARC's CCC, not the whole
  cell, so mixed cells (combinational arcs on a cell with sequential parts) need
  no rework later -- this session is pure-combinational but the check is
  CCC-scoped from the start. Boolean difference reuses `switchlevel.evaluate`.
- `engine/types.py`: add `CombSensitizationResult` (dataclass; `Derivation`-wrapped
  fields, mirrors `SensitizationResult` style).
- A small cell-level cross-check helper (in stage2 or stage5_verify) that
  aggregates arcs by `(rel_pin, output)` and computes the MATCH/CATCH verdict.
- No changes to deck assembly, the sequential path, or v1.

## 5. Synthetic anchors (no real data)

Extend the `examples/sample_collateral` pattern with reconstructed netlists whose
function is confirmed from the cell's own WHEN. Each anchor ships a `.subckt`
(complementary CMOS for the stated Boolean function) plus the cell's `define_arc`
WHEN set, so the engine derives from topology and the test checks against the
documented truth. Anchors this session: AIOI21 (2a), XOR2/XNOR2 (2b),
AOI22 + OAI22 (2c), one deeper AND-OR (2d).

**BINATE anchor (XOR2) -- mandatory, placed SECOND.** AIOI/AOI/OAI are unate in
every input; the region method can pass on EVERY unate anchor and still fail on
the first binate cell. XOR2 (`Z = A ^ B`) breaks the unate assumption early, so a
broken direction/region model is caught before AOI22/OAI build on it. For the
`A -> Z` rise arc (`P = A`, `SIDE = {B}`):
- `SENSITIZING == full space {B=0, B=1}`; `BLOCKED == ∅` -- propagation is
  UNCONDITIONAL (A always flips Z, for either B). The engine MUST NOT emit a
  spurious conditional WHEN.
- BUT the OUTPUT DIRECTION is side-state-dependent: `A-rise @ B=0 -> Z rise`;
  `A-rise @ B=1 -> Z fall`. The engine must associate output direction with the
  side-state (vector encoding, PROJECT_NOTES SS2.3) and NOT confuse
  "direction varies" with "conditional sensitization".
- The two unate-assumption failure modes this anchor tests against:
  "narrower-than-full region <=> conditional arc" and "fixed output direction per
  input edge". XOR2 violates both. (XNOR2 added too if cheap.)

## 5.9 Vector-gate RED step (MANDATORY for every synthetic anchor)

A reconstructed netlist can silently encode the WRONG Boolean function and still
"pass" if you only check it against itself (this happened in the first 2a draft:
a netlist computing `B + A1*A2` was verified against its own output, contradicting
the cell's `-vector` directions). To close the loophole, EVERY anchor's RED phase
MUST, BEFORE any region is derived, assert that `switchlevel.evaluate` on the
reconstructed netlist reproduces the cell's `template.tcl` `-vector` transition
directions -- the per-arc INPUT and OUTPUT polarity (unate sense). For AIOI21 the
vectors are in PROJECT_NOTES SS2.4 (`A1->ZN {RxxF}` = A1 rise, ZN fall =
negative-unate; `B->ZN {xxRR}` = positive-unate). For a cell reconstructed from a
function, emit the expected vectors and assert switchlevel matches. Only after the
vector gate passes may sensitization regions be derived from the netlist. The
`-vector` direction is the independent signal that a truth table alone does not
give.

## 6. Phasing (after approval; one step per turn, test-first)

- **2a -- AIOI21** (`ZN = B*!(A1*A2)`; adjudicated 2026-06-24 -- positive-unate in
  B, negative-unate in A1/A2, B inverted internally). Reconstruct the netlist;
  pass the SS5.9 vector gate (truth table incl. `(A1=1,A2=1,B=0) -> ZN=0`, and
  `A1->ZN {RxxF}`, `A2->ZN {xRxF}`, `B->ZN {xxRR}` directions); THEN feed to the
  engine and assert it INDEPENDENTLY derives, in REGION terms:
  `B -> ZN` `SENSITIZING == !(A1*A2)` = `{!A1&!A2, A1&!A2, !A1&A2}`,
  `BLOCKED == {A1&A2}` (conditional); `A1 -> ZN` `SENSITIZING == {A2&B}` and
  `A2 -> ZN` `SENSITIZING == {A1&B}` (one state each -> unconditional-correct per
  Option A, NOT full-S). And that `SIG(s)` distinguishes the parallel-PMOS state
  (`!A1&!A2`) from the single-PMOS states (the partition datum -- computed, NOT
  gated). `test_aioi21_ground_truth.py` is parser-only -- ADD engine-derivation
  assertions (new `tests/engine/test_aioi21_sensitize.py`); do not weaken or
  duplicate the parser test.
- **2b -- XOR2 / XNOR2 (binate).** Per SS5: `SENSITIZING == full`, `BLOCKED == ∅`,
  no spurious conditional WHEN; output direction tracked per side-state.
- **2c -- AOI22 / OAI22.** Two-and-two structure; verifies split with 2 side
  pins per group and OR/AND duality.
- **2d -- deeper multi-level AND-OR.** One cell, e.g. AOI211, to confirm the
  Boolean-difference method scales past two levels.

**CATCH set per class (bidirectional on reduced WHEN).** Beyond the MATCH
assertions, each class adds:
1. corrupted full-minterm WHEN (a sensitizing minterm flipped to a blocked
   state, and a sensitizing minterm dropped) -> MUST flag DIVERGENCE with the
   differing states named;
2. **reduced-but-CORRECT WHEN -> MUST NOT flag** (the credibility test): when the
   real sensitizing region is e.g. `!A1` (two minterms, identical timing) written
   as a single `-when "!A1"`, assert `cover == SENSITIZING`, verdict MATCH;
3. **reduced-but-WRONG WHEN -> MUST flag**: real region `!A1` but kit wrote
   `-when "!A2"`; assert `cover != SENSITIZING`, verdict DIVERGENCE with the
   differing states named. (Without (3) we only prove "no false alarm", not
   "still catches real errors under reduced form".)

Each step: TDD; never weaken a test; never drop an arc; signed commits
(Co-Authored-By as in prior commits); ASCII source; all 515 existing tests stay
green.

## 7. Acceptance

- For AIOI21 / XOR2 / AOI22 / OAI22 / (deeper), the engine's derived
  `SENSITIZING` and `BLOCKED` regions per `(P, dir, O)` are computed from netlist
  topology with no read of `arc.when` for the derivation itself (only for the
  cross-check), and `cover(W_coll) == SENSITIZING` with
  `cover(W_coll) ∩ BLOCKED == ∅` (MATCH = AGREE).
- CATCH (bidirectional): each corrupted-full-minterm mutation AND the
  reduced-but-WRONG WHEN produce a specific DIVERGENCE naming the differing
  states; the reduced-but-CORRECT WHEN does NOT flag.
- `SIG(s)` is computed and surfaced per sensitizing state (partition hook;
  not gated).
- No false divergence on any correct anchor. 515 existing tests remain green.

## 7.5 Impact honesty

Synthetic anchors prove correctness-of-METHOD, not the impact NUMBER. The impact
number is N REAL N2P cells where the engine flags a kit WHEN that is wrong (CATCH)
or confirms it right. That validation is QUEUED behind the photo channel (the
real-data queue) and is NOT claimed by any synthetic MATCH here. The win is CATCH
on real collateral; synthetic MATCH is scaffolding. When the photo channel opens,
the FIRST real cell requested is the one most likely to CATCH or most likely to
use a reduced `-when` (a multi-input AOI / OAI / MUX) -- one real CATCH outweighs
100 synthetic MATCHes for the narrative.

## 8. Open items for the reviewer

1. `CombSensitizationResult` as a new sibling type vs extending
   `SensitizationResult` -- proposed: a new type (keeps the sequential contract
   untouched).
2. Region representation: compute `cover`/`SENSITIZING`/`BLOCKED` as explicit
   sets of side-pin state tuples over the enumerated `S = {0,1}^n`; a single
   `-when` conjunction is canonicalized to the set of states it covers (never
   string-compared). For display, a state set may be reduced back to a minimal
   `-when`-style label.
3. RESOLVED (EDIT 5): dispatch on STRUCTURE -- the arc's CCC has no state node --
   not on `arc_type`. CCC-scoped from the start.
