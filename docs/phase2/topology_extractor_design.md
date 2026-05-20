# Topology Extractor -- Detailed Design

Status: design draft on `feature/topology-intelligence-agent-review`
Companion doc: `topology_agent_intelligence.md` (broader agent concept)
Worked example: `AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD`

## 1. Scope and Position

The topology extractor is the component of the agentic DeckGen flow that
turns a previously-unseen cell + arc spec into a structured, reviewable,
reusable topology schema. It is the most intelligence-heavy and the most
valuable single piece of the flow, but it is one component of a larger
agentic system, not the whole system.

The rest of the eventual agentic flow:

- A planner agent that expands the target matrix into jobs.
- The principle engine (deterministic, ~60 family target) as the first
  attempt -- fast path for known cells.
- This extractor -- slow path, runs only when the principle engine cannot
  classify or selects with low confidence.
- A reviewer-facing agent that surfaces extractor proposals with the
  evidence and lets a human accept / reject / request more evidence.
- A KB curator agent that maintains the accepted-schema knowledge base
  and its retrieval indices.
- A cross-project query agent that serves the schema KB to AIQC,
  lib_char_auto, and other learning projects.

This document covers only the extractor. The boundary is precise:
**in = (cell SPICE netlist, define_cell, define_arc, char.tcl overrides,
arc spec, optional historical sim result); out = (TopologySchema with
confidence + evidence hash).**

What the extractor does not do: deck assembly, simulation execution,
review workflow management, KB persistence (it queries the KB but does
not write to it; the curator agent writes).

## 2. Problem Statement

### 2.1 The current surface

DeckGen's principle engine compresses MCQC's 18K-line if-chain into a
manageable family registry. The compression numbers, derived from the
current Phase 2 effort:

- MCQC produces 854 rules (extracted into `config/template_rules.json`)
  that route arc specs to 63 SPICE template files in
  `templates/N2P_v1.0/`.
- The principle engine target is ~60 families that cover the same
  surface with parameterized templates rather than name-pattern
  matching.
- The bootstrap MVP in `core/principle_engine/families.py` has 16
  entries as of the snapshot; production work extends this toward the
  ~60 target.

This compression handles the surface of **known** cells across the
current dataset. The problem the extractor solves is what happens
outside that surface.

### 2.2 Three classes of unseen cells

Cells that fall outside the principle engine's coverage break into
three classes, each with different frequency and treatment
characteristics:

**Class A -- Genuinely novel topology.** New compound gates, new
sequential variants (e.g., a SYNC depth not yet in the registry, a new
retention mode), new vendor cells with non-standard internal
structure. Frequency: tens to low hundreds per new PDK node bring-up.
The classifier's `CellClass.UNKNOWN` branch typically triggers here.

**Class B -- Naming variants of known topology.** Same internal
structure as an accepted family, but cell name tokens or pin naming
differ enough that the classifier's regex patterns miss. Frequency:
dozens per vendor library release. These are nominally tractable by
extending regex patterns, but each extension carries regression risk
and adds to the same drift the principle engine is trying to avoid.

**Class C -- Same cell, new arc type or new corner.** A cell already
characterized for delay arcs needs setup/hold or min_pulse_width
characterization; or a previously characterized cell needs
re-characterization at a corner where measurement behavior differs.
Frequency: a few per characterization scope expansion. The cell
classification is known; the arc-specific parameter binding and
measurement context are the new work.

### 2.3 Today's path: hand-authoring

For all three classes, the current path when the principle engine and
v1 rule-chain both miss is hand-authoring by an experienced engineer.
The engineer does six things:

1. Opens the cell's SPICE netlist and visually parses the channel
   connected component structure.
2. Decides which input pins are clock, data, scan, reset, etc.
3. Identifies state-holding loops and computes required `.ic` /
   `.nodeset` count.
4. For a given arc, derives the active transistor path and sensitizing
   state of side pins by hand.
5. Chooses measurement strategy, output load policy, glitch and
   pushout watchouts.
6. Writes or modifies a SPICE template file, parameterizes it,
   registers it in the family or rule registry, validates against
   MCQC byte-equal regression.

The wall-clock cost is 1-3 days per cell, dominated by SPICE
inspection and trial-and-error simulation. The output -- a new family
entry plus possibly a new SPICE template -- is the only artifact that
persists. The engineer's analysis lives only in their head.

The consequence: a second engineer encountering a structurally similar
cell repeats most of the work. There is no mechanism to inspect the
prior engineer's analysis, no record of what alternatives were
considered, no captured evidence beyond the final family entry. This
is the same drift mode that produced MCQC's 18K-line if-chain over a
decade.

### 2.4 What the extractor changes

The extractor converts hand-authoring into structured extraction. For
every (cell, arc) tuple it processes, it produces a TopologySchema --
an inspectable, persistable, reviewable artifact -- with the evidence
used to derive each part of the schema attached.

The reviewer's role transforms: rather than performing the analysis
from scratch, the reviewer **inspects** the extractor's analysis,
spot-checks the evidence, accepts or rejects with rationale. The
extractor handles the mechanical 80%; the reviewer applies judgment to
the remaining 20%.

The accepted schema becomes a durable artifact. The next structurally
similar cell that arrives finds its predecessor in the KB, and the
extractor's confidence on the second cell is higher because retrieval
finds an anchor.

This is the core mechanism by which the extractor makes work
**accumulate**, which is the property hand-authoring lacks.

### 2.5 What the extractor explicitly does not solve

- The principle engine's job of covering the known surface remains
  the principle engine's responsibility. The extractor does not
  subsume or replace the family registry.
- Deck assembly, simulation execution, and byte-equal regression
  remain in DeckGen's existing components.
- Cell-level functional verification (LVS against schematic, formal
  equivalence to a behavioral model) is out of scope. The extractor
  characterizes structure for simulation purposes; it does not
  certify cell correctness.
- Numerical timing prediction (delay, slew, leakage value prediction)
  is out of scope. The extractor's qualitative speed class is for
  measurement window sizing, not for replacing SPICE.

### 2.6 Why the problem is hard

Items 1 and 3 in the hand-authoring list are graph algorithms with
known solutions -- they are tractable individually. Items 2, 4, and 5
require domain reasoning that combines structural graph analysis,
Boolean function derivation, electrical intuition about pull-up /
pull-down speeds and glitch sensitivity, and accumulated experience
about measurement risks.

The combination is what makes hand-authoring slow. A graph algorithm
can find CCCs deterministically, but interpreting which CCC's internal
loop is a master latch vs a keeper requires judgment. A SAT solver
can derive Boolean functions, but mapping a Boolean function to
"this is a scan flop because of the 2-input mux on D" requires
pattern recognition over prior cells. An expert does both kinds of
reasoning fluently and interleaved.

The extractor's design encodes this seam explicitly: deterministic
algorithms produce the structural and logical facts; LLM reasoning
with external verification adds the judgment. Each layer's output is
inspectable; each layer is replaceable without disturbing the others.

## 3. Application Scenarios

Four primary scenarios drive the extractor's design. Each has
different latency, throughput, and reviewer-loop characteristics. The
extractor must serve all four; the architecture in Section 7 is
constrained by this.

### 3.1 Scenario S1 -- New node bring-up

**Trigger.** A new PDK node arrives. A batch of cells (typically
50-200) are structurally novel either because the node uses new
device parameters that change the channel network, or because the
standard cell library was redesigned, or because a new vendor entered
the library.

**Inputs available.** Full collateral set is staged: SPICE netlists,
template.tcl with define_cell and define_arc, char.tcl overrides.
Historical simulation results are typically not available yet -- this
is the first characterization pass.

**Latency target.** Offline batch. The bring-up window is typically
2-4 weeks; producing extractor schemas for the full batch within the
first 48 hours is appropriate, leaving 1-3 weeks for reviewer
turnaround.

