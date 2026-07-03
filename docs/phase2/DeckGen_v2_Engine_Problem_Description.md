# DeckGen v2 — Core Engine Problem Description

*Engineering specification for development. Audience: Claude Code (and the developer driving it).*
*Status: foundational spec. This document defines the problem, the boundaries, and the acceptance contract — not the implementation.*

---

## 1. Purpose and thesis

DeckGen v2 is a next-generation standard-cell **characterization deck engine**. It produces the
SPICE decks that a characterization tool simulates to extract timing data.

It exists to prove **one** claim that has not been demonstrated before:

> **A timing arc's *sensitization* and *initialization* can be derived automatically from the
> cell's transistor-level topology — without relying on cell-name conventions — and every
> generated deck can carry machine-checkable evidence that the derivation is correct.**

Everything in this engine serves that claim. A feature that does not produce evidence for it,
or that re-implements something already solved elsewhere, is out of scope.

### Relationship to prior work
- **MCQC** (the incumbent flow) does sensitization and initialization too, but encodes them as
  ~850 cell-name pattern rules plus fixed per-arc templates. It produces a result; it provides
  no mechanism to verify that the result was set up correctly.
- **DeckGen v1** reproduces MCQC's decks by the same name-driven approach. Useful internally,
  but it only does what MCQC already does. It is **not** part of this engine and is not a
  reference target for v2.

v2's difference, stated precisely: **v1 reproduces MCQC's answer; v2 derives sensitization and
initialization independently from topology and proves them.**

---

## 2. Scope

### In scope — the core engine pipeline
```
netlist → device graph → CCC decomposition → sensitization derivation
        → initialization derivation → deck generation → verification harness
```

### Explicitly out of scope (do not build, do not modify)
- **Measurement.** The physical measurement definitions and their implementation — delay
  check, slew check, constraint bisection, etc. — are owned by the characterization tool
  (Liberate) and assembled correctly by the existing flow. The engine **passes the measurement
  block through unchanged**. It does not redefine, reimplement, or "improve" any measurement.
  Measurement is a mature, correct layer with no pain point. Treat its interface as fixed.
- **The v1 name-based path.** Not extended, not used as an oracle.
- **GUI, multi-PDK abstraction, Spectre backend, .lib assembly.** Later, not now.

