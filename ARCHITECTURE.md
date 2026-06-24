# DeckGen — Engine Architecture & Working Constitution

> **What this document is.** The single source of truth for how the DeckGen engine
> is layered, what it must never do, and how parallel work is divided. It is a *map
> and a set of boundaries*, not a task list. Every new session — human or agent —
> reads this first. If a decision in here conflicts with something a session "wants
> to do for convenience," this document wins; raise an amendment instead of working
> around it.
>
> **Test for this doc:** a fresh agent that has read *only this file* should be able
> to state (a) what input the engine is allowed to depend on, (b) why the engine is
> not MCQC, and (c) which of the three demos it is working on and what proves it
> done. If that ever stops being true, fix this doc.

---

## 1. What the engine is (and is not)

DeckGen's core is **`topo_core`**: a physics engine that reads a transistor-level
LPE netlist and *derives* a cell's timing-relevant behavior from topology, rather
than reading it from a pre-written recipe.

The thing it replaces — **MCQC** — copies the sensitizing `-when` condition straight
out of the characterization collateral and *never asks whether that condition is
physically true*. No step in today's signoff flow verifies the kit. That gap is the
entire reason this engine exists.

**The one-sentence thesis (put this in front of any reviewer):**
> MCQC copies the WHEN from collateral and trusts it. Our engine derives the
> sensitization from transistor topology and **checks** it — so it catches a WHEN
> the kit got wrong, and (next) catches conditions the kit under-characterized.

Two product goals, in priority order:

- **GOAL 1 — byte-parity baseline (must-have, not the highlight).** For any LPE
  netlist package, generate the FMC decks for combinational cells/arcs and match
  MCQC byte-for-byte. This is the *trust anchor*. It is structurally done.
- **GOAL 2 — derivation accuracy (the highlight).** The engine independently derives
  each arc's sensitizing region from topology and verifies it against the kit. The
  win is a **CATCH on real silicon collateral**, not a MATCH on a cell we built.

Locked scope for the current generation of work: **node N2P v1.0**, corner
`ssgnp_0p450v_m40c_cworst_CCworst_T`, **combinational** cells/arcs first (they need
no initialization). Sequential is a separate, research-grade track (§7, §8).

---

## 2. Engine layers (the pipeline)

`topo_core` is a five-stage pipeline (`engine/stages/`). Today **S0–S2 are real;
S3–S5 are stubs** in the engine pipeline (deck generation in production currently
runs through the `core/` recipe path — see §9). The verdict block reports three
properties, **P1 / P2 / P3**.

```
  LPE .subckt  ──►  S0 parse  ──►  S1 CCC  ──►  S2 sensitize  ──►  S3 init ──► S4 deckgen ──► S5 verify
  (+ parasitic                       │             │   (P1)         (sequential)   (stub)       (stub)
   R / C)                            │             │
                                     ▼             ▼
                              channel-connected   Boolean-difference
                              components           region per arc
                                     │
                                     ▼
                              S3.charge  (Pillar 3)  ──►  cap-graph: grounded Cg + coupling Cc  ──►  charge resolve
                              quantitative R/C from the LPE parasitics
```

The layers, by responsibility:

**L0 — Parse (`engine/stages/stage0_parse.py`).** LPE netlist → `DeviceGraph`:
transistors *and* the retained parasitic R/C network, keyed to logical nets. This is
the only required input to the engine (see Red Line A). The parasitic **C is not
optional** — it is the substrate the charge layer consumes.

**L1 — Structure (`engine/stages/stage1_ccc.py`).** Channel-connected-component
decomposition. CCC is how the engine reasons about conduction paths without a PDK.
For sequential cells this layer extends to **CCC + SCC** (strongly-connected
components find the feedback loops = the storage/state nodes — see §8).

**L2 — Sensitization / region derivation (`engine/stages/stage2_sensitize.py`,
`core/sensitize_bridge.py`; the combinational derivation lives in the in-session
`derive_combinational` / `comb_verdict` work pending merge — see §9).** This is **P1**.
Boolean difference over the switch-level model gives, per arc, the set of side-pin
states in which toggling the related pin changes the output. This is the engine's
core claim and the combinational killer capability.

