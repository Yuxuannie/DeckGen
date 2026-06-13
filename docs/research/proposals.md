# Pillar 3 -- Proposals

Status: research only. NOTHING here is applied. Every "diff" is TEXT for review;
the isolation rules forbid touching `engine/`. Each proposal states motivation,
approach, a proposed-diff sketch against the real files on `feat/phase-2b-engine`
(read 2026-06-13), the risk, and the SPICE check that would validate it.

Ordering follows spec SS9 but is re-sequenced by depth-to-risk from `findings.md`.

-----

## P1 -- Layer-B retention in stage0 + IR fields (foundation, unblocks all)

**Motivation.** `stage0_parse` drops every `C` line ("ignored for connectivity").
Pillar 3 needs them; they are the entire answer for a floating node (spec SS0).

**Approach.** Keep Layer A (R-short) untouched. Add a parallel pass that records
`C` lines into a new `DeviceGraph.caps`, and a derived aggregation to logical
nets. Caps with both ends on the same logical net vanish (intra-net), recorded
as a derivation. Purely additive; no existing field changes meaning.

**Proposed diff (TEXT, not applied).**

```
# engine/types.py
@@ class Device ...
+@dataclass
+class Cap:
+    a: str            # logical net (post node_to_net), or rail
+    b: str            # logical net, or rail ("VSS"/"0"=ground)
+    farads: float
+    raw: str          # provenance: the original C line

 @dataclass
 class DeviceGraph:
     ...
     node_to_net: Dict[str, str] = field(default_factory=dict)
+    caps: List[Cap] = field(default_factory=list)         # Layer B (parasitic C)
     checks: List[str] = field(default_factory=list)
     source: str = ""
+
+    def cap_network(self):
+        """Aggregate caps to logical nets: (Cg: net->F, Cc: (net,net)->F)."""
+        ...  # grounded vs coupling split; intra-net dropped (see prototype)
```

```
# engine/stages/stage0_parse.py
@@ in the per-line loop, alongside the R branch:
-        # C / anything else: ignored for connectivity
+        elif head == "C":
+            # Layer B: retain (mapped to logical nets AFTER clustering, below).
+            raw_caps.append((toks[1], toks[2], float(toks[3]), line))
@@ after node_to_net is built:
+    caps = [Cap(node_to_net.get(a, a), node_to_net.get(b, b), f, raw)
+            for a, b, f, raw in raw_caps]
@@ return DeviceGraph(... node_to_net=node_to_net, caps=caps, ...)
```

A self-consistency derivation for `checks`: "Layer B: N caps retained; K grounded,
L coupling, M intra-net (dropped)."

**Risk.** Low. Additive. The only real-world risk is LPE C-line variants the
naive `float(toks[3])` can't parse (units suffix, `$`-comments, 3-terminal C).
Mitigation: tolerant value parse + a derivation listing any skipped lines (never
silently drop -- CLAUDE.md). The prototype's `parse_lpe` handles the fixture
format; real DSPF may differ (open_questions Q5).

**SPICE check.** None needed for parsing itself; correctness of aggregation is
checked by P3's resolve against SPICE.

-----

## P2 -- Cap-graph builder (raw caps -> logical-net Cg / Cc)

**Motivation / approach.** The aggregation in P1's `cap_network()`, factored so
both the resolver and the AIQC feature emitter consume one object. Already
prototyped: `research/prototypes/charge_resolve_demo.py::cap_network`.

**Proposed diff (TEXT).** A new module `engine/charge.py` (NOT in stage0, to keep
stage0 connectivity-only):

```
# engine/charge.py  (NEW)
def cap_network(graph) -> Tuple[Dict[str,float], Dict[Tuple[str,str],float]]:
    """grounded Cg[net], coupling Cc[(net_lo, net_hi)]; intra-net dropped."""
    ...   # body == prototype cap_network(), operating on graph.caps
```

**Risk.** Low. Pure function of P1's data.

**SPICE check.** None (structural).

-----

## P3 -- Charge-conservation resolve (two-step: contract then matrix)

**Motivation.** The core of Pillar 3. Implements `findings.md` Direction 3: the
spec's scalar 2.4 is exact only after contracting ON-connected groups; free-free
coupling and fixed-node coupling need the matrix.