**Throughput target.** 50-200 (cell, arc) tuples per batch run.
Stages must be parallelizable per-(cell, arc) -- no global lock or
shared mutable state that serializes batch members.

**Reviewer workflow.** Schemas land in `reviews/proposed/` or
`reviews/needs_more_evidence/`. Domain experts review in priority
order, typically driven by which cells block downstream IP
characterization. Accepted schemas accumulate in the KB at a rate of
10-30 per reviewer-day during bring-up phase.

**How extractor output is consumed.** Directly by the reviewer-facing
agent. Once accepted, schemas can feed the principle engine's registry
as new family proposals. DeckGen can then characterize the original
cells using either the new family entry or the accepted schema in
experimental mode.

**Design implications.** Batch idempotency: re-running the batch over
the same input should produce schemas with the same evidence bundle
hashes, so reviewers can re-run with confidence after fixing bugs.

### 3.2 Scenario S2 -- New cell variant on existing node

**Trigger.** Vendor releases an incremental library update. A handful
of new cells (typically 1-10) appear that are structurally similar to
existing accepted cells but differ in pin count, drive strength
scaling, or compound gate fan-in.

**Inputs available.** Same as S1, plus a populated KB from prior
bring-up.

**Latency target.** Inline (triggered by principle engine
SelectionError) or offline (next batch run). Inline mode is preferred
when the new cell is blocking an active characterization run;
offline is fine when the new cell appears in advance of need.

**Throughput target.** Low absolute volume but turnaround in hours
(offline) or seconds (inline).

**Reviewer workflow.** KB retrieval should find structurally similar
accepted schemas with high similarity, typically above 0.85 on
canonical signature. The reviewer often accepts a `delta proposal` --
extractor identifies that the new cell maps to an existing family
with a small extension (e.g., one new pin, slight network change),
reviewer confirms.

