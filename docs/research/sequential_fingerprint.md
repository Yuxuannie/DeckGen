# Sequential Cell Analysis & Fingerprint (Demo 3 — Research Lane)

> **Lane discipline (ARCHITECTURE.md §7).** This is the *research* rung. There is
> no "green." The deliverable is a **derivation**, plus the one layer that genuinely
> *is* demoable code (Layer 1). Each layer ends with an explicit
> **solid / conjecture / open** ledger. Nothing here claims a working setup/hold
> analyzer or a working fingerprint system. Where a claim is a guess, it says so.

Branch: `research/seq-fingerprint`. Reads the engine core (L0–L2) read-only;
extends on this branch only (Red Line A, §7 dependency direction).

The three layers, in decreasing certainty:

| Layer | What | Status |
|-------|------|--------|
| 1 | CCC+SCC structure extraction (state nodes, loops, clock, discriminator) | **Solid — code + tests on SDFX** |
| 2 | Charge characterization of the storage node (setup/hold physical basis) | **Research — paper derivation + 1 worked number** |
| 3 | Cell fingerprint (structural+behavioral signature) | **Concept + hand-computed sketch** |

Anchor cell throughout: `engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt` — a synthetic
scan-DFF in LPE form (device terminals are private extracted nodes, connectivity
only via parasitic R, noise C only). The engine re-derives its topology *blind*
(R-merge + CCC); nothing keys off the `ml_*`/`sl_*` names — those are the test's
known-answer only.

---

## Layer 1 — Structure extraction (SOLID; test-covered, demoable)

### 1.1 The thesis being encoded

ARCHITECTURE.md §8, made executable:

> A combinational cell's CCC has **no SCC** in its influence graph.
> A sequential cell's CCC contains an **SCC** — the cross-coupled storage loop —
> and that SCC *is* the state node.

This is also **the clean structural combinational-vs-sequential discriminator**
(Red Line D, extended from the per-arc CCC check to whole-cell and whole-arc
scopes). "Topology can't lie; the `arc_type` label can."

### 1.2 What the engine core already provides (assessed, not rebuilt)

`engine/stages/stage1_ccc.py` already does the hard part:

- Builds the **influence graph**: a directed edge `(gate → drain)` and
  `(source → drain)` per transistor, over non-rail nets.
- Runs **Tarjan SCC** (`_sccs`) over it.
- Keeps only the *real storage* members: an SCC of size ≥ 2, intersected with the
  set of nets that are *gates* somewhere (a stored value both **is driven** — a
  drain — **and controls** — a gate; series-stack internal nodes are drains/sources
  only, so the intersection drops them). This is the subtle, correct part.
- Labels master/slave by **influence-distance to the output** (the slave drives Q
  directly; the master is one stage back).

Run on SDFX, the core already returns the four state nodes
`{ml_a, ml_b}` (master), `{sl_a, sl_b}` (slave). **The SCC reasoning the §8
frontier calls for is therefore already present in the core** — this was the most
important finding of the Layer-1 assessment.

### 1.3 What was genuinely missing (built on this branch)

The core emits a *flat* `List[StateNode]` and stops. For Demo 3 we need a clean
**public sequential-structure object** and three things the core does not expose:

1. **Storage loops as discrete objects** — group the flat state-node list back into
   one `StorageLoop` per cross-coupled SCC, with its member nets and role.
2. **Clock-path identification** — the primary input whose influence reaches the
   *most* storage loops is the clock (a clock gates every latch pass-gate; a data
   input feeds one). Its **buffered phase nets** are the nets it reaches *before*
   entering any storage loop.
3. **A whole-arc sequential discriminator** + reconciliation with the core's
   existing per-arc `is_combinational_arc` (see §1.5 — this surfaced a real scope
   subtlety).

New module: `engine/seq_structure.py` (this branch). Public API:

```
extract(graph, ccc=None) -> SeqStructure
    .is_sequential : bool          # cell has >= 1 storage SCC
    .storage_loops : [StorageLoop] # ordered master..slave, each with nets+role
    .clock_pin     : str | None
    .clock_path    : [str]         # buffered clock nets (e.g. ['clkb'])

arc_traverses_storage(graph, rel_pin, output, struct=None) -> bool
check_discriminator(graph, rel_pin, output, is_comb_local, struct=None) -> str
```