**Approach.** Pure function: `(free_groups, Cg, Cc, entry_V, fixed_V) -> {net: V|None}`.
Step A contracts ON-connected floating groups by grounded-cap charge sum; Step B
assembles the coupling matrix over super-nodes and solves. Singular component ->
`None` (X), never a fabricated value. Already prototyped as `charge_resolve()`
(pure-Python dense solve; numpy is NOT installed here, so the production version
should use numpy if available else the stdlib fallback).

**Proposed diff (TEXT).**

```
# engine/charge.py
def resolve(free_groups, Cg, Cc, entry_V, fixed_V) -> Dict[str, Optional[float]]:
    # Step A: contract each ON-connected group via grounded-cap charge sum.
    # Step B: A[i][i]=Cg(super_i)+sum Cc; A[i][k]=-Cc(i,k); b[i]=Q+coupling-to-fixed.
    # solve A v = b; singular component -> None (X).
    ...   # == prototype charge_resolve(); see findings.md 3.3 / 3.4
```

Determinism: sort nets and groups by name before assembly (matches the existing
deterministic-derivation contract; `stage0`/`stage2` already sort).

**Risk.** Medium. The MODEL (ON=short / OFF=open, lumped LPE caps, ideal hold) is
an idealization; the ALGEBRA is exact (`findings.md` 3.1 derivation, prototype
hand-checked). The risk is physical, not code: see SPICE check.

**SPICE check (this is the trust artifact).**
1. Scalar: precharge a 2-node group, isolate, SPICE `.tran` UIC no `.ic`; settled
   V must match `(C1 V1 + C2 V2)/(C1+C2)` within tol.
2. Coupled: a 2-free-node coupled case where the matrix predicts a split (like
   `demo_coupled`); SPICE must reproduce the split, not the average.
3. Tolerance proposal: settled node V within `min(5 mV, 1% VDD)` of SPICE.
   UNVERIFIED tolerance -- must be calibrated against numerical/UIC-settling noise
   first (open_questions Q2).

-----

## P4 -- Node classification via ordered phase recurrence

**Motivation.** `findings.md` Direction 1: "last-driven value" is not a lookup;
it is the end of an ordered per-phase voltage trajectory, and driven-then-perturbed
nodes need the trajectory. Also the vacuous-fixpoint criterion tells the engine
when a single pass is provably correct vs when it must iterate-or-X.

**Approach.** Replay `switchlevel.evaluate` across the drive-and-settle phases
(stage3 already plans them) carrying voltages forward via P3's resolve. Classify
each net at the measured instant: DRIVEN (rail) / SETTLE-REACHABLE (class 2,
trajectory value) / TRULY-FLOATING (class 3, charge-shared). Tag each net with
`drives_a_gate = net in gate_nets` (stage1 already computes `gate_nets`); if any
floating net drives a gate, run the intra-phase fixpoint with a bounded iteration
cap and emit X on non-convergence.

**Proposed diff (TEXT).**

```
# engine/stages/stage3_initialize.py  (EXTEND -- do NOT regress sequential path)
@@ after the existing master/slave derivation:
+    # Pillar 3: resolve floating COMBINATIONAL internal nodes by charge history.
+    Cg, Cc = charge.cap_network(graph)
+    phases = _phase_assignments(sens, arc)        # ordered pre-edge phases
+    entry_V = {}                                   # net -> volts, carried forward
+    for ph in phases:
+        logic = switchlevel.evaluate(graph, ph, broken)
+        floating = [n for n in graph.nets if logic[n] is None]
+        groups = _on_connected_groups(graph, logic, floating)
+        v = charge.resolve(groups, Cg, Cc, entry_V, _fixed_volts(logic))
+        entry_V.update({n: (vdd if logic[n]==1 else 0.0) for n in graph.nets
+                        if logic[n] is not None})
+        entry_V.update({n: x for n, x in v.items() if x is not None})
+    # classify + emit (see P5)
```

```
# engine/types.py :: InitializationResult  (ADD fields; required_state extended)
+    ic_lines: List[Derivation] = field(default_factory=list)   # "v(x1.node)=V" + charge math
+    node_class: Dict[str, str] = field(default_factory=dict)   # net -> driven|settle|floating|X
```