### The boundary, in one line
The engine owns **how the arc is set up and proven** (sensitization + initialization +
verification). It does **not** own **what is measured** (Liberate's domain) or **how decks were
historically named** (MCQC's domain).

---

## 3. Terminology (precise definitions — read before implementing)

These two terms are the heart of the engine and are routinely conflated. They answer different
questions about the same goal: *making the arc actually occur, correctly, in simulation.*

### Sensitization
**Making the measured path the only active path.** A cell has many possible signal paths; an
arc is one specific input-transition-to-output-response path. Sensitization holds every
**non-measured side input** in the static bias that turns competing paths *off* and leaves the
measured path *on*.
- Governs: **side pins**, **static**, **logical**.
- In MCQC's rules this surfaces as the `when` condition (e.g. `when !I1` on a 2:1 mux: to
  measure the I0 path, the I1 path must be held off).
- Verifiable by Boolean reasoning / SAT: prove the chosen biases sensitize the target arc and
  mask all others.

### Initialization
**Putting the cell in the correct starting state before the measured transition.** Sequential
cells hold internal state. To measure a transition, the internal state-holding nodes must
already sit at the value the measured edge needs as its starting point.
- Governs: **internal state nodes**, **dynamic**, **physical**.
- Established by three mechanisms that must agree (this is the subtle part):
  1. **`.nodeset` / `.ic`** — a value asserted at t = 0.
  2. **Multi-cycle pre-cycle waveform** — earlier stimulus cycles walk the cell into the
     target state. The measured transition happens on a *later* cycle; the earlier cycles are
     pre-conditioning. *Initialization is partly hidden here, not only in `.nodeset`.*
  3. **Measurement timing** — `cross` / `td` offsets select which late cycle is the measured
     one, implicitly defining how many cycles are pre-cycle.

**One-line distinction:** sensitization decides *which path is live* (side pins, static,
logical); initialization decides *where the cell starts* (state nodes, dynamic, physical).

### Supporting terms
- **Arc** — a `(rel_pin/dir, constr_pin/dir, arc_type, when, measurement)` definition; the
  unit of characterization. Input to the engine is one arc on one cell.
- **CCC (channel-connected component)** — a group of transistors connected through
  source/drain channels. The standard transistor-level partitioning unit; used to find the
  real state-holding nodes structurally instead of by name wildcard.
- **Drive-and-settle** — establishing the initial state by *driving the pins* with a stimulus
  that walks the cell into the target state and lets it settle, then probing to confirm —
  rather than asserting it with `.ic` and hoping the DC solve lands in the right basin.
- **Pre-cycle** — the pre-conditioning portion of the stimulus before the measured edge.

---

## 4. The problem being solved

For a given `(cell, arc)`, the current name-driven approach has three structural limits the
engine must overcome:

1. **It cannot handle a cell it has no rule for.** A cell whose name does not match the rule
   patterns falls back silently or is set up by the closest-matching template. Sensitization
   and initialization are only as correct as the name-to-template guess.
2. **It does not derive — it looks up.** The required side-pin biases and initial state come
   from a fixed template chosen by name, not computed from what the arc and the topology
   actually require.
3. **It cannot prove it is right.** There is no check that the sensitization actually isolates
   the arc, or that the cell actually reached the intended state before the measured edge.

The engine replaces *look-up by name* with *derive from topology*, and adds *proof* where there
was none.

---

## 5. Engine architecture (pipeline stages)

Each stage has a single responsibility, a typed input, and a typed output. Stages are
independently testable.

| Stage | Input | Output | Responsibility |
|-------|-------|--------|----------------|
| **0. Parse** | netlist (`.subckt`) | device graph (transistors, nets, terminals) | Build a structural model of the cell. No PDK-specific assumptions. |
| **1. CCC decomposition** | device graph | components + **identified state-holding nodes** | Partition by channel connectivity; locate the real storage nodes (feedback loops / cross-coupled pairs) — structurally, not by name. |
| **2. Sensitization derivation** | device graph + arc | side-pin biases + **proof obligation** | Compute the static bias on every non-measured input that turns the target path on and competing paths off. Emit the obligation for P1. |
| **3. Initialization derivation** | CCC state nodes + arc | per-node required start state + **drive-and-settle stimulus** + pre-cycle | For the measured transition, compute each state node's required pre-edge value; synthesize a stimulus that walks the cell there and a settle interval; place probes for P2. |
| **4. Deck generation** | stages 2–4 outputs + measurement block | SPICE deck | Assemble sensitization biases, init stimulus + probes, and the **passed-through measurement block** into a valid deck. |
| **5. Verification harness** | generated deck + simulation result | P1/P2/P3 verdicts | Run the machine checks defined in §6 and emit a structured verdict per deck. |

The measurement block enters at Stage 4 as an opaque, pre-formed unit (Liberate's
configuration). The engine positions it; it does not author it.

### 5.1 Build on existing work before writing new code
Several stages correspond to techniques that already exist in published work or open-source
code. **Survey and reuse before implementing from scratch.** Specifically, look for and evaluate:
- **Netlist / SPICE parsing** — mature open-source parsers exist; do not hand-roll one.
- **CCC (channel-connected component) decomposition** — a standard transistor-level
  partitioning; look for existing graph/EDA implementations rather than inventing the algorithm.
- **Boolean / SAT reasoning for sensitization (P1)** — leverage an existing SAT solver and, if
  available, published arc-recognition approaches (e.g. Boolean-difference methods).
- **Device-graph / circuit-graph libraries** — for the structural model in Stage 0–1.

For each, the engine should record what was found, what was adopted, and what had to be built
(and why). The novel contribution is the **composition** — deriving sensitization and
initialization from topology and proving them per deck — not re-implementing solved primitives.

---

## 6. Acceptance contract (mandatory per-deck output)

Every generated deck **must** produce a structured verdict on three properties. This contract
replaces byte-equality with golden files (we explicitly do **not** require byte-equality —
matching MCQC byte-for-byte would only reproduce its unverified assumptions).

- **P1 — Sensitization correct.** The chosen side-pin biases sensitize the target arc and mask
  all competing paths. *Check:* Boolean/SAT over the device graph. *Output:* `PASS/FAIL` +
  the masked paths.
- **P2 — Initial state correct.** At the end of the pre-cycle, the CCC state nodes sit at the
  derived required values (within a VDD/2 threshold). *Check:* probe internal nodes in the
  simulation at the settle point and compare to the derivation. *Output:* `PASS/FAIL` + per-node
  measured vs. expected.
- **P3 — Measurement context consistent.** The measurement window, probe, and metric are
  consistent with the arc and the observed settling (the cell is in steady state when the
  measured edge fires). *Output:* `PASS/FAIL` + the window/edge alignment.

A deck that cannot produce all three verdicts is incomplete by definition. P2 is the property
the incumbent flow cannot provide today and is the engine's central contribution.

---

## 7. Architecture and environment constraints (binding)

The development environment forces these constraints. They are not optional and must shape the
design from the first commit.

1. **Air-gapped production environment.** The real characterization server has no outbound
   network. Files enter via file-share zip; results leave only as terminal screenshots. Real
   netlists, real PDK models, and real golden data **cannot be brought out**.
2. **Develop on synthetic data; validate on real data with the same code.** All local
   development and testing use **self-authored representative netlists** with generic MOS
   models — topologically faithful, PDK-free. Real cells run the **identical engine** on the
   server. No code path may depend on a real PDK to be exercised locally.
3. **Thin data-access boundary.** Anything that touches a real artifact (netlist source, model
   include, corner data) goes through one narrow interface with two implementations: a
   `fixture` backend (local, synthetic) and a `real` backend (server). Swapping them changes a
   config value, never engine logic.
4. **The engine self-reports; feedback is screenshots.** Because intermediate results return as
   screenshots rather than full file trees or long logs, every stage must emit **compact,
   structured, self-describing status** — stage name, key derived values, and PASS/FAIL — that
   fits on a screen. The harness prints the P1/P2/P3 verdict as a small structured block, not a
   wall of SPICE output. Assume the developer cannot paste large outputs back.
5. **Deterministic and inspectable.** Given the same inputs, output is reproducible. Every
   derived value (a state node's required start, a side-pin bias) carries its derivation reason
   in the output, so a screenshot alone is enough to judge correctness.

---

## 8. Data strategy

- **Local fixtures:** a small library of hand-authored `.subckt` netlists covering the target
  structures (see §10), each with a generic transistor model. These are the unit/integration
  test inputs. They live in the repo.
- **No real PDK locally, ever.** If a test needs model parameters, it uses generic ones.
- **Server runs** point the `real` backend at actual collateral; the same tests/asserts run
  against real cells and the verdicts are read off the screen.
- **The arc** is supplied as a `define_arc`-style record (the §3 arc fields). Local fixtures
  ship with hand-written arcs; real runs use the real `define_arc`.

---

## 9. First worked example — SDF (scan D flip-flop), `hold(CP, D)`

The first implementation milestone. Chosen deliberately: a scan flop exercises **both** core
concepts in one cell (the scan mux forces a real sensitization decision; the master-slave latch
forces a real initialization decision), and a **hold constraint arc** — not a delay arc — puts
**initialization at the center**. A delay arc (e.g. `CP→Q`) is a combinational propagation
measurement where the starting state matters relatively little; a hold arc requires the latch to
already hold a known value before the data edge, so getting the initial state right *is* the
problem. This is the arc that makes property **P2 (initial state correct)** load-bearing.

**Cell.** Scan D flip-flop. Functional input `D`, scan input `SI`, scan enable `SE`, clock
`CP`, output `Q`. Internally: an input mux (`SE` selects `D` vs `SI`) feeding a master-slave
latch pair (two cross-coupled storage nodes).

**Arc.** `hold(CP, D)` — the hold constraint of data `D` relative to clock `CP`: after the
capturing `CP` edge, how long `D` must stay stable before it is allowed to change without
corrupting the captured value. `rel_pin = CP`, `constr_pin = D`, `arc_type = hold`,
`when = SE` selects the functional path.

What each stage must produce for this example:

- **Stage 1 (CCC):** identify the master and slave storage nodes structurally (the
  cross-coupled pairs), not by matching `*Q*` or `ml*`.
- **Stage 2 (sensitization):** derive that `SE` must be held to select the **functional `D`
  path** (scan off) and `SI` held to a non-interfering value, so the hold being measured is the
  one through the functional data path, not the scan path. Emit the P1 obligation proving the
  `D` path is the live capture path and the `SI` path is masked.
- **Stage 3 (initialization):** for the hold measurement, derive the known value the latch must
  hold going into the capturing edge and the `D`/`CP` sequence that establishes it — i.e. the
  master must capture a defined value on the relevant `CP` phase, and the slave/`Q` must hold the
  prior known value. Synthesize a drive-and-settle pre-cycle that walks the flop into that
  defined held state, then the capturing `CP` edge followed by the `D` change whose timing the
  hold check bisects. Place probes on the master and slave nodes for P2.
- **Stage 4 (deck):** assemble the `SE`/`SI` biases, the pre-cycle stimulus + probes, the `CP`/`D`
  edge sequence, and the passed-through hold-measurement block into a deck.
- **Stage 5 (verify):** P1 confirms the scan mux selects `D` and masks `SI`; P2 confirms master
  and slave probed at the derived held values after settle (before the capturing edge); P3
  confirms the `CP` capturing edge and the `D` constraint edge are placed in a steady, settled
  context consistent with a hold check.

**Definition of done for the milestone:** running the engine on the SDF fixture for
`hold(CP, D)` emits a complete deck and a P1/P2/P3 verdict block, with every derived value
carrying its reason — judged reasonable on a single screen, with no real PDK involved.

---

## 10. Roadmap — stress cases (after the SDF milestone)

Each later case stresses a different axis of the core claim. They are validation targets, not
new features.

1. **`sync(N)` × min_pulse_width** — stresses **initialization via multi-cycle pre-cycle /
   settling**. The hardest case for the "init hidden in waveform + timing" mechanism; its
   complexity is invisible in name-based metadata.
2. **`ckgmux2` × nochange** — stresses **sensitization breadth** (most side-pin conditions) and
   **multiple internal state nodes** in one deck (clock-gate + mux interplay).
3. **`retn` × nochange/removal** — stresses **state depth and arc-type breadth** (retention
   latch across sleep/set/reset; the widest arc coverage).

Customized / non-standard-named cells are an **application** of the engine (the name-blind
derivation handles them for free), not a development target in their own right.

---

## 11. Non-goals (restated to keep focus)

- Not reproducing MCQC byte-for-byte.
- Not authoring or modifying any measurement (delay/slew/constraint) logic.
- Not extending the v1 name-based engine.
- Not supporting real PDKs in local development.
- Not building GUI / multi-backend / .lib assembly in this phase.