It **imports** `stage1_ccc.decompose` (read-only reuse); it does not modify it.

### 1.4 Worked example — SDFX (verbatim engine output)

```
=== SeqStructure(SDFX_LPE_PLACEHOLDER) ===
is_sequential : True
clock_pin     : CP      clock_path : ['clkb']
storage loop [master] : ['ml_a', 'ml_b']
storage loop [slave]  : ['sl_a', 'sl_b']
```

Every line is *derived blind*: the clock is found because **CP** is the only
primary input whose influence reaches *both* storage loops; `clkb` is named as the
clock path because it is the net CP reaches before the first loop. (`D`, `SI` each
reach only the data side; `SE` gates the input mux, not the latches.) This matches
the generator's ground truth exactly, with zero name matching.

### 1.5 The discriminator agreement — and a real scope subtlety

Red Line D requires the SCC discriminator to **agree** with the engine core's
combinational dispatch (`stage2_sensitize.is_combinational_arc`). Verified:

- **All six combinational fixtures** (AIOI21, AOAI, AOI22, OAI22, XNOR2, XOR2):
  `is_sequential=False`, 0 loops, no clock, and `check_discriminator` returns
  **AGREE**. The thesis holds: no SCC ⇒ combinational.

- **The DFF `CP→Q` arc** exposed a genuine, instructive subtlety. The core's
  `is_combinational_arc` is **CCC-LOCAL**: it scopes the no-state check to the
  *output's own* channel-connected component. On SDFX, `Q`'s CCC is just the output
  inverter (`['Q']`) — no feedback inside it — so the local check correctly returns
  *combinational for Q's immediate group*. But the **arc** `CP→Q` is sequential:
  its logical influence path runs `CP → clkb → {ml_a,ml_b} → {sl_a,sl_b} → Q`,
  i.e. **through** both storage loops.

  These are not in conflict; they answer different questions. `arc_traverses_storage`
  answers the whole-arc question (does the path go through state?); the core's check
  answers the local question (does the output's own conduction group hold state?).
  `check_discriminator` returns **REFINE** here and prints the reconciliation rather
  than crying contradiction.

  **This is a finding worth flagging to the Build Agent (owner of L0–L2):** if a
  future cell has a *mixed* output whose own CCC contains feedback *and* a
  combinational fan-in arc, the CCC-local check is the right scope; but for the
  classic DFF `CK→Q` timing arc, whole-arc traversal is the physically meaningful
  signal. Demo 3 keeps its own arc-level discriminator rather than changing the
  core's (red line), and documents the relationship instead.

### 1.6 Tests

`tests/engine/test_seq_structure.py` — 10 tests, all passing under `python3.12`:
SDFX sequential / two loops / master-slave order / clock pin+path / CP→Q
traversal / structural-reason provenance; combinational fixtures have no storage;
discriminator AGREE on all combinational; REFINE on DFF CP→Q; determinism.

### Layer 1 ledger

- **Solid:** the SCC = state-node thesis is empirically confirmed on 6 comb + 1 seq
  fixture; clock + clock-path extraction works blind on SDFX; the discriminator
  agrees with the engine core on every combinational cell (Red Line D extended).
  All of this is test-covered.
- **Conjecture:** the *clock heuristic* ("most-loops-reached = clock") is validated
  on **one** flop. It will hold for standard single-clock DFFs/latches but is
  untested on dual-clock, gated-clock, or clock-divider cells (see open).
- **Open:**
  - Only one sequential fixture exists (SDFX, synthetic). The thesis needs a
    **real flop** from the airgap collateral to be more than a single-witness claim.
  - Master/slave labeling relies on a single influence-distance metric; cells with
    symmetric paths (e.g. a balanced latch) may tie. Untested.
  - SCC-of-size-≥2-that-are-also-gates is the right filter for cross-coupled
    inverter pairs; **C²MOS / true-single-phase-clock (TSPC)** flops store charge on
    a *dynamic* node with no static cross-couple — the SCC test would (correctly)
    find no static loop, but then the "state node" is a charge-retention node, not
    an SCC. **This is the boundary where Layer 1's structural test stops working and
    Layer 2 (charge) must take over.** Flagged as the single most important open
    question (see end of doc).

---

## Layer 2 — Charge characterization of the storage node (RESEARCH; from near-zero)

> **Boundary (ARCHITECTURE.md §8).** The engine is **not** a SPICE replacement.
> Charge work yields **relative / structural / ordering** insight — "this input can
> disturb the node by ≈X% of VDD," "this aggressor matters more than that one." It
> does **not** produce absolute setup/hold picoseconds. Absolute numbers are the
> FMC deck's job (GOAL 1). Everything below respects that ceiling.

### 2.1 The question

Layer 1 *finds* the storage node. Layer 2 asks the physical question behind
setup/hold:

> **Can an input event flip (or disturb past the metastable threshold) the storage
> node within a timing window?**

Setup/hold *is* this question in disguise: hold time is "how long must data stay
after the clock so the master commits before the path that would overwrite it
opens"; the failure is the storage node being *pulled the wrong way* by charge
redistribution before the keeper re-establishes it.

### 2.2 The substrate that already exists (not greenfield)

`engine/charge.py` (Pillar 3) already reduces the LPE parasitics into exactly the
two objects this needs (`cap_network`):

- `Cg[net]` — grounded capacitance (node-to-rail; at AC every rail is ground).
- `Cc[(lo,hi)]` — coupling capacitance between two signal nets.

and `resolve_checked(free_groups, Cg, Cc, entry_V, fixed_V)` does a
**charge-conservation resolve**: given a set of floating nets carrying trapped
charge (`entry_V`) and fixed aggressor/rail nets (`fixed_V`), it solves the coupled
cap network for the floating-node voltages, with SPICE-free invariant checks
(residual, convex-hull bound, scalar cross-check). **This is the arithmetic engine
Layer 2 rides on.** Layer 2 contributes the *framing* — what to feed it and how to
read the answer — not the linear algebra.

### 2.3 Derivation: the disturbance model (DERIVED, first-order)

Model the storage node `s` at the instant the keeper is momentarily weak (just after
the latch goes opaque, before feedback re-asserts). Treat `s` as **floating**,
holding trapped charge `Q_s = (ΣCg_s)·V_s0`, where `V_s0` is the value it stored.
An adjacent net `agg` (data, scan, the complementary storage node, a clock) swings
by `ΔV_agg`, coupled through `Cc(s,agg)`.

Charge conservation on the isolated node `s` (no DC path while floating):

```
(Cg_s + ΣCc_s)·V_s_new  =  Cg_s·V_s0  +  Σ_k Cc(s,k)·V_k
```

For a single dominant aggressor and the rest held, the **coupling-induced shift** is

```
        Cc(s,agg)
ΔV_s = ─────────────── · ΔV_agg              ... (Eq. 2.1, DERIVED)
        Cg_s + ΣCc_s
```

This is the textbook capacitive-divider / Miller-coupling result, *but expressed in
the engine's already-extracted `Cg`/`Cc` quantities*, so it is computable from the
`.subckt` alone with **no PDK and no SPICE.**

**Reading it as a relative signal (respecting the §8 ceiling):** `ΔV_s` is not an
absolute timing number. It is a *susceptibility*: a storage node with large
`Cc/(Cg+Cc)` to a fast-switching neighbor is *structurally more disturbable*, i.e.
its hold margin is structurally tighter. The engine's job is to **rank** nodes/arcs
by this susceptibility and to flag when two cells the kit treats identically have
*different* susceptibility — never to emit a hold time in ps.

### 2.4 Hand-worked example — SDFX master node (real fixture numbers)

From `cap_network(SDFX)` (computed, verbatim):

```
Cg[ml_a] = 1.2e-18 F   Cg[sl_a] = 1.1e-18 F   Cg[Q] = 2.0e-18 F
Cc[(ml_a, sl_a)] = 3.4e-19 F      (the only coupling cap in the cell)
```

Scenario: the master has just gone opaque holding `ml_a` at `VDD = 0.45 V`; the
keeper is momentarily weak (Layer-1 "broken feedback" instant). The slave node
`sl_a` is the aggressor, swinging `0 → VDD`.

Apply Eq. 2.1 (and cross-check with `resolve_checked`, which agrees to 6 digits):

```
ΔV_ml_a = Cc/(Cg_ml_a + Cc) · ΔV_agg
        = 3.4e-19 / (1.2e-18 + 3.4e-19) · 0.45
        = 0.0993 V   ≈ 22.1% of VDD
```

`resolve_checked` independently: `ml_a` floats from `0.351 V` (aggressor low) to
`0.450 V` (aggressor high) — a **0.0994 V** swing, matching the closed form. All
three SPICE-free invariants PASS.

**Interpretation (relative, not absolute):** a full-swing slave event can push the
floating master ~22% of the way across the rail. That is a *non-trivial structural
susceptibility* — enough that this node's hold behavior is coupling-sensitive and
should be characterized, not assumed. The engine states the **ordering claim** ("22%
is large relative to a node with, say, 2% coupling"), and stops there. It does **not**
claim "therefore hold = N ps."

### 2.5 From disturbance to a setup/hold *structural* statement (CONJECTURE)

The step from §2.4's instantaneous `ΔV_s` to a *window* statement is where the
research genuinely begins, and where I mark conjecture explicitly:

- **Conjecture C1 (flip threshold):** `s` is at risk of an unwanted flip when the
  accumulated coupling shift drives it past the cross-coupled pair's metastable
  point, ≈ `VDD/2` for a symmetric keeper. So a *structural hold-risk flag* is
  `ΔV_s ≳ |V_s0 − VDD/2|`. For §2.4: `|0.45 − 0.225| = 0.225 V` vs `ΔV_s = 0.099 V`
  → below threshold → *single* coupling event does not flip it, but two correlated
  aggressors might. **This is a plausibility argument, not a proof; the metastable
  point is keeper-strength-dependent and the engine has no transistor strengths.**
- **Conjecture C2 (window via RC ordering):** the *time* the node stays floating
  (and thus vulnerable) is set by the keeper re-assertion RC. The engine can compute
  a **relative** RC (`Cg+Cc` over a topological on-resistance count from the CCC
  path length) and use it to **order** which arcs have the longest vulnerable window
  — never to emit the window in seconds.
- **What is explicitly NOT claimed:** any absolute setup or hold time; any
  metastability-resolution-time number; correctness of C1's threshold without
  transistor strengths.

### Layer 2 ledger

- **Solid / DERIVED:** Eq. 2.1 (coupling divider in the engine's own `Cg`/`Cc`); the
  §2.4 worked number (0.099 V, 22% of VDD) — both the closed form and the
  independent `resolve_checked` solve agree, invariants PASS. The *relative
  susceptibility* framing is sound and within the §8 ceiling.
- **Conjecture:** C1 (flip threshold ≈ VDD/2) and C2 (RC-ordered vulnerability
  window). Both are reasonable first-order arguments; neither is validated against
  SPICE or silicon.
- **Open:**
  - The model assumes the node is cleanly *floating* at the analyzed instant; a
    real keeper is weak-but-on, so Eq. 2.1 *over*-estimates `ΔV_s`. Bounding the
    error needs a transistor on-conductance estimate the engine deliberately lacks.
  - No transistor strengths ⇒ the metastable point and keeper RC are *structural
    proxies*, good for ordering, not for thresholds.
  - The whole layer is exercised on **one** coupling cap in **one** synthetic cell.
    A real flop has dozens of parasitics; whether Eq. 2.1's single-dominant-aggressor
    reduction stays useful at that density is untested.

---

## Layer 3 — Cell fingerprint (CONCEPT + hand-computed sketch)

> A **framework + concept demo**, not a working system (ARCHITECTURE.md §5, §8).

### 3.1 Purpose

The fingerprint is the **atom for pattern discovery**: a structural+behavioral
signature such that **isomorphic fingerprints ⇒ likely the same structural class**,
and therefore **divergent kit treatment between two isomorphic cells is a suspicious
signal** (the kit may have under-characterized one of them). This is the sequential
analogue of the combinational partition-adequacy hook (Red Line F).

### 3.2 Proposed schema (the invariants, and *why each*)

A fingerprint is a tuple of **rename-invariant** structural facts (it must not
change if nets are renamed — the whole point is to match across cells):

| Field | Source | Why it is an invariant of the structural class |
|-------|--------|------------------------------------------------|
| `n_state` | Layer 1 | number of storage loops (1 = latch, 2 = master/slave FF). A class-defining count. |
| `loop_sizes` | Layer 1 | sorted SCC sizes (2 = simple cross-couple; >2 = gated/C²MOS keeper). Distinguishes keeper styles. |
| `clock_fanout` | Layer 1 | how many loops the clock reaches (1 = single-latch, 2 = full FF). |
| `clock_depth` | Layer 1 | length of `clock_path` (0 = direct, 1 = one buffer/inverter `clkb`, …). Inversion structure of the clock. |
| `n_data_inputs` | Layer 1 | primary inputs that reach a storage loop but are not the clock (1 = DFF, 2 = scan-mux DFF, …). |
| `output_polarity` | switch-level eval | does the slave drive Q true or inverted? (Q vs QN cells.) |
| `couple_sig` | Layer 2 | sorted, *quantized* coupling susceptibilities `round(Cc/(Cg+Cc), 1)` per storage node. The **behavioral** half: two cells identical in structure but different in `couple_sig` are a same-structure-different-RC pair — exactly the Demo-2 / partition-adequacy target, lifted to sequential. |

The first six are **purely structural** (Layer 1, solid). The seventh is the
**charge signature** (Layer 2, as-far-as-it-goes — quantized coarsely on purpose, so
it carries ordering information without pretending to absolute precision).

### 3.3 Hand-computed fingerprint — SDFX

From the Layer 1 + Layer 2 results above:

```
fingerprint(SDFX_LPE_PLACEHOLDER) =
  n_state         = 2
  loop_sizes      = [2, 2]          # two simple cross-couples
  clock_fanout    = 2               # CP reaches both loops
  clock_depth     = 1               # CP -> clkb -> loops (one buffer)
  n_data_inputs   = 2               # D and SI reach the master (scan-mux DFF)
  output_polarity = (derivable via switch-level eval; not computed here)
  couple_sig      = [0.2]           # round(0.34/(1.2+0.34),1)=0.2 on ml_a;
                                    # sl_a has the same single coupling cap
```

Read: this is a **2-state, scan-input, clock-buffered, simple-cross-couple FF** with
one non-trivial coupling susceptibility. The schema captures exactly the facts that
would let it be matched against a *real* scan-DFF from the library.

### 3.4 Intended use (the pattern-discovery seed)

1. Compute the fingerprint for every sequential cell in the library (Layer 1 is
   already library-runnable; Layer 2 quantized field is cheap).
2. **Bucket by the structural fields** (`n_state, loop_sizes, clock_fanout,
   clock_depth, n_data_inputs`). Cells in one bucket are the same structural class.
3. Within a bucket, **flag pairs whose kit treatment diverges** (different `-when`
   coverage, different arcs characterized, different `couple_sig` despite identical
   structure). That flag is the sequential partition-adequacy signal — the
   higher-value verdict, the seed of "the kit treated two structurally-identical
   cells differently; one is probably under-characterized."

### Layer 3 ledger

- **Solid:** the six structural fields are all computed by Layer 1 today and are
  rename-invariant; the SDFX fingerprint above is real (hand-computed from working
  output).
- **Conjecture:** that fingerprint *isomorphism* is a reliable proxy for "same
  structural class," and that divergent kit treatment within a bucket is a useful
  flag. Plausible and motivated by the combinational analogue, but **demonstrated on
  zero real pairs** — there is only one sequential cell available.
- **Open:**
  - No second sequential cell to test matching/bucketing against. The whole
    pattern-discovery claim is currently a framework with N=1.
  - `couple_sig` quantization (round to 0.1) is a guess; the right granularity is an
    empirical question once real coupling distributions are seen.
  - `output_polarity` and the C²MOS/dynamic-node case (Layer 1 open) would each add
    a field; the schema is provisional.

---

## The single most important open question

> **Does the SCC = state-node thesis survive contact with a *real* flop, and what
> replaces it for dynamic (C²MOS / TSPC) storage that has no static cross-couple?**

Everything in Layer 1 is validated on exactly one *synthetic* sequential cell, and
the structural SCC test is *defined* for static cross-coupled keepers. A dynamic
flop stores its bit as **trapped charge on a high-impedance node** with no static
feedback loop — the SCC test will find no loop, and the "state node" becomes a
*charge-retention* node that only **Layer 2** can identify (a node that is floating
during a clock phase and whose value must be preserved). Resolving this is the hinge
on which Demos 3's depth turns: it is simultaneously the Layer-1 boundary, the
Layer-2 reason-to-exist, and the prerequisite for a fingerprint schema that
generalizes beyond classic DFFs. It needs **one real flop's `.subckt`** from the
airgap collateral (Layer 1 runs blind on it; no template.tcl — Red Line A) to move
from N=1 to a defensible claim.