**Risk.** Medium-high. Touches the load-bearing stage3 and adds a fixpoint loop.
Mitigation: gate the whole block behind the vacuous-fixpoint test so the common
case (no floating gate-driver) is a single deterministic pass; the iterate-or-X
path runs only for keeper/bootstrap topologies and is bounded. MUST not regress
the existing sequential derivation -- it is additive, the sequential `required_state`
entries are preserved.

**SPICE check.** Series-stack internal node: SPICE drive-and-settle (no `.ic`)
settling value vs the recurrence's predicted `V(p_m)`, within P3's tolerance.
A keeper case to exercise the fixpoint/X path (open_questions Q6).

-----

## P5 -- Deck emission: drive-and-settle extension + `.ic` fallback + probes

**Motivation / approach.** spec 2.6. Class-2 nodes: extend the drive-and-settle
stimulus so a real path charges them (no `.ic`; simulator computes the charge).
Class-3 nodes: emit `.ic v(x1.<node>)=V` with transient UIC, each wrapped in a
`Derivation` carrying the charge math. Probe every resolved node for P2/P3.
NEVER `.nodeset` for held charge (spec 2.6).

**Proposed diff (TEXT).**

```
# engine/stages/stage4_deckgen.py
@@ in sections["engine"], after init.stimulus:
+        + ["* initialization (.ic fallback, class-3 charge-shared nodes):"]
+        + [f".ic {d.value}   $ {d.reason}" for d in init.ic_lines]
@@ ensure transient UIC is present in the .tran (collateral/measurement section)
```

**Risk.** Low-medium. `.ic` correctness depends entirely on P3/P4 (it asserts a
voltage the simulator will not recompute). Risk is concentrated upstream; here the
risk is only deck syntax (UIC flag presence, hierarchical node path `x1.<node>`,
which stage3 already builds via `_probe_node` `[CODE]`).

**SPICE check.** The `--verify` cross-check below (P7-adjacent): deck-with-`.ic`
vs deck-with-long-preconditioning-no-`.ic` must yield the same measured edge.

-----

## P6 -- SPICE validation protocol (a deliverable in itself)

A repeatable procedure to run when SPICE is available. Degeneration-first.

| # | Cell / setup | What runs | Cross-check | Proposed tol |
|---|---|---|---|---|
| V0 | 2-node hand-calc (no cell) | analytic | `(C1V1+C2V2)/(C1+C2)` vs prototype | exact (1e-9) |
| V1 | NAND2/AOI21 PDN internal node, precharged then isolated | SPICE `.tran` UIC, no `.ic` | settled V vs P3 resolve | min(5mV,1%VDD) |
| V2 | same, with a coupled neighbor swung | SPICE | dV_f vs `alpha*dV` (divider) | min(5mV,1%VDD) |
| V3 | two coupled floating nodes (no merge) | SPICE | split vs matrix (not average) | min(5mV,1%VDD) |
| V4 | any cell, full arc | deck `.ic` vs deck long-precond no-`.ic` (--verify) | same measured edge | edge within sim noise |
| V5 | keeper / floating-gate node | SPICE | does engine X match a real charge-race? | qualitative |

Discriminator note (`findings.md` D5): V4 alone is insufficient -- if the charge
VALUE is wrong, both decks can be wrong the same way and agree. V1-V3 (absolute,
against analytic or direct transient) are the real value checks; V4 checks the
STIMULUS plan. Run both classes.

Sample selection: stratify across PDN depth (stack of 2 vs 3+), presence of a
dynamic node, presence of a coupling cap above some fraction of `C_total`, and
corner (the `ssgnp_0p450v_m40c` fixture corner is a good low-VDD stress case --
`alpha*dV` is a larger fraction of a 0.45 V rail).

**Risk.** N/A (protocol). **SPICE check.** Is the deliverable.

-----

## P7 -- Coupling-bump worst-case vector selection (couples back to Pillar 2)

**Motivation.** `findings.md` Direction 2. Among P1-valid sensitizing vectors,
pick the one that maximizes the t=0 charge perturbation at the measured node, so
the golden is a worst-case bound -- the promise spec 2.5 makes.