**How extractor output is consumed.** When the delta is small, the
reviewer may approve direct admission of the new cell into the
existing family (extending the family's `param_schema`) rather than
creating a new family entry. The extractor schema's
`proposed_principle_family.status` field carries this hint:
`new_proposal` vs `extension_of_existing`.

**Design implications.** Stage B and Stage C must be able to consume
prior accepted schemas as in-context anchors and produce explicit
diff output, not just absolute schema output.

### 3.3 Scenario S3 -- Same cell, new arc type or corner

**Trigger.** A cell already characterized for delay arcs needs
setup / hold / min_pulse_width characterization, possibly because IP
integration requires constraint arcs not previously needed. Or, the
cell is already characterized but needs re-characterization at a new
corner where convergence or measurement behavior may differ.

**Inputs available.** Same as S1 and S2, plus prior accepted
schemas from earlier arc types on the same cell.

**Latency target.** Inline. This scenario typically appears during
an active characterization run, blocking specific arcs from being
generated.

**Throughput target.** Single (cell, arc) tuples on demand.

**Reviewer workflow.** Stage A and Stage B output can be reused from
prior accepted schemas on the same cell. Only Stage C (arc projection)
and Stage D (measurement context) need fresh derivation. The reviewer
sees a much smaller diff against prior accepted schemas, which speeds
review.

**How extractor output is consumed.** Same as S1 once accepted; the
new arc's `param_binding` extends the cell's coverage in the principle
engine.

**Design implications.** Stage outputs must be independently
addressable and versioned. A schema must be loadable as
`{cell, structural, functional}` for re-use without reloading
`{arc_projection, measurement}`.

### 3.4 Scenario S4 -- Cross-project KB query

**Trigger.** A consumer outside DeckGen (AIQC's Feature Analysis
Agent, lib_char_auto's sampling planner, a future learning project)
needs structural or measurement-risk information about cells.

**Inputs available.** KB only. No fresh evidence bundle is provided.
The query is a structural similarity question or a feature lookup.

**Latency target.** Online, sub-second response for typical queries;
under five seconds for large queries (e.g., "for the top 100 cells
by Stage C confidence, return their measurement_risk levels").

**Throughput target.** Hundreds of queries per day initially; design
for scaling to thousands per day as adoption grows.

**Reviewer workflow.** None. The KB is read-only from the query
agent's perspective.

**How extractor output is consumed.** Indirectly. The extractor's
output (accepted schemas) is what the KB serves. The extractor itself
does not run for S4; only the KB curator agent and a separate query
agent do.

**Design implications.** The schema's `learning.reusable_features`
and structural fields must be cross-project-stable. Schema versioning
must be field-level, not just whole-schema, so that AIQC consumers
can declare which fields they depend on and the KB curator can warn
before breaking them.

### 3.5 Cross-cutting constraints from scenarios

The four scenarios together impose:

- **Batch and inline parity.** No global state that batch mode
  assumes but inline mode lacks. Each stage must be both batchable
  and invocable on a single (cell, arc).
- **Per-stage skipping with prior-schema reuse.** Each stage's
  output must be independently versioned, hashable, and re-usable.
- **Field-level schema versioning** for cross-project stability.
- **Deterministic re-runs.** Identical evidence bundle hash must
  produce identical schema (modulo LLM nondeterminism, which is why
  Stages B/C/D must record their LLM model id and seed when used).

## 4. Success Metrics

Five categories. Each has a definition, a baseline, a starting
target, a six-month target, and a measurement method.

### 4.1 Novel cell coverage rate

**Definition.** Fraction of a held-out novel cell set for which the
extractor produces a TopologySchema that, after reviewer acceptance,
drives DeckGen to produce a SPICE deck that passes byte-equal
regression against the MCQC reference.

**Baseline.** Today, novel cells require hand-authoring; 100% of
novel cells eventually pass byte-equal but only after expert time.
The relevant baseline for "without extractor" is 0%.

**Starting target.** 70%.

**Six-month target.** 85%.

**Measurement.** Maintain a held-out set of 30-50 novel cells from
one or more PDK nodes that the extractor has not been trained or
KB-seeded on. Run the full pipeline; count byte-equal passes after
one round of reviewer acceptance.

**Pitfall.** KB contamination. The held-out set must be strictly held
out from KB seeding; otherwise the metric measures retrieval rather
than generalization.

### 4.2 Time-to-first-good-deck

**Definition.** Wall-clock time from "collateral for a novel cell
becomes available" to "DeckGen produces a byte-equal-passing deck for
at least one of its arcs."

**Baseline.** 1-3 days per cell (dominated by expert hand-authoring).

**Starting target.** 4 hours of reviewer time per novel cell.
Extractor runs in seconds to minutes; reviewer time is the
bottleneck.

**Six-month target.** 2 hours of reviewer time.

**Measurement.** Time-stamp logs on the reviewer-facing agent.
Wall-clock from agent-inbox arrival to accept verdict.

**Pitfall.** Cherry-picking easy cells. Use a stratified sample
across novelty types (Class A / B / C) and arc types (delay / hold /
setup / min_pulse_width / nochange).

### 4.3 Reviewer direct-accept rate

**Definition.** Fraction of extractor proposals that the reviewer
accepts without requesting additional evidence or modifying the
schema.

**Baseline.** Not applicable.

**Starting target.** 60%.

**Six-month target.** 80%.

**Measurement.** Outcome counters on the reviewer-facing agent:
`accepted_clean`, `accepted_after_evidence`, `accepted_with_edit`,
`rejected`, `needs_more_evidence`. Direct-accept rate
= `accepted_clean / (sum of all outcomes)`.

**Pitfall.** Reviewer permissiveness drift. If reviewers become
looser to hit the metric, the metric goes up while quality goes down.
Counter with periodic byte-equal regression on accepted schemas;
flag if pass rate trends down.

### 4.4 Cross-project query latency

**Definition.** P95 wall-clock latency for KB queries from
non-DeckGen consumers.

**Baseline.** Not applicable.

**Starting target.** Under 5 seconds at P95 for queries returning up
to 100 schemas.

**Six-month target.** Under 2 seconds at P95.

**Measurement.** Standard query-latency telemetry on the KB query
agent.

**Pitfall.** Latency vs index freshness. Aggressive caching can hit
latency targets while serving stale data after new acceptances.
Measure both `query_latency_p95` and `max_staleness_seconds`.

### 4.5 Per-stage health metrics

These do not feed external dashboards but feed confidence propagation
(Section 13).

**Stage A.** Percentage of CCCGraphs that satisfy all verification
properties (every transistor in exactly one CCC, every primary output
is a CCC output, loop count consistent with define_cell). Target:
99%+.

**Stage B.** SAT verification pass rate -- the algorithmically derived
Boolean function must be consistent with LLM-proposed pin roles.
Target: 100% pass at exit. If not 100%, the stage must surface the
conflict and not silently reconcile.

**Stage C.** SAT-sensitization pass rate (100% at exit). KB retrieval
hit rate (fraction of arcs that find at least one similar accepted
schema as anchor): 70% as the KB matures.

**Stage D.** Rule-table coverage rate (fraction of arcs whose
measurement guidance is fully determined by rule table without LLM
generalization). Target: 80% as the rule table is populated.

### 4.6 Explicit anti-goals

What the extractor is not optimizing for. Listing these prevents
scope creep:

- The extractor does not aim to characterize cells faster than SPICE
  simulation. Stages A-D produce a schema; deck generation and
  simulation downstream are not in the latency budget.
- The extractor does not aim to replace the principle engine's family
  registry. The registry is the fast path; the extractor handles
  misses.
- The extractor does not aim to produce SPICE-level numerical
  accuracy in its `expected_signature` field. The qualitative speed
  class is for measurement window sizing only.
- The extractor does not aim to detect functional bugs in cells. If a
  cell has a design defect, the extractor will characterize it as-is;
  defect detection is the design team's responsibility.

## 5. Literature Review

The extractor's design draws on four categories of prior art. This
section documents what is reusable, what gaps remain, and how each
extractor stage maps to specific prior work.

### 5.1 Category 1 -- Graph-based logic gate identification

Classical EDA problem: identify standard cells inside a
transistor-level netlist. Several decades of work; mature.

**ReGDS / LGE** (Rajarathnam et al., UT Austin) is representative of
the modern open-source state. The tool reads SPICE netlists and
identifies logic gates using a Digital Connectivity Index encoding of
transistor-terminal connectivity, plus a subgraph isomorphism
algorithm against a library of known gate definitions. Open-source
C++ implementation available on GitHub. Reference:
`github.com/rachelselinar/ReGDS-Logic-Gate-Extraction`.

Strength: deterministic, reproducible, handles flattened netlists.

Limitation: stops at "this is a NAND" -- does not produce arc-level
or measurement-level abstraction. Useful as a building block, not as
a solution.

**GCN-based hierarchical annotation** (Sapatnekar's group, University
of Minnesota; DATE 2020, TCAD 2023). Extends classical subgraph
isomorphism with graph convolutional networks for approximate
matching. Abstracts circuit netlists as graphs and uses GCN to
classify circuit elements into sub-blocks. Primary target: analog
circuit hierarchy recognition.

Strength: handles structural variation (parallel transistors for
sizing, dummies, decaps) that exact subgraph isomorphism rejects.

Limitation: trained primarily on analog primitives. Digital standard
cell coverage is incidental. The training-data requirement is
significant.

**Classical graph canonicalization** (nauty, Traces, Weisfeiler-Lehman
hashing). Mature; reference implementations in standard graph
libraries.

**Mapping to extractor.** Stage A's CCC canonical signature uses
Weisfeiler-Lehman hashing on the labeled series-parallel structure.
Stage B's KB retrieval uses approximate subgraph isomorphism on
CCCGraphs; GCN-style embeddings remain an option for similarity
search if the KB grows large enough to justify the training cost.

### 5.2 Category 2 -- Channel Connected Component decomposition

CCC is the EDA term for a sub-network of transistors sharing a common
output node and connecting to power/ground through transistor
channels. CCC decomposition is the canonical first step in
transistor-level analysis. Most prior art appears as patents from
commercial EDA vendors, not academic papers, because this work lives
inside commercial characterization tools.

**US Patent 10133835** -- "System and method for computationally
optimized characterization of complex logic cells." Decomposes a cell
into channel connected component portions, each with a local output
node and a transistor network establishing conduction to a power
plane. A function generation module produces a `component
characteristic function` for each CCC by summing the logic value
vectors that activate each channel path. A function expansion module
combines a CCC's local characteristic function with its upstream
CCC's. The mathematics is Boolean algebra on transistor networks:
NMOS pull-down series-parallel structure dualizes to PMOS pull-up;
node logic values propagate through CCCs in topological order.

**US Patent 6367057** -- "Method of analyzing a circuit having at
least one structural loop within a channel connected component."
Inserts boolean variable pairs at break points in loops, derives
boolean equations representing the CCC's behavior at each break
point, and solves the equation system. A single solution indicates
combinational behavior; multiple solutions indicate sequential
behavior; no solution indicates oscillation. This directly produces
the data needed to populate `ic_count by topology` -- the same table
that appears in `family_types.py` for `InitStyle.IC` distributions
(latch_S / RCB / CKG = 2, EDF = 4, MB = 8, synx = 14, syn2 = 16).

**US Patent 8655634** -- "Modeling loading effects of a transistor
network." For a load CCC, transistors that remain off during a
transition are replaced with capacitors; transistors that remain on
are replaced with RC; transistors that switch are kept intact.
Produces the qualitative speed class used for measurement window
sizing.

**Mapping to extractor.**

| Extractor capability | Patent |
|---|---|
| Stage A CCC decomposition | US 10133835 (structural approach) |
| Stage A loop detection in CCCs | US 6367057 |
| Stage B algorithmic Boolean function per CCC | US 10133835 (characteristic functions) |
| Stage B ic_count derivation | US 6367057 (single vs multiple vs no solution) |
| Stage C `path_resistance_qualitative` | US 8655634 (FET replacement model) |

**What is missing.** The patents describe CCC analysis but do not
address arc-aware projection -- Stage C's specific job of taking a
specific arc spec with a when condition and projecting the CCC
structure into the active path and sensitizing state. The integration
of CCC analysis with arc-specific parameter binding has no public
prior art, likely because it lives inside commercial characterization
tools as proprietary internal abstraction.

### 5.3 Category 3 -- Machine learning for cell library characterization

Recent body of work applying ML to cell characterization, primarily
for delay / leakage / slew numerical prediction. The relevance to the
extractor is in technique transfer rather than direct reuse of
predictions.

**Knowledge transferring framework for cell library characterization**
(ScienceDirect, December 2024). Addresses the observation that
existing ML-based cell characterization methods often neglect the
knowledge embedded across different timing arcs, requiring extensive
per-arc training data. The framework proposes a fine-grained metric
to quantify similarity among training tasks within a cell library,
enabling cross-arc transfer learning. Reported results on 45nm MOSFET
and 14nm FinFET technologies: cell delay prediction error reduced by
80% and 67% respectively over baseline.

Mapping to extractor: the arc-similarity metric concept directly
informs Stage C's KB retrieval similarity scoring. The work itself
targets delay prediction not deck generation; the predictions are not
reusable but the metric structure is.

**LiMo: Framework Leveraging Machine Learning for Multi-Input
Switching Timing Models** (IEEE TCAD, 2024). Combines SAT solvers and
ML: a logical analysis on the Boolean function of a logic gate
identifies input patterns that lead to MIS-induced speed-up; these
patterns then become the training set for ML models.

Mapping to extractor: Stage C's SAT-based sensitization analysis is
conceptually similar -- using SAT to derive the set of input patterns
that activate a given arc path. LiMo's specific contribution (MIS
modeling) is orthogonal to the extractor's goal, but its
SAT-then-ML pipeline structure is a useful template.

**Cell Library Characterization for Composite Current Source Models
Based on Gaussian Process Regression and Active Learning** (ACM/IEEE
ISLPED 2024). Representative of the ML-for-CCS workflow. Not directly
applicable to the extractor; mentioned for completeness.

**Mapping to extractor.** Stage C's KB retrieval similarity scoring
borrows from the cross-arc transfer learning framework. Stage C's
SAT-based sensitization analysis aligns with LiMo's SAT-then-ML
structure. Stage D's rule-table-plus-LLM composition does not have a
direct prior-art parallel.

**What is missing.** ML-for-char work targets numerical prediction.
It does not target structured artifact generation (the
TopologySchema). The arc-similarity metrics are conceptually reusable,
but their specific formulations are tied to delay prediction and
would need re-derivation for the extractor's structural-similarity
use.

### 5.4 Category 4 -- Sequential circuit state-node identification

Specialized prior art for identifying state-holding nodes in
transistor-level sequential circuits.

**US Patent 7246334** -- "Topological analysis based method for
identifying state nodes in a sequential digital circuit at the
transistor level." Reduces the device-level netlist to a graph
representation and identifies state nodes via minimal combinatorial
loop properties. Argued to be an order of magnitude more efficient
than alternative methods at the time of filing.

Mapping to extractor: directly relevant to Stage B's `state_elements`
population and Stage C's `init_requirements` derivation for
sequential cells (DFF, latch, retention).

### 5.5 Category 5 -- Commercial characterization tools

Cadence Liberate, Synopsys PrimeLib, and Synopsys SiliconSmart are
the production tools for cell library characterization. They
internally perform CCC decomposition, arc-aware deck generation, and
measurement strategy selection. Their internal abstractions are not
published. Public documentation describes user-facing configuration
but not the topology-to-deck mapping algorithms.

Mapping to extractor: useful as a reference for the surface of the
problem (which cells and arcs commercial tools handle, which
configuration knobs they expose) and as a benchmark target (MCQC
v3.5.5 is itself derived from commercial-tool-equivalent outputs;
byte-equal regression validates that the extractor's path produces
results indistinguishable from the commercial path). Not useful as an
algorithmic source.

### 5.6 Coverage summary

| Stage | Prior art coverage | Public algorithm available | Original work required |
|---|---|---|---|
| A: Structural decomposition | Strong | Yes (CCC decomposition, loop detection, WL hashing) | Pass-gate ambiguity handling; multi-driver net resolution |
| B: Functional naming | Partial | Algorithmic Boolean derivation: yes. Pin role assignment: no | Pin role inference; cell class proposal beyond existing taxonomy; state-element vs keeper distinction |
| C: Arc projection | None public | None | All of: active path projection, sensitizing state derivation, init requirement mapping, drive strategy selection |
| D: Measurement context | Partial | Rule extraction from MCQC: mechanical. Generalization: no | Measurement risk reasoning; glitch / pushout decision logic; feedback-loop calibration |

Three of four stages have meaningful prior art coverage. Stage C is
the most original contribution; Stage D is partially original (rule
extraction is mechanical from MCQC, but generalization beyond the
rule table requires fresh design).

### 5.7 What no one has published

The integration of these pieces -- CCC decomposition plus
arc-aware projection plus measurement-context derivation plus
KB-backed continuous learning -- as a coherent system that produces
reviewable, versioned, cross-project topology schemas is not in the
literature. The closest commercial parallels (Liberate, PrimeLib) are
proprietary. The closest academic work (cross-arc transfer learning,
SAT + ML) addresses single sub-problems.

This is the extractor's substantive contribution: not any single
stage, but the composition with the verification discipline between
stages.

## 6. Input Contract

For each (cell, arc) target, the extractor receives:

| Source | Content | Used by |
|---|---|---|
| Cell SPICE netlist (`.spi`, flattened to transistor level) | nets, devices, pin list, hierarchy | Stage A, Stage B |
| `define_cell` block from template.tcl | pinlist, output pins, delay/constraint/mpw template names, attributes | Stage B (pin role hints) |
| `define_arc` block from template.tcl | vector, related pin, arc type, probe list, metric, when condition | Stage C |
| char.tcl-derived overrides | glitch threshold, pushout percent, output-load index, model includes | Stage D |
| Arc spec (cell_arc_pt identifier) | arc_type, rel_pin/dir, constr_pin/dir, probe_pin/dir, when, LUT indices | Stage C, Stage D |
| Optional: historical sim result | byte-diff status vs MCQC, convergence info, waveform anomalies | Stage D, confidence |

The input contract is strict. Missing any of the first four = extractor
refuses to run and returns `needs_more_evidence`. This is a safety
property: do not produce a plausible schema from incomplete inputs.

## 7. Architecture: Four Stages

The extractor is a four-stage pipeline. Each stage has a typed
input/output contract, an internal mechanism, and a verification step.
The four stages and their input/output types:

```
SPICE + define_cell --> [A: Structural Decomposition] --> CCCGraph
                                                            |
                          CCCGraph + define_cell --> [B: Functional Naming] --> FunctionalView
                                                                                   |
                            FunctionalView + arc spec --> [C: Arc Projection] --> ArcProjection
                                                                                     |
                ArcProjection + char.tcl + sim hist --> [D: Measurement Context] --> MeasurementContext
                                                                                       |
                                                                                       v
                                                                              TopologySchema
```

The principle that holds everything together: **each stage's output is
a structured artifact that downstream stages and external reviewers can
inspect**. There is no monolithic LLM call that takes raw SPICE and
emits a schema.

### Stage A -- Structural Decomposition

**Input**: Cell SPICE netlist (flattened transistor list + net list).
**Output**: CCCGraph -- a directed graph where each node is a channel
connected component (CCC) and edges express signal flow between CCCs.

**Algorithm**, deterministic, no LLM:

1. Build the channel-connected graph: nodes are nets, an edge exists
   between two nets if they are connected through a source/drain of the
   same transistor.
2. Compute connected components in this graph after removing supply
   nets (VDD, VSS) and primary inputs/outputs. Each component is a CCC.
3. For each CCC, identify the output net(s) -- nets that drive
   transistor gates outside the CCC or are primary outputs.
4. For each CCC, build the PMOS pull-up sub-network and NMOS pull-down
   sub-network as series-parallel structures with the input gates as
   labels.
5. Within each CCC, detect structural loops (cycles in the transistor
   gate connectivity that pass through the CCC's output). The loop
   count is the upper bound on state-node count.
6. Compute a canonical signature for each CCC: a Weisfeiler-Lehman
   graph hash over the labeled series-parallel structure. This
   signature is what the KB retrieval keys on.

**Prior art used**: CCC decomposition (US patent 10133835), loop
detection within CCCs (US patent 6367057), graph canonicalization
(nauty / Weisfeiler-Lehman).

**Output schema** (CCCGraph):

```yaml
schema_version: 1
cell_name: <str>
primary_inputs: [<pin>, ...]
primary_outputs: [<pin>, ...]
power_nets: {vdd: <net>, vss: <net>}
cccs:
  - id: ccc_0
    output_net: <net>
    pmos_network:   # series-parallel expression with pin labels at leaves
      type: series
      children:
        - {type: parallel, children: [{type: leaf, gate: A1}, {type: leaf, gate: A2}]}
        - {type: leaf, gate: B}
    nmos_network: ...
    contained_transistors: [<dev_id>, ...]
    has_loop: false
    loop_count: 0
    canonical_signature: <wl_hash>
ccc_edges:
  - from: ccc_0
    to: ccc_1
    via_gate_of: <transistor_id>
```

**Verification at exit**: every transistor in the original netlist
belongs to exactly one CCC; every primary output is the output_net of
some CCC; loop_count is consistent with the cell's `define_cell`
sequential / combinational marker if present.

**Failure modes**:
- Pass-gate-style cells where source/drain swap during simulation may
  ambiguate the channel graph. Marked as `ambiguous_channels: true` and
  Stage B receives both candidate decompositions.
- Cells with hidden power gating may have nets that don't connect to a
  CCC under the static analysis. Marked as `dangling_nets: [...]` and
  Stage B is asked to reason about them.

### Stage B -- Functional Naming

**Input**: CCCGraph + define_cell.
**Output**: FunctionalView -- assignment of meaning to structures.

**What Stage B decides**:

- For each input pin: role in `{data, clock, scan_in, scan_enable,
  reset, set, enable, control, unknown}`. Roles are based on
  connectivity patterns: a pin that drives the clock-input of an
  identified state element is `clock`; a pin that gates a 2:1 mux
  selector for data is `scan_enable`; etc.
- For each CCC: the Boolean function it implements, expressed as an
  expression tree over the input pins it sees. Derived from the
  series-parallel structure (NMOS pull-down implements the negated
  function, PMOS pull-up implements the dual).
- For each loop in a CCC: whether it is a bistable storage element
  (master latch, slave latch, scan latch) or a keeper (weak feedback).
  This affects ic_count.
- Cell-level classification: combinational, latch, flop, scan flop,
  retention flop, clock gater, etc. -- feeds the existing
  `CellClass` enum where possible, or proposes a new value.
- Output polarity per primary output: `maxq` (Q-style, follows D) or
  `minq` (QN-style, inverts D).

**Mechanism** -- three parts cooperating:

- **Algorithmic part**: Boolean function derivation from
  series-parallel networks is symbolic. NMOS pull-down series of (A, B)
  = `A AND B` in the pull-down sense; parallel = `A OR B`. Pull-up is
  the dual. The Boolean function of each CCC is computed exactly.
- **LLM part**: pin role assignment, distinguishing storage loops from
  keepers, naming the cell class. The LLM sees the CCCGraph (not raw
  SPICE), the Boolean function of each CCC, and any define_cell hints
  (e.g., the presence of a `constraint_template` on a pin strongly
  implies it is a state element's data input).
- **Retrieval part**: structurally similar accepted schemas from the
  KB are injected as in-context anchors. If the CCC signature exactly
  matches an accepted schema, Stage B can copy that schema's pin role
  assignment and only flag drift.

**Verification at exit**:

- SAT check: re-derived Boolean function from Stage B's pin role
  assignment is logically equivalent to the algorithmic Boolean
  function from the CCC structure. (If LLM claims `Q = D when CP rises`
  but the algorithmic Boolean for the output CCC says `Q = !D when CP
  rises`, this is a polarity inversion that the LLM must justify or
  retract.)
- Loop / state-element consistency: declared state element count
  matches CCC loop count (subject to keeper detection).
- Pin role coverage: every input pin in `define_cell.pinlist` has a
  role assigned; unassigned = `unknown` and triggers low confidence.

**Failure modes**:

- LLM proposes a role that contradicts the algorithmic Boolean function
  -> SAT verification fails -> Stage B records the conflict and lowers
  confidence; reviewer sees both views.
- KB has no structurally similar prior; LLM proposes role without
  anchor -> confidence reduced proportionally to retrieval gap.

**Output schema** (FunctionalView):

```yaml
schema_version: 1
cell_name: <str>
proposed_cell_class: <CellClass-enum-value>
proposed_class_confidence: <0.0-1.0>
pin_roles:
  A1: {role: data, confidence: 0.95, evidence: [structural, define_cell_hint]}
  A2: {role: data, confidence: 0.95, evidence: [structural]}
  B:  {role: data, confidence: 0.90, evidence: [structural]}
  ZN: {role: output, polarity: minq, confidence: 0.99, evidence: [algorithmic]}
ccc_functions:
  ccc_0:
    output_net: ZN
    boolean: "!((A1 AND A2) OR B)"
    derivation: algorithmic
    sat_verified: true
state_elements: []   # AIOI21 case: combinational, no state
keeper_loops: []
overall_confidence: 0.93
```

### Stage C -- Arc-Aware Projection

This is the stage that has no public prior art and is the agent's
unique contribution. Given a FunctionalView and an arc spec, project
out the arc-specific topology and electrical context.

**Input**: FunctionalView + arc spec (arc_type, rel_pin, rel_dir,
constr_pin, constr_dir, probe_pin, when condition, LUT indices).
**Output**: ArcProjection -- the structural and electrical context of
the simulation deck for this specific arc.

**What Stage C decides**:

- Active path: the set of CCCs and transistors that participate in
  propagating the transition from rel_pin to probe_pin under the given
  when condition.
- Sensitizing state: the assignment of values to non-arc inputs (side
  pins) needed so that the active path is electrically open and the
  arc is observable at probe_pin.
- Initialization requirement: for each state element, whether it needs
  `.ic`, `.nodeset`, or DC bias; what value; for how long the init
  must hold before the arc transition starts.
- Side-pin drive strategy: for each side pin in the sensitizing state,
  whether to drive it with a DC voltage source or pulse it
  pre-transition.
- Expected path resistance signature: qualitative -- fast / medium /
  slow -- based on how many PMOS or NMOS are in parallel vs series on
  the active path. Used by Stage D for measurement window sizing.

**Mechanism** -- LLM + SAT + KB retrieval cooperating:

- **LLM proposes** the active path, sensitizing state, init strategy,
  drive strategy.
- **SAT verifies** that under the proposed sensitizing state, the
  Boolean function from FunctionalView indeed makes probe_pin
  responsive to rel_pin's transition. If not, the proposal is rejected
  and the LLM retries with the SAT counter-example as additional
  context.
- **KB retrieves** the top-K most structurally similar accepted
  ArcProjections (matched on CCCGraph canonical signature plus arc
  type) as in-context anchors before the LLM is queried.
- **Symbolic path tracer** (algorithmic helper): given the sensitizing
  state, propagate Boolean values through the CCC graph and identify
  which transistors are switching during the transition vs static. The
  switching set is the active path. This helper can be run after the
  LLM as a verification, or before the LLM to constrain its options.

**Verification at exit**:

- Active path includes all transistors with switching gates under the
  sensitizing state and excludes all transistors with static gates.
- Sensitizing state plus the arc's input transition produces a
  detectable change at probe_pin in the Boolean function (SAT
  verified).
- Init requirements are consistent with state element count from
  FunctionalView.

**Failure modes**:

- LLM proposes a sensitizing state that does not make the arc
  observable. SAT catches this. Retry with counter-example. After two
  failed retries, mark `needs_more_evidence` and surface to reviewer.
- LLM proposes an init requirement that names a node not in
  FunctionalView's state_elements. Reject and ask LLM to justify or
  retract.

**Output schema** (ArcProjection):

```yaml
schema_version: 1
arc_id: <cell_arc_pt-identifier>
cell_name: <str>
arc_type: <hold | delay | setup | min_pulse_width | ...>
rel_pin: {name: B, direction: rise}
probe_pin: {name: ZN, direction: rise, polarity: maxq}
when_condition: "!A1 & !A2"
active_path:
  switching_transistors: [<dev_id>, ...]
  ccc_traversal: [ccc_0]
  pmos_segment: "(A1-P || A2-P) -- B-P series"
  nmos_segment: "(A1-N -- A2-N) || B-N"
  path_resistance_qualitative: low  # both A1-P and A2-P in parallel
sensitizing_state:
  side_pin_values:
    A1: 0
    A2: 0
  derivation: "when=!A1&!A2 directly specifies side pins"
  sat_verified: true
init_requirements:
  state_elements: []   # combinational, none
  notes: "No initialization needed; cell is combinational"
drive_strategy:
  A1: {mode: dc_bias, value: 0}
  A2: {mode: dc_bias, value: 0}
  B:  {mode: pulse, edge: rise}
expected_signature:
  speed_class: fast
  rationale: "Two PMOS in parallel pulling up; B-PMOS unconditionally on (in this conducting context); expect lowest RC of B-related arcs"
confidence: 0.91
evidence:
  - algorithmic: active_path derived from sensitizing state propagation
  - sat: sensitization validated
  - retrieval: nearest neighbor in KB is AOI22 cell_X, arc Y, byte-equal pass rate 0.94
```

### Stage D -- Measurement Context

**Input**: ArcProjection + char.tcl override cascade + optional
historical sim result.
**Output**: MeasurementContext -- measurement and risk guidance.

**What Stage D decides**:

- Measurement type: `standard`, `pushout`, `glitch`, `both`.
- Glitch risk assessment: presence of dynamic nodes on the active path,
  charge-sharing risk, internal high-impedance nodes.
- Measurement window: time relative to rel_pin transition for the
  measurement to start and end.
- Output load policy: how the LUT index_2 value maps to output
  capacitance.
- Known failure modes: a small set of pattern-matched watchouts
  derived from similar prior cells in the KB.
- Char.tcl override binding: which overrides apply (glitch threshold,
  pushout percent, model include), with source attribution.

**Mechanism** -- rule-table + LLM + feedback loop:

- **Rule table**: hand-curated heuristics. Examples: "if active path
  contains a dynamic node and arc_type is delay -> glitch risk high";
  "if cell class is `ckg` and arc_type is `nochange` -> measurement is
  pushout"; etc. The rule table is small (single-digit hundreds) and
  reviewable.
- **LLM** generalizes beyond rule-table coverage: for an unfamiliar
  topology, look at the ArcProjection's pmos/nmos segments and reason
  about charge sharing nodes, propose risks.
- **Feedback loop**: rejected proposals from prior reviews provide
  negative examples. When the LLM proposes a measurement guidance that
  matches a past `rejected` schema's pattern, confidence is reduced.

**Verification at exit**:

- Measurement type is consistent with cell class and arc type
  (cross-checked against rule table even if LLM disagrees; LLM disagreement
  surfaces to reviewer).
- Char.tcl overrides cited actually exist in the input override
  cascade.
- Glitch risk + active path consistency (cannot claim glitch risk if
  active path has no dynamic nodes and no charge-sharing structure).

**Output schema** (MeasurementContext):

```yaml
schema_version: 1
arc_id: <cell_arc_pt-identifier>
measurement_type: standard
glitch_risk:
  level: low
  rationale: "Static CMOS, no internal dynamic nodes on active path"
measurement_window:
  start: t_rel_transition + 0
  end: t_rel_transition + 5 * tau_estimate
  tau_estimate_from: active_path.path_resistance_qualitative
output_load_policy:
  source: lut_index_2
  binding: standard_capacitive
known_failure_modes: []
char_tcl_overrides:
  glitch_threshold: {value: <from-cascade>, source: <global|cell|arc>}
  pushout_percent: {applicable: false}
confidence: 0.88
```

## 8. Composite Output: TopologySchema

The four stage outputs compose into a single TopologySchema. The
schema is the only thing that leaves the extractor.

```yaml
schema_version: 1
extractor_version: <semver>
arc_id: hold_AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD_ZN_rise_B_rise_notA1_notA2_1_1
cell_name: AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
source:
  node: N2P_v1.0
  lib_type: <example_lib>
  corner: ssgnp_0p450v_m40c_cworst_CCworst_T
evidence_bundle:
  netlist_hash: <sha256>
  define_cell_hash: <sha256>
  define_arc_hash: <sha256>
  char_tcl_hash: <sha256>
  bundle_hash: <sha256>
structural:    # from Stage A, CCCGraph reference
  ccc_count: 1
  has_loop: false
  canonical_signature: <wl_hash>
functional:    # from Stage B summary
  cell_class: aoi_compound
  pin_roles: {A1: data, A2: data, B: data, ZN: output}
  boolean_per_ccc: {ccc_0: "!((A1 AND A2) OR B)"}
  state_element_count: 0
arc_projection: ...      # from Stage C, full structure inlined
measurement: ...         # from Stage D, full structure inlined
confidence:
  overall: 0.90
  by_stage: {A: 1.00, B: 0.93, C: 0.91, D: 0.88}
  rationale: "Stage A deterministic. Stage B nearest-KB match exact on CCC signature. Stage C SAT-verified, KB nearest neighbor at 0.94 byte-equal pass rate. Stage D rule-table match, no past rejected pattern."
novelty_type: known_family_new_cell
human_review_required: true
proposed_principle_family:
  key: delay/aoi/rise_when_side_zero
  status: new_proposal     # not in current ~60-family registry
  param_binding_for_deckgen:
    REL_PIN: B
    CONSTR_PIN: null   # not applicable to delay arc
    PROBE_PIN_1: ZN
    VDD_VALUE: <from-corner>
    INDEX_1_VALUE: <from-LUT>
    OUTPUT_LOAD: <from-LUT>
    SIDE_PIN_BIAS: {A1: 0, A2: 0}
```

## 9. Worked Example: AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

The cell from `PROJECT_NOTES.md` section 2.4. Function `ZN = !((A1 * A2) + B)`,
i.e., AOI21. The cell name uses TSMC's `AIOI21` naming convention and the
function is the standard AOI21 with input polarity respecting the PMOS
pull-up structure described in `PROJECT_NOTES` section 2.5.

Ten delay arcs total in the cell. We trace **arc #5** from the table:
`B -> ZN under when="!A1 & !A2", vector {xxRR}` -- B rises, ZN rises.

Pinlist order (from define_cell): `[A1, A2, B, ZN]`, so vector position
3 = B, position 4 = ZN, matching `{xxRR}` = B rises, ZN rises, A1 and
A2 static.

### Stage A on AIOI21

Netlist has 8 MOS (4 PMOS, 4 NMOS).

CCC decomposition: the cell has one CCC, ccc_0, with output net = ZN.

PMOS network (pull-up):

```
ccc_0.pmos_network:
  type: series
  children:
    - type: parallel
      children:
        - {type: leaf, gate: A1, device: MP_A1}
        - {type: leaf, gate: A2, device: MP_A2}
    - {type: leaf, gate: B, device: MP_B}
```

NMOS network (pull-down):

```
ccc_0.nmos_network:
  type: parallel
  children:
    - type: series
      children:
        - {type: leaf, gate: A1, device: MN_A1}
        - {type: leaf, gate: A2, device: MN_A2}
    - {type: leaf, gate: B, device: MN_B}
```

`has_loop: false`. Canonical signature: WL hash over the labeled SP
tree. (This signature would match exactly across all AOI21 variants
regardless of TSMC naming or pin order.)

### Stage B on AIOI21

The Boolean function for ccc_0:

- NMOS pull-down expression (when on, pulls ZN to 0):
  `(A1 AND A2) OR B`
- ZN is 0 when pull-down is on, so:
  `ZN = NOT((A1 AND A2) OR B)`

The algorithmic derivation is exact; no LLM needed for the function
itself.

Pin role assignment by LLM:

- No state element loops, so no clock pin candidates.
- `define_cell` has no `constraint_template` field on any pin, so no
  pin is a state element data input.
- All three input pins (A1, A2, B) get role `data`.
- ZN gets role `output`, polarity `minq` (the Boolean is an inversion
  of a function of inputs).

Cell class proposal: `aoi_compound` (or whatever value the classifier
admits for this structure; if the current `CellClass` enum has no
matching member, the proposal is a new class candidate flagged for
review).

SAT verification: passes trivially since the Boolean function was
algorithmically derived.

Overall Stage B confidence: ~0.93. The 0.07 deduction comes from the
"new cell class" novelty -- no exact KB neighbor on the cell-class
front, even though there are AOI21 neighbors on the CCC signature
front.

### Stage C on AIOI21, arc B->ZN @ !A1&!A2

Arc spec:

```
arc_type: delay (interpreted from {xxRR}, no -type in template.tcl)
rel_pin: B, rel_dir: rise
constr_pin: not applicable (delay arc, no constraint)
probe_pin: ZN, probe_dir: rise
when: "!A1 & !A2"  ->  A1=0, A2=0
```

LLM proposes (with the KB nearest neighbor -- say AOI22 from a prior
node -- as in-context anchor):

- Sensitizing state: A1=0, A2=0 (directly from when).
- Active path: when A1=0 and A2=0, both A1-PMOS and A2-PMOS are on
  (PMOS conducts at gate=0). When B then rises from 0 to 1, B-PMOS
  turns off and B-NMOS turns on. So during the transition, B-PMOS
  switches and B-NMOS switches. A1-PMOS and A2-PMOS were already on
  before the transition; they continue on, providing the pull-up path.
  But ZN is rising, which means pull-up wins for an instant before
  pull-down takes over... wait.

Let me reread: B is rising. Initial state B=0: B-PMOS on, B-NMOS off.
With A1=A2=0, A1-PMOS and A2-PMOS on; A1-NMOS and A2-NMOS off. So the
PMOS pull-up path is (A1-P || A2-P) -- B-P, all on -> ZN is pulled to
VDD -> ZN=1. NMOS pull-down has the (A1-N -- A2-N) branch and the B-N
branch; with A1=A2=B=0, all NMOS are off, no pull-down. So ZN=1
initially. **Correct: when A1=A2=0 and B=0, ZN = !((0*0)+0) = !0 = 1.**

Now B rises to 1: B-PMOS turns off, B-N turns on. The PMOS pull-up
path is broken (B-PMOS is the series element). The NMOS pull-down now
has B-N conducting; (A1-N -- A2-N) is off because A1=0; B-N alone
pulls ZN down. **ZN = !((0*0)+1) = !1 = 0.**

So when B rises, ZN **falls**, not rises. That contradicts vector
`{xxRR}` which says both B and ZN rise.

This is the kind of error the SAT verification catches. The proposed
arc spec for "B rise -> ZN rise under !A1 & !A2" is logically
inconsistent with the Boolean function `ZN = !((A1*A2)+B)`. SAT
returns the counterexample: under A1=A2=0, B rising means ZN falling.

What does this tell us? Either:

- (a) The vector `{xxRR}` parser interpretation is wrong (positions
  don't map to pins in the order assumed).
- (b) The cell's actual function differs from standard AOI21 (it might
  be `AIOI21` = "And-Invert-Or-Invert-21", which could be `ZN = !A1 *
  !A2 * !B` or some other variant; the TSMC naming may not match the
  standard AOI21).
- (c) PROJECT_NOTES section 2.4 has the function annotation slightly
  off from the actual cell function.

In a real run, the extractor would:

1. Surface the SAT inconsistency to the reviewer with all three
   hypotheses.
2. Inspect the netlist polarity directly -- is there an internal
   inverter on B before it reaches B-PMOS / B-NMOS?
3. Re-derive the function from the actual physical PMOS/NMOS gate
   inputs, not from the assumption that pin "B" goes straight to a
   transistor labeled B.

This is exactly the value of separating Stage A (algorithmic Boolean
from physical structure) from Stage B (semantic pin role assignment) --
the **structural ground truth catches LLM and human assumptions that
don't survive verification**.

For the purposes of completing this worked example, assume scenario
(b) and the actual cell function is `ZN = !B + !(A1*A2)` (which makes
B's polarity inverted; equivalently, "B" pin internally drives an
inverter before reaching the PMOS/NMOS gates labeled "B" in
PROJECT_NOTES's analysis). Under this corrected function:

- A1=0, A2=0, B=0 -> ZN = !0 + !(0) = 1 + 1 = 1.
- A1=0, A2=0, B=1 -> ZN = !1 + !(0) = 0 + 1 = 1.

So under !A1 & !A2, ZN is always 1 regardless of B. B -> ZN is hidden,
not active. This **also** doesn't produce a rising-B-rising-ZN arc.

The most likely correct function for AIOI21 with vector `{xxRR}` and
`{xxFF}` valid under `!A1 & !A2`: `ZN = B * !(A1*A2)` as originally in
PROJECT_NOTES, which under !A1&!A2 gives ZN = B * !0 = B * 1 = B,
making ZN follow B directly. This requires the PMOS/NMOS network to
actually implement `ZN = B * !(A1*A2)` and the structure in
PROJECT_NOTES section 2.5 is just descriptive but not directly the
pull-up network.

The lesson for the extractor design is the important part: **whatever
the actual structure is, Stage A reads it directly from the netlist
and Stage B's Boolean derivation is exact. Stage C cannot proceed
until Stage B's Boolean is consistent with the arc's observable
behavior under the when condition.** SAT verification catches all
inconsistencies between human descriptions, LLM proposals, and
physical structure.

Continuing under the assumption that B -> ZN @ !A1&!A2 with both rising
is the correct arc behavior (matching `{xxRR}`):

- Active path on B rise: B-PMOS switches (gate goes high to low, on
  to off... wait, if the actual pull-up has B's input inverted
  internally so B-PMOS-gate sees !B): when B rises, !B falls, so
  B-PMOS-gate falls, B-PMOS turns on. Combined with A1-PMOS, A2-PMOS
  on (gates A1=A2=0), the pull-up conducts, ZN rises.
- Sensitizing state: A1=0, A2=0 (from when).
- Drive strategy: A1 DC to GND, A2 DC to GND, B pulse 0->VDD.
- Init requirements: none (combinational).
- Expected speed: fast -- both A1-PMOS and A2-PMOS in parallel give R/2
  for the (A1 || A2) segment; B-PMOS in series adds R; total ~1.5R.
  Compared to A1&!A2 case (only A2-PMOS on, single device R), the
  !A1&!A2 path is faster. This matches PROJECT_NOTES section 2.5
  intuition.

Output of Stage C:

```yaml
active_path:
  switching_transistors: [MP_B_path, MN_B_path]
  ccc_traversal: [ccc_0]
  pmos_segment: "(A1-P parallel A2-P) series B-P  [structure per netlist]"
  nmos_segment: "(A1-N series A2-N) parallel B-N"
  path_resistance_qualitative: low
sensitizing_state:
  side_pin_values: {A1: 0, A2: 0}
  sat_verified: true   # after Boolean reconciliation
init_requirements:
  state_elements: []
  notes: "Combinational; no init"
drive_strategy:
  A1: {mode: dc_bias, value: 0}
  A2: {mode: dc_bias, value: 0}
  B:  {mode: pulse, edge: rise}
expected_signature:
  speed_class: fast
  rationale: "Both A1-P and A2-P in parallel; expected lowest RC among the three when-conditional B arcs"
confidence: 0.85
evidence:
  - algorithmic: active_path from sensitizing state propagation
  - sat: sensitization-vs-Boolean consistency confirmed
  - retrieval: KB has no exact AIOI21 neighbor; nearest AOI22 from N2P used as anchor (similarity 0.78)
```

The 0.85 confidence reflects (i) Boolean reconciliation took a SAT
back-and-forth, (ii) KB lacks an exact AIOI21 neighbor.

### Stage D on AIOI21 arc B->ZN

- Measurement type: `standard delay`.
- Glitch risk: low. No dynamic nodes, no internal high-Z nodes, all
  PMOS/NMOS are static CMOS.
- Measurement window: from B's 50% transition to ZN's 50% transition,
  bounded above by ~5 x tau estimated from path resistance.
- Output load policy: LUT index_2 binds directly to a single output
  capacitor on ZN (standard delay measurement).
- Char.tcl override: glitch threshold not applicable; pushout not
  applicable.
- Known failure modes: empty (AIOI compound static CMOS with no
  dynamic structure).

Confidence: ~0.92 (rule table covers this case directly; LLM not
needed).

### Composite TopologySchema for AIOI21 arc B->ZN @ !A1&!A2

Overall confidence: 0.88 (weighted product / minimum across stages).
Novelty type: `known_family_new_cell` -- the family (AOI compound,
B-side rise/fall) likely already exists in the principle engine or
nearby; AIOI21 specifically is the novel part.

Reviewer action expected: confirm Boolean reconciliation, accept
proposed principle family or map to existing family, then schema goes
to `reviews/accepted/` and KB curator updates indices.

## 10. Sequential Cell Extension Sketch

For a DFFQ1 hold arc (`hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1`),
the differences from the AIOI21 case are concentrated in Stages B and
C:

- **Stage A**: identifies multiple CCCs (typically 4-6 for a basic
  DFF: clock buffer, master-latch CCC pair, slave-latch CCC pair,
  output buffer). At least two CCCs have `has_loop: true` -- the
  master latch and slave latch state-holding loops.
- **Stage B**: CP is `clock` (drives the gate of pass transistors
  between master and slave); D is `data`; Q is `output`. The two state
  loops are bistable storage, contributing ic_count=2 (matches the
  `InitStyle.IC, ic_count by topology` entry for latch_S / RCB / CKG
  in `family_types.py`).
- **Stage C**: for a hold arc, the sensitizing state requires the
  master latch to be initialized to a value opposite to D's eventual
  transition -- so the D->master transition during the hold window is
  detectable. Init requirements list both latch internals with
  specific .ic values.
- **Stage D**: hold measurement is typically `standard`; glitch
  risk is low unless the cell has internal dynamic nodes.

This document does not work through DFF in full detail; the structural
treatment is mechanical from the AIOI21 walkthrough. A separate
companion document is the appropriate place.

## 11. Where Intelligence Lives

To answer the recurring question directly: intelligence in this
extractor is not located in a single stage. It is the composition
property of:

- **Stage A's deterministic ground truth** providing structural facts
  that no LLM or human assumption can override silently.
- **Stage B's SAT-verified Boolean function** providing a hard logical
  anchor that catches polarity and pin-role inconsistencies.
- **Stage C's three-way reconciliation** between LLM proposal, SAT
  sensitization check, and KB nearest-neighbor retrieval. No single
  source is trusted alone; agreement of at least two raises confidence.
- **Stage D's rule-table + LLM + feedback-loop triplet** providing
  bootstrap coverage, generalization beyond rules, and continuous
  calibration from past reviews.

A monolithic LLM call that reads raw SPICE and emits a schema has none
of these checks. It would produce plausible-but-untrusted output. The
worked example above demonstrates concretely: even an experienced
human-authored description (PROJECT_NOTES) had a Boolean function
detail that the structural-vs-arc consistency check would flag. The
extractor's value is not in matching human intuition -- it is in
producing schemas that are **internally consistent across structure,
logic, and arc behavior**, with all inconsistencies surfaced rather
than hidden.

## 12. Knowledge Base Interaction

The extractor reads from the KB at three points:

- **Stage B**: structurally similar accepted FunctionalViews as
  in-context anchors for the LLM pin-role and cell-class decisions.
- **Stage C**: structurally + arc-type similar accepted ArcProjections
  as in-context anchors. The retrieval key is the CCCGraph canonical
  signature plus arc_type. Top-K (K=3) returned with similarity
  scores.
- **Stage D**: past `rejected` MeasurementContexts with similar
  structural signature as negative examples.

The extractor does not write to the KB. The reviewer-facing agent and
the KB curator agent handle persistence and indexing.

KB retrieval is required for Stages B, C, D, but the extractor must
still produce output when retrieval returns empty (fresh KB, novel
node). In that case, confidence is reduced and the schema's
`evidence` field records the lack of anchor explicitly.

## 13. Confidence Propagation

Each stage emits a confidence in [0, 1]. The overall TopologySchema
confidence is the minimum across stages, not the product, because each
stage's failure invalidates the schema regardless of other stages'
quality.

Stage-internal confidence is computed from:

- Stage A: always 1.0 unless the netlist had `ambiguous_channels` or
  `dangling_nets` issues; then proportional reduction.
- Stage B: 1.0 if all SAT checks pass and every pin has a KB anchor;
  reduced for SAT-LLM conflicts, unanchored pin roles, novel cell
  class proposals.
- Stage C: starts at the KB nearest-neighbor's byte-equal pass rate;
  reduced for SAT retries, no KB anchor.
- Stage D: 1.0 if rule table covers the case directly; reduced for
  LLM-only generalization, presence of past rejected pattern in KB.

The reviewer threshold defaults to 0.80 for `direct accept` candidate,
0.60 to 0.79 for `review with evidence`, below 0.60 for
`needs_more_evidence`. Thresholds are configurable per project.

## 14. Implementation Roadmap

1. **Stage A first** -- fully deterministic, has prior art, can be
   tested against AIOI21 PROJECT_NOTES ground truth and any other cell
   the user can hand-verify. No LLM dependency.
2. **CCCGraph schema and persistence** -- finalize the YAML format,
   add a snapshot test on AIOI21, and prepare a small set of hand-
   labeled CCCGraphs as eventual training / retrieval seed.
3. **Stage B with SAT verification** -- implement the algorithmic
   Boolean derivation first; LLM hooks come second; SAT cross-check
   runs unconditionally.
4. **Stage C arc-aware projection** -- needs Stage A and Stage B
   stable. Implement symbolic path tracer first (no LLM), then add
   LLM reasoning layer on top.
5. **Stage D measurement context** -- rule table first (extracted from
   `template_rules.json` and `delay_template_rules.py` patterns), LLM
   on top, feedback loop last.
6. **KB retrieval interface** -- initially empty; populated as accepted
   schemas accumulate. Stage C can run with empty KB at reduced
   confidence.
7. **Integration with the principle engine** -- the extractor proposal
   feeds an experimental-mode path in DeckGen, gated behind an
   explicit flag, until a proposal accumulates enough byte-equal pass
   evidence to be promoted to a real family entry.

## 15. Open Questions Deferred

- Stage A handling of pass-gate ambiguity in scan flops with multiple
  channel directions.
- Stage B's choice between extending the existing `CellClass` enum vs
  introducing a free-form `cell_class_proposal` field.
- Stage C's KB retrieval cutoff: top-K vs similarity-threshold; which
  is more reviewer-friendly.
- Stage D's rule table format: hand-authored Python predicates vs
  YAML conditions evaluated by a small DSL.
- How the extractor handles cells with multiple primary outputs (e.g.,
  Q and QN both probed); per-output Stage C runs or unified.
- Latency budget: target wall-clock per (cell, arc) for both inline
  and offline modes.

## 16. Boundary With the Rest of the Agentic Flow

The extractor produces a TopologySchema. The rest of the agentic flow:

- The reviewer-facing agent presents the schema plus its evidence to a
  human reviewer; the reviewer accepts, rejects with rationale, or
  requests more evidence. The reviewer-facing agent is responsible for
  prompt presentation, evidence linkage, and capturing the verdict.
- The KB curator agent persists accepted schemas, updates the
  retrieval indices, and may promote schemas to principle engine
  family proposals after sufficient byte-equal pass evidence.
- The planner agent decides when to invoke the extractor (batch
  offline for new node bring-up; on-demand inline for missed
  principle-engine matches).
- The cross-project query agent serves the KB to external consumers.

Each of these is a separate agent component with its own design
document. This document is scoped to the extractor only.