**L3 — Charge / electrostatic (Pillar 3: `engine/charge.py`, `charge_svg.py`,
`charge_viz.py`).** This layer is **real and partially built — it is not greenfield.**
`charge.py` already reduces the LPE parasitic network into grounded capacitance
(`Cg`) and coupling capacitance (`Cc`) per logical net; a charge-resolve step
consumes them. This is the *quantitative* layer — it turns "these two states have a
different conduction structure" into "these two states differ in RC by ~X." It is
the substrate for Demo 2's ceiling and Demo 3's foundation (§7).

**L4 — Verdict / report (`engine/verdict.py`, `core/report.py`,
`core/engine_present.py`).** Renders **P1/P2/P3** and the combinational verdict
(MATCH / DIVERGENCE / UNSUPPORTED, with named differing states). `verdict.py` is
deliberately built to fit **one screen** so it survives the screenshot-only feedback
channel (§6, Red Line F-adjacent). `engine_present.py` exposes region / verdict / SIG
as JSON so the GUI can render the same data the tests assert.

---

## 3. Load-bearing principles (the red lines)

These are non-negotiable. An agent that finds itself about to violate one should
**stop and raise an amendment**, not route around it.

**A. The engine derivation depends on `.subckt` ONLY. Never on `template.tcl`.**
This is the most important rule in the project, because GOAL 1 is "any LPE package,
*including unseen cells*." A truly unseen cell ships its `.subckt`; it does **not**
(and must not need to) ship a `template.tcl`. `template.tcl` is exactly what MCQC
relies on and what we intend to retire. If the engine needs collateral to *derive*,
the dependency has merely moved from "table-driven generation" to "table-driven
verification" — that is not retirement.
- The **vector gate** (verify a reconstructed netlist reproduces template.tcl's
  `-vector` transition directions) is a **development-time scaffold** to stop a
  reconstructed synthetic netlist from silently encoding the wrong function. It is
  **never a runtime input.**
- At **library scale (Demo 1)**, the netlist is real, not reconstructed, and the
  verification signal is **deck byte-parity vs the template flow** — a strictly
  stronger, end-to-end signal that *supersedes* the vector gate. Deck-parity ⊃
  (unate polarity correct) + (region correct) + (parser reproduces deck).
- The engine's end state on real cells: read `.subckt`, derive unate polarity and
  region from topology alone (the NMOS series/parallel structure *is* the unateness).
  `-vector`/`-when` are then **the objects under audit**, used for cross-check when
  collateral happens to be present — not as ground truth, and not as a requirement.

**B. Region equivalence, not minterm-set equality.** A correct kit frequently writes
the sensitizing region in *reduced* form (one `-when "!A1"` covering two states when
the timing is identical). Comparing minterm sets would false-flag that correct cell.
MATCH is defined over the explicit side-pin state space:
`cover(W_coll) == SENSITIZING  AND  cover(W_coll) ∩ BLOCKED == ∅`, computed by
expanding conjunctions into covered states — **never by string-comparing `-when`**.
Split-vs-merge of *timing-equivalent* states is then a packaging question, not a
correctness question. A false-positive generator is worse than no tool; the team
stops trusting it after the second false alarm.

**C. Unconditional ≠ "covers all states."** An arc with no `-when` means "P
sensitizes O, characterized at its natural condition" — *not* "P sensitizes
everywhere." On a complex gate a pin can be unconditional yet sensitize in a single
state (e.g. AIOI21 `A1→ZN` sensitizes only at `{A2 & B}`). For an unconditional arc:
skip region-equivalence, assert **liveness** (`SENSITIZING ≠ ∅`; an empty region is a
dead arc → DIVERGENCE), and flag a **partition-adequacy candidate** if the single
covered region spans ≥2 distinct conduction signatures (§3-E).

**D. Topology over labels.** Decide combinational-vs-sequential by the structural
signal — **the channel-connected component feeding the arc has no state node** — not
by `arc_type == "combinational"`, which is a collateral label that can be wrong.
Scope the no-state-node check to the *arc's CCC*, not the whole cell, so mixed cells
need no rework later. "Topology can't lie" is the thesis of this work; encode it.