**Approach.** Do NOT add a solver. Extend the EXISTING enumeration in stage2: keep
every P1-valid `a` instead of `break`-ing on the first, score each by
`sigma*dV_f(a)` using P2's cap network, pick the max. Exhaustive over `2^|M|`
which is tiny for standard cells (`findings.md` 2.3). Large-`|M|` Dinkelbach/QPBO
is documented but NOT proposed for build.

**Proposed diff (TEXT).**

```
# engine/stages/stage2_sensitize.py
@@ replace "break on first P1 hit" with "collect all, score, argmax":
-    found = None
-    for cp in (0, 1):
-        for vals in product(*choices):
-            a = dict(zip(sides, vals))
-            if controls(cp, a, constr):
-                ...
-                found = (cp, a, setpins, masked); break
-        if found: break
+    candidates = []
+    for cp in (0, 1):
+        for vals in product(*choices):
+            a = dict(zip(sides, vals))
+            if controls(cp, a, constr):
+                masked = [s for s in sides if pin_masked(cp, a, s)]
+                score = charge.bump_score(graph, arc, cp, a, masked)  # sigma*dV_f
+                candidates.append((score, cp, a, masked))
+    found = max(candidates, key=lambda t: t[0])[1:] if candidates else None
```

**Risk.** Medium. Changes WHICH valid vector is chosen -> changes the golden's
masked-pin biases. This is intended (worst-casing) but it alters output for cells
with free masked pins; must be gated behind a flag until validated, and the
chosen vector must still pass P1 (it does -- only P1-valid candidates are scored).
Determinism: ties broken by the existing sorted enumeration order.

**SPICE check.** V2/V3 above, plus: across the candidate vectors, confirm the
t=0-worst-case vector tracks the measured-edge-worst-case vector (the caveat in
`findings.md` 2.4 / open_questions Q4). If it does not track, this proposal is
downgraded to "report the bump per vector" rather than "auto-select worst."

===========================================================================

# COVERAGE EXTENSIBILITY ANALYSIS  (MPW / setup-hold / sync) -- TOP PRIORITY

This section answers the QC lead's first question per arc/cell type: does the
engine have a PHYSICAL PATH to the type (CAN EXTEND), or does a premise of the
current abstraction fail (ARCHITECTURAL WALL)? Tags as in findings.md
(`[CODE]` quoted source, `[STD]` textbook, `[DERIVED]` my derivation,
`[UNVERIFIED -- no SPICE cross-check]`). No engine change is applied.

Two structural facts from the engine read drive every verdict below `[CODE]`:

- F1. The sequential init stage was BUILT FOR HOLD. `stage3_initialize.py`
  hard-codes a hold convention: `cap = 1 if arc.constr_dir == "fall" else 0`
  with reason "HOLD CONVENTION ... the value held just before the constrained
  edge", and the only fixture arc is `hold_cp_d_placeholder`. The engine already
  derives master/slave pre-edge state across a capturing edge.
- F2. The storage labeller is ALREADY MULTI-STAGE. `stage1_ccc.py`:
  `labels[id(core)] = "slave" if i == 0 else ("master" if i == last else
  f"stage{last - i}")` -- it ranks N>=2 cross-coupled storage cores by
  influence-distance to the output and names intermediate stages `stage{k}`.

## Judgment table (the per-type answer to give the QC lead)

| Type | Structural / deterministic part | Other part | VERDICT | One-line physical reason |
|---|---|---|---|---|
| **setup/hold** | CAN EXTEND -- approx. already doing it (F1) | pushout/degradation pass-criterion = measurement layer | **CAN EXTEND** | same master/slave-state-across-the-capturing-edge physics stage3 already derives; setup is the mirror of hold |
| **MPW** | CAN EXTEND -- sensitize pulse path + set pre-pulse internal charge state | min-width SEARCH = simulator + measurement layer | **CAN EXTEND** | MPW deck-gen = sensitization (stage2) + Pillar-3 pre-pulse charge state (stage3) + pulse stimulus; the RC charging that sets the actual minimum is the sim's job (scope guard 8) |
| **sync cell** | CAN EXTEND -- N storage stages (F2) | metastability (MTBF, tau) = statistical / AIQC layer | **SPLIT: structural CAN EXTEND; metastability is a clean BOUNDARY, not a wall** | the deterministic engine's honest X (Pillar-3 non-convergence) IS the metastable locus; quantifying it is statistical |

Headline for the QC lead: **none of the three is an architectural wall.** Two are
direct extensions; the third splits cleanly into a structural part the engine
extends to and a statistical part that was never the deterministic engine's job --
and the seam between them is exactly the engine's existing X semantics.

-----

## CE-1. setup / hold

**(a) Physical requirement.** `[DERIVED]` A setup/hold golden deck for a flop
(rel_pin = CP, constr_pin = D) must: (i) sensitize D as the live capture path
(scan/side inputs masked); (ii) pre-load the master/slave latch to the PRIOR
value (complement of the value to be captured) so the capture yields an
observable Q transition; (iii) apply the capturing CP edge with D transitioning
at a controlled offset relative to that edge. Setup = D must be stable a
sufficient time BEFORE the edge; hold = stable a sufficient time AFTER. The
quantity characterized is the minimum offset at which capture is still correct,
read as the cp2q-delay-degradation (pushout) threshold, not a pure logic flip.

**(b) Current-abstraction gap.** `[CODE]+[DERIVED]`
- Sensitization (i): `stage2_sensitize` already derives and proves it (P1).
- Initial state (ii): `stage3_initialize` already derives it -- this is its
  primary, hold-convention purpose (F1). Master written-node value + cross-coupled
  complement + slave prior value are all computed.
- Stimulus offset (iii): the constraint-offset SEARCH (bisection over the D-to-CP
  separation) is the only piece NOT in the engine -- and it belongs in the
  measurement layer, which stage4 passes through UNCHANGED ("MEASUREMENT (Liberate,
  passed through UNCHANGED)" `[CODE]`). The engine emits the deck for ONE timing
  point; Liberate's block + the search drive the offset.
- The genuine engine gap is small: stage3 hard-codes the hold convention. Setup
  needs the convention PARAMETERIZED by arc_type (which side of the edge the
  D-stability window sits on; the prior-load and sensitization are identical).

**(c) Verdict: CAN EXTEND** (the closest of the three to "already done"). The gap
is a parameterization of an existing stage plus a measurement-layer search, not a
new abstraction. No premise fails.

**(d) Physical reason it extends + hypotheses to TEST.** `[DERIVED]`
Setup and hold are the SAME event -- a value captured at a clock edge -- measured
from opposite sides of the edge. The initial-state physics (latch must hold the
prior value so the transition is observable) is identical and already implemented.
Proposed text diff:

```
# engine/stages/stage3_initialize.py  -- parameterize the convention
-    cap = 1 if arc.constr_dir == "fall" else 0       # HOLD CONVENTION (stated)
+    # convention by arc_type: hold = value held BEFORE the edge; setup = value
+    # that must ARRIVE-and-be-stable to capture. Prior-load is identical.
+    cap = _captured_value(arc)   # branches on arc.arc_type in {hold, setup}
```

Hypotheses to test (NOT assume):
- H1 `[UNVERIFIED]`: the existing prior-load + sensitization, with the convention
  parameterized, produces a setup deck whose P2 passes. Needs a setup fixture arc
  + SPICE.
- H2 `[UNVERIFIED]`: the pushout/degradation pass-criterion is fully expressible
  in the passed-through Liberate measurement block (i.e. the engine need not own
  it). If a setup arc requires the engine to compute the degradation threshold,
  that is a measurement responsibility, not an abstraction gap -- confirm the
  boundary holds for setup as it does for hold.

Risk: low-medium. The prior-load is reused; the only behavioral change is the
convention branch. Setup's "stable before" vs hold's "stable after" must map to
the correct edge-relative stimulus, which is deck timing, not topology.

-----

## CE-2. min pulse width (MPW)