**E. A reconstructed netlist must be cross-checked against an INDEPENDENT ground
truth before any region is derived from it.** This is the AIOI21 lesson, made into a
rule. In the synthetic/dev path the independent signal is the `-vector` transition
polarity (the RED-phase vector gate). At scale it is deck-parity. The failure mode
this prevents: building the netlist to produce the answer you already wrote down,
then "verifying" it against itself. (What it caught: a netlist computing `A1·A2+B`
that contradicted `{RxxF}` = A1↑→ZN↓ negative-unate; the documented function
`B·!(A1·A2)` was correct all along.)

**F. The partition-adequacy hook must survive every refactor.** The engine computes,
per sensitizing state, the **conduction-path signature (SIG)** — the series/parallel
transistor structure forming the active path. Even when only sensitization is gated,
**SIG must still be computed and surfaced.** It is cheap (the CCC walk already has
it) and it is the data foundation for the higher-value verdict — "the kit merged
states whose pull-network differs, so it plausibly under-characterized." A refactor
that collapses per-state structure away to make regions "clean" deletes the most
valuable thing the engine can do. Do not.

---

## 4. The dev ↔ airgap contract

Real N2P collateral lives on an **air-gapped secure system** and cannot leave it.
The intended deployment is therefore the reverse of data exfiltration: **build the
engine, download it into the airgap, and run it there against the full collaterals
folder.** This is already designed for, and the contract must be preserved.

**The contract that exists (`engine/config.*.json`, `engine/config.py`):**
- `config.fixture.json` — `backend: "fixture"`, local synthetic data, **stdlib-only
  so it runs on an air-gapped box with no `pip install`**. This is the dev default
  (SEGMENT 1).
- `config.real.json` — `backend: "real"`, with `real_root` pointing at the server
  collateral root. This is the airgap run (SEGMENT 2).
- **The only thing that changes between dev and airgap is the config pointer.** Same
  engine code, different backend.

**The architecture rule:** every new capability must work through the **backend
abstraction**. Nothing in the engine may hardcode the synthetic fixture's directory
layout, file naming, or path depth — those are an *input contract* satisfied by
config-driven discovery, not assumptions baked into code. A capability that runs in
`fixture` but breaks in `real` is a contract violation, and it is the failure mode
you **cannot catch in dev** (the synthetic fixtures are arranged to your own taste).

**Before any library-scale run:** reconcile the parser against the *real* collateral
layout (see `docs/phase2/n2p_collateral_inspection.md` /
`n2p_collateral_inventory.md`). If the parser was written to the simplified synthetic
layout, the first airgap run is a layout mismatch, not a result. Treat
"download-and-run" as gated on this reconciliation, not on the algorithm.

**Stdlib-only is a constraint, not a preference** — it is what lets the engine run in
an airgap with no package installs. New engine-core dependencies are a red flag;
justify them against the airgap before adding.

---

## 5. The three demos (a capability ladder)

These are not three parallel features. They are a ladder from *reproduce known* →
*handle unknown* → *understand structure*, with **decreasing certainty and
increasing difficulty.** The narrative value also rises with the ladder: Demo 1 buys
trust, Demo 2 shows generalization, Demo 3 shows depth.

| # | Demo | Nature | Exercises | Verification signal | Certainty |
|---|------|--------|-----------|--------------------|-----------|
| **1** | Full-library combinational cross-validation | Engineering (scale) | L0–L2, deck gen | **deck byte-parity** vs template flow (⊃ region + parser correctness) | **High — will land** |
| **2** | Self-authored cell | Controlled experiment (generalization) | L0–L2, + L3 for "same structure, different RC" | **author-supplied ground truth** (you designed the cell) | **Medium-high** |
| **3** | Sequential cell analysis + fingerprint | **Research** (understanding) | L1 (CCC+SCC), L3 charge | partial — structure extraction demoable; charge/fingerprint is derivation, not a passing suite | **Structure demoable; theory is research** |