**(a) Physical requirement.** `[DERIVED]` MPW characterizes the narrowest pulse on
rel_pin (a clock, set, or reset) for which the receiving internal node still
transitions PAST THRESHOLD before the pulse ends -- a narrower pulse is
"swallowed" (the node charges partway, then the pulse reverses and it relaxes
back). A golden MPW deck must: (i) sensitize the path so the pulse reaches the
target internal node; (ii) set the target node's PRE-pulse charge state to the
value the pulse must flip away from; (iii) emit a single pulse of width W (the
search parameter) and probe the node's transition completion. The minimum W is
found by the simulator over the search; the engine produces the parameterized
deck.

**(b) Current-abstraction gap.** `[CODE]+[DERIVED]`
- Sensitization (i): stage2 -- present.
- Pre-pulse charge state (ii): for a flop clock-MPW, this is the same prior-load
  stage3 does (F1). For a node that is FLOATING/dynamic before the pulse, the
  correct pre-pulse voltage is exactly a Pillar-3 charge-resolve result (P3/P4).
  So MPW's initial-state requirement sits DIRECTLY on the conduction-graph +
  Pillar-3 charge framework -- no new abstraction.
- Pulse stimulus + completion probe (iii): deck emission. A single narrow pulse is
  a simpler stimulus than the multi-cycle drive-and-settle stage3 already emits;
  W is a parameter supplied by the measurement/search layer.
- What is NOT in the engine and SHOULD NOT BE: the RC charging dynamics that
  decide whether width W is sufficient. Scope guard 8 explicitly forbids
  reimplementing Elmore / transition time -- that is the simulator's job. The
  engine sets t=0 charge state; the sim computes whether the node crossed.

**(c) Verdict: CAN EXTEND.** MPW deck-generation decomposes entirely into
existing pieces (sensitize + Pillar-3 initial charge + pulse emission). No premise
of the abstraction fails. The boundary to state to the QC lead: the engine
GENERATES the MPW deck and sets the charge state; the simulator + width search
find the minimum -- and that division is correct, not a limitation.

**(d) Physical reason it extends + hypotheses to TEST.** `[DERIVED]`
The hypothesis "MPW is a sensitization + internal-node charge-state problem"
HOLDS under analysis: pulse-swallowing IS a charge question -- did the node
accumulate enough charge to cross threshold within W? The engine owns the
boundary conditions of that question (sensitization + initial charge); the
trajectory is the sim's. This turns "we have not done MPW yet" into "MPW is a
direct application of our charge model for the initial state, with the dynamics
left to SPICE."

Hypotheses to test (NOT assume):
- H3 `[UNVERIFIED]`: for a clock-MPW on a standard flop, the pre-pulse state is
  exactly stage3's prior-load (no new charge math needed). Likely true; test on a
  DFF MPW fixture.
- H4 `[UNVERIFIED]`: for an MPW whose target is a dynamic/floating node, the
  Pillar-3 charge resolve gives the correct pre-pulse voltage AND the coupling
  bump (2.5) during the pulse onset does not invalidate the t=0 setup. This is the
  case that most stresses Pillar 3; needs a dynamic-node MPW cell + SPICE.
- H5 (boundary): confirm the engine is NOT expected to PREDICT minimum width
  analytically. If the QC lead expects an analytic min-W, that is out of scope
  (it would duplicate the transient solver). The engine's deliverable is the
  parameterized deck; the search is measurement.

Risk: medium, concentrated in H4 (dynamic-node MPW depends on Pillar 3 being
right). For flop clock-MPW (H3) the risk is low (reuses prior-load).

-----

## CE-3. sync (multi-stage synchronizer) cell

**(a) Physical requirement.** `[DERIVED]+[STD]` A synchronizer is N>=2 flops in
series sampling an asynchronous input to suppress metastability propagation. Its
characterization has TWO distinct parts:
- Structural/deterministic: the ordinary per-stage arcs (delay through each stage,
  setup/hold of each flop). Requires identifying and ordering N storage stages and
  loading them.
- Metastability/statistical: the mean-time-between-failures, governed by the
  resolution time constant tau and aperture Tw `[STD]`:
  `MTBF = exp(t_r / tau) / (T_w * f_clk * f_data)` (Kleeman-Cantoni form). This is
  a DISTRIBUTION over resolution times when the first flop is driven to its
  metastable point -- a measure-zero initial condition with exponential settling.

**(b) Current-abstraction gap.** `[CODE]+[DERIVED]`
- Multi-stage structure: stage1 ALREADY ranks and labels >=2 storage cores and
  names intermediate stages `stage{k}` (F2). CCC + state-node id therefore already
  covers the N-stage skeleton; the per-stage arcs reduce to CE-1 (setup/hold) and
  the existing delay path, applied per stage.
- Multi-stage drive-and-settle: stage3 currently loads master+slave for one flop;
  loading N stages in sequence is a parameter extension (more precycles, ordered
  by the stage{k} labels), not a new abstraction.
- Metastability: the deterministic switch-level + charge engine resolves every
  node to definite 0/1 or X. The metastable state is precisely a node held AT
  threshold whose resolution is statistical/exponential -- which the deterministic
  engine cannot quantify and SHOULD NOT (it has no probability model). Notably,
  Pillar-3's non-convergence X (findings D1.3: a threshold-straddling node whose
  fixpoint oscillates) is exactly the metastable locus. The engine marks WHERE
  metastability lives; it does not measure HOW LONG it lasts.

**(c) Verdict: SPLIT.** Structural part: **CAN EXTEND** (stage1 already
multi-stage; per-stage arcs are CE-1 + delay). Metastability part: a clean
**ARCHITECTURAL BOUNDARY, not a wall** -- it is out of the deterministic engine's
responsibility by design and belongs to the statistical / AIQC layer. The
distinction matters for the QC lead: the engine does not FAIL at sync cells; it
covers their structural characterization and hands the statistical metric across
a seam that coincides with its own honest X.

**(d) Physical reason + the separation hypothesis to TEST.** `[DERIVED]`
The two parts separate because they are different mathematical objects: the
structural arcs are deterministic functions of topology + charge state (engine
territory); MTBF is an expectation over a continuous resolution-time distribution
(statistical territory). The engine can even FEED the statistical layer -- Pillar
3 can parameterize a near-threshold initial node voltage, setting up the
metastable condition the statistical layer then samples (Monte Carlo / analytic
tau extraction).

Hypotheses to test (NOT assume):
- H6 `[UNVERIFIED]`: stage1's multi-stage labelling produces a correct ordered
  stage list for a real 2- or 3-stage sync cell (the influence-distance ranking
  does not collapse two stages or mis-order them). Needs a sync-cell netlist.
- H7 `[UNVERIFIED]`: the structural and metastable parts separate CLEANLY -- i.e.
  every deterministic sync arc is derivable WITHOUT a metastability model, and the
  metastability metric needs ONLY a near-threshold initial condition + a
  statistical layer (no hidden deterministic dependency). If a deterministic arc
  turns out to require a metastability assumption, the seam is not clean and this
  verdict tightens.
- H8 (boundary statement for the QC lead): metastability MTBF/tau is owned by the
  AIQC statistical layer; the deterministic engine's contribution is (1) the
  structural per-stage decks and (2) optionally a Pillar-3-parameterized
  near-threshold initial condition to seed the statistical run. Confirm the AIQC
  layer accepts that handoff object.

Risk: structural -- low/medium (reuses F2 + CE-1). Metastability -- not an engine
risk; it is a scope boundary that must be AGREED with the AIQC owner, not built
here.

-----

## Cross-type summary for the QC conversation

The single most important framing: the engine's abstraction is "sensitize a path
+ resolve internal charge/logic state + emit a parameterized deck; leave dynamics,
search, and statistics to the simulator and the measurement/statistical layers."
Measured against that boundary:

- setup/hold and MPW are INSIDE it (deterministic deck-gen) -> CAN EXTEND.
- sync is INSIDE it structurally and OUTSIDE it for the statistical metric -> CAN
  EXTEND for the structure, clean handoff for metastability.

No type requires overturning a premise of the abstraction. The one thing to NOT
claim: that the engine predicts minimum pulse width, setup/hold pushout
thresholds, or MTBF analytically -- those are the simulator's and the statistical
layer's outputs. Claiming them would mean reimplementing the transient solver or
a probability model, which is explicitly out of scope. The defensible claim is
deck-generation coverage, and that reaches all three.