**Demo 1 — full library.** Run the whole library through *both* the engine flow and
the template flow; cross-validate. This single demo validates GOAL 1 and GOAL 2 at
once: if the engine's derived region is wrong, its deck fails byte-diff. The output
is a **library-scale report**: for every cell × every arc, engine-region vs kit-WHEN,
classified **MATCH / DIVERGENCE / UNSUPPORTED**. The high-value part is *not* "all
green" — it is the split: "*X* cells byte-parity-pass (trust), *Y* cells the engine
flags for review (value)." Present those two cohorts separately. Cleanest, most
defensible, most aligned with "measurable impact." **Vector gate retires here**;
deck-parity replaces it.

**Demo 2 — self-authored cell.** You design a cell (so *you* are the ground truth),
hand the engine only the `.subckt`, and show that its derived region / unateness /
deck match your design intent. This loses Demo 1's end-to-end signal (no template
deck to diff), so the ground truth must come from you. Its purpose is to **stress the
generalization boundary** — deliberately author awkward topologies (deep AND-OR,
internal inversion, asymmetric paths; and a "same structure, different RC" case that
only the charge layer can distinguish). Its ceiling is set by how far L3 (charge) is
built. Defer authoring this prompt until Demo 1's engine core is stable, or its
baseline keeps moving under it.

**Demo 3 — sequential + fingerprint.** This is the **research** rung; see §8. Do not
scope it as engineering. The honest demo form: **CCC+SCC structure extraction is a
real demo** (give a real flop, the engine marks its state nodes and feedback loops);
**charge-based timing characterization and the fingerprint are theory + worked
examples, explicitly research-in-progress.** For a reviewer like MJ, "I have a
serious framework underway on the structural problem" lands harder than "another
working tool," precisely because it shows you are after the structural prize.

---

## 6. The screenshot-only feedback channel

Real collateral reaches a developer-side session only as **photos / screenshots**.
This is a recognized, first-class constraint — it is why `verdict.py` is built to fit
one screen. It shapes how *any* agent requests real data:

- Default to progress that needs **no real data** (synthetic anchors confirmed from a
  cell's own WHEN/truth table; the charge math against documented parasitics).
- When real data is genuinely required, **batch all of it into one numbered request**
  per work unit: per item, give file + exact lines/section to photograph + why; for
  terminal output, give the exact command to run; for anything ≤ a few tokens (a pin
  name, a path, a number), ask the user to **type** it.
- On receiving a screenshot, **echo back what was extracted and wait for confirmation**
  before building on it. Misreads are expensive.
- **At library scale this channel is bypassed entirely** — the engine runs inside the
  airgap and reads the collateral directly. The screenshot channel is for
  developer-side spot-validation, never for scale.

---

## 7. Multi-agent organization

The three demos differ enough in *nature* that they get different agents with
**different disciplines**, sharing this document as the constitution. One repo, three
isolated worktrees/branches.

```
                ARCHITECTURE.md  (this file — shared constitution)
                         │
      ┌──────────────────┼───────────────────────┐
      │                  │                       │
 [Build Agent]      [Generalization Agent]   [Research Agent]
  Demo 1             Demo 2                   Demo 3
  worktree/branch    worktree/branch          worktree/branch
  loop / TDD         controlled experiment    research notebook
  autopilot ON       half-loop                autopilot OFF
  byte-parity locks  you supply ground truth  NO "green"; output is a derivation
        │                  │                       │
        └─ owns engine core (L0–L2)  ◄── read-only ──┘ (extend on own branch, merge up)
```

**Disciplines (this is the point — they are not the same):**
- **Build Agent (Demo 1):** full loop engineering. Autopilot on, TDD, deck-parity is
  the lock. This is the proven playbook. **It owns the engine core (L0–L2)** — single
  source of truth.
- **Generalization Agent (Demo 2):** half-loop. It has assertions (your cell's truth)
  but its goal is to **find where the engine derives wrong/incompletely**. Its STOP
  condition is *not* "all green" — it is "found a cell class the engine mis-handles."
  **Failure cases are deliverables**; autopilot must not strong-arm them green.
- **Research Agent (Demo 3):** **not loop engineering. Autopilot OFF.** Its
  deliverable is **theory + CCC/SCC extraction code + worked examples**, not a passing
  suite. Its CLAUDE.md must say, in these words: *"This is research. There is no
  'green.' The deliverable is a derivation, not a passing test suite. Do NOT fabricate
  completeness."* This institutionalizes the autopilot-resistance lesson: an
  open-ended problem has no green to converge on, and a wrapper that says "continue
  working" will make an agent spin or self-deceive.

**Dependency direction (encodes Red Line A across agents):**
- Engine core (L0–L2) is owned by Build Agent; the other two **read it, do not change
  it.** New work (charge layer, SCC, fingerprint) lives on the owning agent's branch
  and merges **up** to mainline only when mature.
- **No agent may add a `template.tcl` dependency to the engine core for its own
  convenience.** This is the red line, replicated into every agent's CLAUDE.md.

**The human is the bottleneck — design around it.** Each agent will STOP at decision
gates (as the AIOI21 episode did), and the human review at those gates — e.g.
catching a wrong derived function via `-vector` polarity — is the single
highest-value step in the flow. Three high-intensity lines reviewed by one person
degrades that review. Recommended cadence: **watch the Build Agent closely; let the
Research Agent run asynchronously with periodic review** (research should not be
rushed); slot Generalization after or interleaved with Build. Do not staff three
hot lines at once.

---

## 8. Research frontier — charge quantification & sequential

Two ambitions are intentionally *queued behind* a trustworthy single-cell engine,
because pattern-finding needs reliable atoms to generalize from. Building them before
the method is validated on real cells is building on sand.

**Charge quantification (the next real use of internal-node structure).** L3 already
aggregates the parasitic network into `Cg`/`Cc`. The next step turns SIG's *qualitative*
"structure differs" into a *quantitative* "delay differs by ~X" via first-order RC /
charge estimation over the topology. This is what makes **partition-adequacy** safe to
gate (structure-different states whose RC barely differs should *not* warn; cry-wolf
again otherwise) and what makes the library report **actionable** (a relative delta,
not just a flag). **Boundary:** the engine is **not** a SPICE replacement — absolute
delay is the FMC deck's job (GOAL 1). Charge estimation produces *relative magnitude /
ordering* for "should this have been split?" and for prioritizing divergences — not
absolute numbers. (`docs/research/findings.md` holds the working derivations.)

**Sequential — a genuine step-change, not an increment.** Everything above rests on
combinational logic being *memoryless*. Sequential cells have state, which breaks the
foundation:
- Output is a function of inputs **and internal state** — plain Boolean difference
  does not apply.
- The state nodes must first be *found*. **CCC + SCC** is the right tool and the right
  structural insight: a combinational cell's CCC has no SCC (no feedback); a sequential
  cell's CCC contains an SCC (the cross-coupled storage loop). **This is also the
  clean structural combinational-vs-sequential discriminator** (Red Line D, extended).
- Sensitization becomes *temporal* (setup/hold, clock-to-Q, capture windows) — modeling
  the storage loop's behavior, a markedly harder theoretical problem.

The path: **CCC+SCC state extraction (achievable, demoable) → charge-based
characterization of the storage node (research, from near-zero) → cell fingerprint** (a
structural+behavioral signature: state-node count, feedback topology, clock structure,
storage-node charge signature). The fingerprint is the **atom for pattern discovery** —
two cells with isomorphic fingerprints are likely the same structural class, and kit
treatment that diverges between them is a suspicious signal. **This requires solid
theoretical research and derivation; do not underestimate it, and do not put it in an
autopilot loop.**

---

## 9. Current state & known reconciliations

Honest status so a fresh agent does not mis-assume:

- **Engine pipeline:** S0–S2 (parse / CCC / sensitize) are real; S3–S5 (init /
  deckgen / verify) are stubs in the *engine* pipeline. Production deck generation
  currently runs through the **`core/` recipe path** (`core/deck_recipe.py`,
  `core/deck_builder.py`, `core/batch.py`), which has template+generator dual-path
  cross-validation and byte-parity (GOAL 1 baseline). Unifying the engine S4 with the
  recipe path is future work; until then, know that "deck gen" lives in `core/`.
- **Charge layer (L3):** real and partially built (cap-graph aggregation done; resolve
  step present). **Not empty** — a common mis-read.
- **Combinational region-derivation (P1 region equivalence, partition hook, structural
  dispatch, the AIOI21 fixes):** designed and validated in an interactive session and
  **may not yet be merged to mainline** (`derive_combinational` / `comb_verdict`).
  Reconcile/push before treating it as in-repo. The *decisions* in §3 are settled
  regardless of merge state.
- **GUI:** the data layer (`engine_present.py` → region/verdict/SIG JSON) is ready;
  the *visualization* (purple+gold, collapsible, region/verdict rendering) is **not yet
  built** — correctly deferred behind engine correctness. One demo screen (a real cell's
  region + a red DIVERGENCE + named bad state) is enough for the MJ demo; full GUI is
  not required first.
- **MJ demo material:** the engine-story walkthrough is in `docs/engine_walkthrough/`
  (s0_parse / s1_ccc / s2_sensitize + figure/pptx builders).

---

## Appendix — module map

| Path | Role |
|------|------|
| `engine/stages/stage0_parse.py` | LPE → DeviceGraph (transistors + parasitic R/C) |
| `engine/stages/stage1_ccc.py` | CCC decomposition (L1); CCC+SCC for sequential |
| `engine/stages/stage2_sensitize.py` | Boolean-difference sensitization (P1) |
| `engine/stages/stage3_initialize.py` | Sequential init (stub; Demo 3 territory) |
| `engine/stages/stage4_deckgen.py` · `stage5_verify.py` | Deck gen / verify (stub in engine; see §9) |
| `engine/charge.py` · `charge_svg.py` · `charge_viz.py` | Pillar 3 — cap-graph (Cg/Cc), charge (L3) |
| `engine/switchlevel.py` | Switch-level conduction model (Boolean-difference basis) |
| `engine/verdict.py` | One-screen P1/P2/P3 verdict (screenshot-safe) |
| `engine/config.py` · `config.fixture.json` · `config.real.json` | Backend abstraction; dev↔airgap contract (§4) |
| `core/deck_recipe.py` · `deck_builder.py` · `batch.py` | Production deck generation (GOAL 1, recipe path) |
| `core/sensitize_bridge.py` · `engine/whencond.py` | WHEN ↔ region bridge |
| `core/engine_present.py` · `core/report.py` | Verdict/region JSON + HTML report (L4) |
| `tools/deck_diff.py` | Two-path cross-validation (template vs generator) |
| `tools/validate_decks.py` | Tiered diff vs reference decks (byte / normalized / classified) |
| `tools/scan_collateral.py` · `batch_report.py` | Collateral discovery + batch report (Demo 1 scale) |
| `docs/engine_walkthrough/` | MJ demo material (S0–S2 story) |
| `docs/research/findings.md` | Charge / electrostatic working derivations |

## Appendix — glossary

- **CCC** — channel-connected component: transistors sharing source/drain nets;
  the unit of conduction-path reasoning without a PDK.
- **SCC** — strongly-connected component: a feedback loop in the CCC = a storage/state
  node. Present in sequential cells, absent in combinational.
- **P1 / P2 / P3** — the engine's three verdict properties (P1 = sensitization).
- **Region** — the set of side-pin states in which an arc's related pin sensitizes the
  output. The physics. Compared by *region equivalence*, not minterm-set identity.
- **SIG** — conduction-path signature: the series/parallel transistor structure of the
  active path in a given state. The basis for partition-adequacy.
- **Vector gate** — dev-time check that a reconstructed netlist reproduces template.tcl's
  `-vector` transition polarity. A scaffold; superseded by deck-parity at scale; never a
  runtime input.
- **Partition-adequacy** — verdict (queued) that a single `-when` covering states of
  differing SIG is under-characterized (the kit should have split it).
- **MATCH / DIVERGENCE / UNSUPPORTED** — per-arc verdict: region agrees with kit / region
  disagrees (with named states) / `-when` form the engine does not yet handle.
- **SEGMENT 1 / SEGMENT 2** — fixture (dev, synthetic, stdlib-only) vs real (airgap server)
  backend; the only difference is the config pointer.
