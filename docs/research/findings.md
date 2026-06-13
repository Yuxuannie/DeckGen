# Pillar 3 -- Research Findings (charge-resolution direction)

Status: research only, pre-implementation. Companion to
`pillar3_charge_resolve_spec.md` (the input spec) and `proposals.md`.
Branch: `research/autonomous-explore`. ASCII-only.

Grounding: the spec's "current-state assessment" cites files on
`feat/phase-2b-engine` that do not exist on this branch. I fetched that branch
read-only and read `engine/switchlevel.py`, `engine/stages/stage0_parse.py`,
`engine/stages/stage1_ccc.py`, `engine/stages/stage2_sensitize.py`,
`engine/stages/stage3_initialize.py`, `engine/stages/stage4_deckgen.py`,
`engine/stages/stage5_verify.py`, `engine/types.py`, `engine/pipeline.py`, and
the LPE fixture generator `engine/fixtures/_gen_sdf_lpe.py`. All code claims
below are quoted from that read; all PHYSICS claims are tagged.

## How to read the tags

- `[STD]` -- a standard textbook / literature result. The algebra is established;
  I re-derive it so it can be checked, but it is not my invention.
- `[DERIVED]` -- my own derivation built on `[STD]` results. Algebra is shown in
  full; it is internally checkable but is still UNVERIFIED as physics.
- `[UNVERIFIED -- no SPICE cross-check]` -- a claim about what the real cell /
  real LPE / real simulator will do. CANNOT be confirmed in this session.
- `[CODE]` -- a fact about the existing engine source, quoted from the read.

The blanket rule for this whole document: **no derived physical result is stated
as established fact.** Where I write "the node settles to V", read "the model
predicts the node settles to V, UNVERIFIED."

-----

## 0. Executive summary of what I found

1. The spec's load-bearing type mismatch is real and unstated: `switchlevel.evaluate`
   returns logic `{0, 1, None}` `[CODE]`, but the charge-share formula needs analog
   voltages. "Last-driven value" is therefore not a lookup -- it is the output of an
   ORDERED, phase-by-phase voltage recurrence, and the spec's one-shot framing is
   only correct for a restricted (but common) class of nodes. (Direction 1.)

2. The spec's "latent fixpoint" (classification depends on voltages that depend on
   classification) is real but BOUNDED: it only bites when a floating node fans out
   to a transistor gate. For floating nodes that drive no gate -- which includes the
   spec's headline example, a series-stack PDN internal node -- the
   classify-then-resolve pipeline is provably single-pass-correct. I give the
   dividing criterion. (Direction 1.)

3. The spec's 2.4 conflates two different problems under one scalar formula. The
   scalar average is exact ONLY for nodes that are channel-connected (merge to one
   conductor) with no free-free coupling. The correct general procedure is
   two-step: contract ON-connected groups by grounded-cap charge sum, THEN solve a
   coupling matrix over the contracted super-nodes. The inter-node coupling cap
   provably drops out of the merge step but not the non-merged step. (Direction 3,
   with full algebra + a runnable prototype.)

4. Worst-case vector selection (spec 2.5) is a ratio (fractional) pseudo-Boolean
   optimization. For real standard cells the free-variable count is tiny and the
   engine ALREADY enumerates it (`product(*choices)` in stage2 `[CODE]`); the
   correct, low-risk move is to score that existing enumeration instead of
   `break`-ing on the first hit. I give the objective and the large-case solver.
   (Direction 2.)

5. The charge model's natural features are already dimensionless ratios, which is
   the cross-PDK transfer handle the AIQC/StatCHAR story wants -- but they only
   transfer if `V_th/VDD` is carried as a covariate. (Direction 4.)

-----

## Direction 1: phase-ordered charge recurrence and the classification fixpoint

### 1.1 The type mismatch the spec does not name `[CODE]`

`engine/switchlevel.py::evaluate` returns `Dict[str, Optional[int]]` -- each net
is `0`, `1`, or `None` (X). Its resolution rule for a channel-connected group is
quoted verbatim:

```
drivers = {val[m] for m in members if m in strong and val[m] is not None}
if len(drivers) == 1:    v = that driver
elif len(drivers) > 1:   v = None        # conflicting strong drivers -> X
else:                    continue        # undriven -> leave as-is (X)
```

So a floating group comes back as `None`. The spec (2.3 class 2) says such a node
"carries a known last-driven charge. V = last-driven value." But `evaluate`
yields a LOGIC value, not a voltage, and only for DRIVEN nodes. The voltage of a
floating node is not in the resolver's output at all. This is the precise seam
Pillar 3 must add -- and it is an analog quantity layered on a logic resolver.

### 1.2 Why "last-driven value" is not a lookup `[DERIVED]`

Consider a node n that is:

- phase p0: driven to logic 1 by a real path  -> V_n(p0) = VDD          `[STD]`
- phase p1: isolated (driving path off), no charge-share partner        -> V_n(p1) = VDD (ideal hold)
- phase p2: channel-connects through an ON device to node m at 0 V, no rail in the group

At p2 the group {n, m} is floating, so by charge conservation `[STD]`

```
V(p2) = (Cg_n * V_n(p1) + Cg_m * V_m(p1)) / (Cg_n + Cg_m)
```

which is NOT VDD and NOT 0 -- it is sub-rail. If a later phase p3 re-isolates n,
its held voltage is this sub-rail value, and any subsequent charge-share uses it
as the entry voltage. So the quantity the resolve needs at the measured instant
is `V_n(p_m)`, the end of a **voltage trajectory across phases**, where each
phase's output is the next phase's input:

```
[DERIVED]  V(p_{k}) = Resolve( conduction(p_k), Cg, Cc, V(p_{k-1}) )
```

`Resolve` is the charge solve of Direction 3. The spec's class-2 / class-3
dichotomy is a property of the FINAL phase only; "driven at some earlier phase"
does not pin the value, because an intervening charge-share can move it. This is
the first concrete deepening: **replace "last-driven value lookup" with an
explicit, ordered per-phase recurrence over the drive-and-settle phase list that
stage3 already plans** (`SensitizationResult` carries the phase list `[CODE]`:
`stimulus` lines + `precycle_count`).

This recurrence is still UNVERIFIED as physics: it assumes ideal hold between
phases (no sub-threshold leakage, no gate leakage discharging the node over the
settle time). `[UNVERIFIED -- no SPICE cross-check]` Whether the hold is "ideal
enough" over the actual settle window is exactly a SPICE question (open_questions
Q1).

### 1.3 The classification/resolve fixpoint, and when it is vacuous `[DERIVED]`

The spec's algorithm (SS3) runs: (step 2-3) switch-level classification, THEN
(step 4-5) charge resolve + coupling. That ordering is a linear pipeline. But
2.5 says a coupling bump "can push f across a device threshold, changing
sub-threshold conduction or the next charge-share." Conduction is what defines
the charge-share groups (step 2-3). So in general:

```
conduction  ->  charge-share groups  ->  resolved voltages  ->  gate levels
     ^                                                              |
     +--------------------------------------------------------------+
```

This is a fixpoint, not a pipeline. Define the intra-phase operator T on the
vector of floating-node voltages v (entry voltages held fixed):

```
[DERIVED]
  T(v): 1. for each floating gate-net g, logic(g) = 1 if v_g > V_th_n else 0
           (and the PMOS-side comparison vs VDD - |V_th_p|);
        2. recompute which transistors conduct from logic(.);
        3. recompute channel-connected groups;
        4. charge-resolve groups -> v'.
  Fixpoint: v* = T(v*).
```

**Key result -- the fixpoint is vacuous (single pass exact) iff no floating node
fans out to a transistor gate.** `[DERIVED]`

Proof sketch. Step 1 of T only reads `v_g` for nets g that are SOME transistor's
gate. If the set of floating nets is disjoint from the set of gate-nets, then
logic(.) in step 1 is unchanged by v, so steps 2-3 (conduction, groups) are
independent of v, and T reduces to a single application of step 4. No iteration
is possible to change the partition; the spec's classify-then-resolve order is
then correct as written. QED (modulo the threshold model in step 1, which is
`[UNVERIFIED]`).

Corollary -- the spec's headline case is in the vacuous class. `[DERIVED]` A
series-stack PDN internal node (the mid-node of two stacked NMOS in a NAND/AOI
pulldown) connects only to transistor sources/drains, never to a gate -- the
same structural fact stage1_ccc relies on `[CODE]`: "Series-stack internal nodes
are drains/sources only -- never gates -- so intersecting the SCC with gate-nets
drops them." So for the cells the spec foregrounds, classify-then-resolve needs
no fixpoint iteration. This is a reassuring, checkable boundary -- and it is
exactly the set of cells worth doing FIRST.

**When the fixpoint is NOT vacuous** (a floating node drives a gate): keepers,
bootstrap nodes, charge-sharing into a feedback inverter. Here T can oscillate:
a bump lifts v_g above V_th, turning on a device that discharges the node below
V_th, turning it off, recharging it. `[DERIVED]` This is a step-function
(threshold) composed with an averaging map; averaging alone is a contraction
`[STD]` (convex combination, spectral radius < 1 for positive caps with a rail
anchor), but the threshold quantization destroys continuity and a 2-cycle can
exist. The physically correct response is the one switch-level simulators
already take for unresolvable nodes: bounded iteration, and **declare X on
non-convergence** -- which mirrors `evaluate`'s existing X semantics `[CODE]`.
An X here is information, not failure: it flags a metastable / charge-race node
to the reviewer instead of fabricating a voltage.

### 1.4 What this buys the engine

- The recurrence makes the "history replay" in spec SS3 step 3 precise and
  ordered, and it correctly handles driven-then-perturbed nodes the lookup misses.
- The vacuous-fixpoint criterion is a cheap structural test (is the floating net
  in `gate_nets`? stage1 already computes `gate_nets` `[CODE]`) that tells the
  engine when it may use the simple pipeline vs when it must iterate-or-X. It
  turns the spec's hand-wave ("can push across threshold") into a decidable gate.

-----

## Direction 2: worst-case sensitizing-vector selection as optimization

### 2.1 What is actually free `[CODE]`

stage2_sensitize enumerates side-pin assignments with
`choices = [(forced[s],) if s in forced else (0, 1) for s in sides]` and
`for vals in product(*choices)`, then **`break`s on the first assignment that
makes the constraint pin control capture**. It then partitions sides into
`set_pins` (toggling changes capture -> value required) and `masked_pins`
(capture independent -> "static hold ... value non-critical").

The masked pins' values are non-critical FOR LOGIC. They are NOT non-critical for
charge: they set which transistors are on, hence the cap topology seen by a
floating node and the coupling-bump magnitude. So among all P1-valid vectors,
there is freedom that Pillar 2 currently resolves arbitrarily (first hit) but
that Pillar 3 should resolve to the WORST case, so the golden is a true bound.

### 2.2 The objective `[DERIVED]`

Let `M` = masked (logic-non-critical) side pins, each free in `{0,1}` subject to
the arc's when-constraints; let `a in {0,1}^M` be an assignment. Let `f` be the
floating node whose charge sets the measured edge (e.g. a PDN internal node on
the active path, or a dynamic output). For a single switching aggressor `g*`
(swing `dV`), the capacitive-divider bump is `[STD]`:

```
dV_f(a) = C_c(f, g* ; a) / C_total(f ; a) * dV
C_total(f ; a) = C_g(f) + sum over neighbors n connected-to-f-under-a of C_c(f, n ; a)
```

The objective for a worst-case golden is to **erode the measurement margin**:

```
[DERIVED]
  maximize_a  sigma * dV_f(a)        subject to   P1(a) holds  AND  f floats under a
```

where `sigma in {+1, -1}` is chosen so the bump pushes the measured node the
wrong way (toward late/early capture for setup/hold; toward a glitch for delay).
The `P1(a) holds` constraint keeps the chosen vector a VALID sensitization -- we
worst-case within the legal set, we do not change the arc. The `f floats`
constraint excludes assignments that accidentally give f a rail path (then there
is no trapped charge to perturb).

### 2.3 Structure of the program `[DERIVED]`

`dV_f(a) = N(a) / D(a)` where both `N` (the relevant coupling cap, gated on by
the literals that keep g* coupled to f) and `D = C_total` (a sum of cap terms
gated by transistor-on indicators) are PSEUDO-BOOLEAN functions of `a`. So this
is a 0/1 FRACTIONAL program. Two regimes:

- **Small `|M|` (the real case).** Standard cells have 0-4 free masked side pins.
  `2^|M| <= 16`. EXHAUSTIVE enumeration is exact and trivial -- and the engine
  ALREADY HAS THE LOOP (`product(*choices)`). The only change is to not `break`
  on first P1 hit but to keep every P1-valid `a`, score each by `sigma*dV_f(a)`,
  and pick the max. Exactness is immediate: we evaluate the objective on every
  feasible point. `[DERIVED]`

- **Large `|M|` (hypothetical compound cells).** Use Dinkelbach's parametric
  method `[STD]`: maximize `N(a) - lambda*D(a)` and binary-search `lambda` to the
  ratio's optimum. Each subproblem is pseudo-Boolean maximization; if
  `N - lambda*D` is supermodular it is solvable exactly by max-flow / QPBO `[STD]`.
  Whether it IS supermodular depends on the cap-gating sign structure and is NOT
  guaranteed -- a real open question (open_questions Q3). For the engine as it
  stands this regime is academic; I flag it but do not propose building it.

### 2.4 Honest caveat on "worst case"

`dV_f` is an INSTANTANEOUS divider bump `[STD]`. The real perturbation then
relaxes through whatever resistive path exists, on a timescale the SPICE run
computes (scope guard 8). Picking the vector that maximizes the t=0 bump is NOT
provably the vector that maximizes the measured-edge error -- the relaxation
could reorder them. `[UNVERIFIED -- no SPICE cross-check]` So the proposal (2.2)
is "worst-case INITIAL charge perturbation," and the validation protocol must
confirm the t=0 worst case tracks the measured worst case across a few cells
before this is trusted as a true bound (open_questions Q4).

-----

## Direction 3: when 2.4 does not collapse to scalar (full algebra)

### 3.1 The scalar formula and its exact scope `[STD] + [DERIVED]`

Two nodes a, b, each with a grounded cap `Cg_a, Cg_b` and a coupling cap `Cab`
between them, at entry voltages `Va, Vb`. They become shorted (one conductor).
Conserve charge on the merged conductor referenced to ground. Charge on a's
plates before merge: `Cg_a*Va + Cab*(Va - Vb)`; on b's: `Cg_b*Vb + Cab*(Vb - Va)`.
Sum (the conserved total on the merged conductor):

```
[DERIVED]
  Q = Cg_a*Va + Cg_b*Vb + Cab*(Va-Vb) + Cab*(Vb-Va)
    = Cg_a*Va + Cg_b*Vb          <-- the Cab terms CANCEL exactly
```

After merge both plates of Cab sit at the common V, so Cab stores zero and the
merged capacitance to ground is `Cg_a + Cg_b`. Hence

```
[DERIVED]  V = (Cg_a*Va + Cg_b*Vb) / (Cg_a + Cg_b)
```

**The inter-node coupling cap does not appear in the merge result.** This is why
the spec's scalar formula uses only grounded caps -- but the spec never states
the precondition (the nodes must actually merge). The prototype's `demo_scalar`
reproduces this (0.346 V for the example) and `demo_fixed_coupling` confirms the
divider sub-case (0.150 V), both hand-checked for arithmetic.

### 3.2 Where it breaks `[DERIVED]`

The scalar average is wrong whenever the floating set is NOT a single merged
conductor. Four cases:

1. **Free-free coupling without merge.** Two floating nodes f1, f2 that are NOT
   channel-connected but ARE coupled by Cc, each grounded. They do not equalize;
   they settle to distinct voltages coupled through Cc. The prototype's `demo_coupled`
   shows the naive merge gives 0.225 V while the correct matrix solve gives
   f1 = 0.3115 V, f2 = 0.1385 V -- a 90 mV / 90 mV split the average erases.
2. **Coupling to a fixed non-rail node** (a held internal net, or a neighbor
   mid-swing). It enters as an RHS source term, shifting each free node; the pure
   average is wrong even for a single free node.
3. **Partial conduction** (a sub-threshold device that is neither short nor open).
   This is outside the charge model entirely (scope guard 8) -- flag, do not solve.
4. **Singular island** (case 3.4 below).

### 3.3 The correct two-step procedure `[DERIVED]`

```
Step A -- contract. Find channel-connected groups among floating nodes (ON
  devices only). Each group merges to one super-node with
    Cg(super)  = sum of member grounded caps
    Q(super)   = sum of member (Cg_i * Ventry_i)      [grounded-cap charge]
  (coupling caps internal to a group are dropped -- proven in 3.1).

Step B -- couple. Build the capacitance matrix over the super-nodes:
    A[i][i] = Cg(super_i) + sum_j Cc(i, j)   over ALL coupling neighbors j
    A[i][k] = -Cc(i, k)                      for free super-node neighbors k
    b[i]    = Q(super_i) + sum_{fixed m} Cc(i, m) * V_fixed(m)
  Solve  A v = b.
```

This is exactly `charge_resolve()` in the prototype. The assembly is the nodal
charge-balance of spec 2.4, but with the crucial pre-contraction step the spec
omits -- which is what makes the inter-node caps behave correctly (cancel inside
a merge, act as real elements between non-merged nodes).

The matrix `A` is a (weighted graph) Laplacian-plus-grounding `[STD]`. It is the
standard capacitance / Kirchhoff matrix; the scalar formula is its 1x1 reduction
after contraction.

### 3.4 Degeneracy: the singular case `[DERIVED]`

`A` is singular exactly when a connected component of the super-node coupling
graph has NO grounded cap and NO coupling to any fixed/rail node -- a perfectly
isolated coupling-only island. Physically its absolute DC level is undetermined
(only inter-node differences are fixed by trapped charge), so the model MUST
return X, never a number. The prototype's `demo_singular` detects this (the
Gaussian-elimination pivot underflows -> `solve` returns `None` -> nets report
`None`). Detection rule for the engine: per connected component of the coupling
graph, require at least one node with `Cg > 0` or a coupling edge to a fixed
node; else X + needs-evidence. `[DERIVED]`

This matters for trust: the integrity-floor argument (spec SS0) cuts both ways --
class-3 nodes can only use `.ic` (they are by definition unreachable by a drive
path), so the golden's correctness rests on THIS arithmetic. The singular guard
ensures the arithmetic refuses to invent a value it cannot determine, consistent
with CLAUDE.md "never fail silently / never drop arcs without telling the user."

-----

## Direction 4: cross-PDK dimensionless normalization (StatCHAR bridge)

### 4.1 The natural features are already ratios `[DERIVED]`

Absolute farads scale with node geometry and PDK; the charge model's outputs are
ratios that are geometry/topology-driven and PDK-light:

- charge-share weights `w_i = Cg_i / sum_j Cg_j`  (simplex; the merge result is
  `sum_i w_i * Ventry_i`) -- dimensionless by construction.
- coupling divider `alpha(f, g) = Cc(f,g) / C_total(f)` in `[0, 1)` -- the t=0
  bump per unit aggressor swing.
- trapped charge in rail units `Ventry_i / VDD`.
- ground fraction `Cg(f) / C_total(f)` (1 minus total coupling fraction).

A per-floating-node feature vector of these is PDK-blind in the sense that it
strips the absolute-farad scale. This is the same Layer-B object the StatCHAR
anchor (spec SS6) reduces -- the bridge to the AIQC cross-node story is: emit
these ratios alongside the resolved voltage.

### 4.2 The covariate that must ride along `[DERIVED]`

Ratios are not sufficient for transfer of the THRESHOLD-CROSSING prediction. Whether
a bump `alpha*dV` flips a downstream gate depends on `(Ventry + alpha*dV)` vs
`V_th`, and `V_th/VDD` differs across nodes/corners/PDKs. So the dimensionless
feature set must carry `V_th/VDD` (per device flavour) as a covariate, else a
model trained on one node's ratios mispredicts conduction on another. `[UNVERIFIED
-- no SPICE cross-check]` for the magnitude of this effect; the claim that the
covariate is NECESSARY is `[DERIVED]` (it appears in the crossing inequality).

-----

## Direction 5: pointer to the validation protocol

The full SPICE validation protocol is a deliverable in `proposals.md` (P6),
because it is actionable rather than a finding. The one finding worth stating
here: the `--verify` cross-check the spec proposes (deck with `.ic` vs deck with
long pre-conditioning and no `.ic`) is the RIGHT discriminator, because it
separates two error sources the engine must not conflate -- a wrong charge VALUE
(both decks wrong the same way -> agreement hides it) vs a wrong STIMULUS plan
(the no-`.ic` deck diverges). The protocol must therefore ALSO include an
absolute check against a hand-calc / direct transient, not only the
`.ic`-vs-settle relative check. `[DERIVED]`

-----

## Appendix A: structural facts relied on, quoted from the engine read `[CODE]`

- `switchlevel.evaluate -> Dict[str, Optional[int]]`; undriven group "leave as-is (X)".
- `stage0_parse.parse`: shorts every `R` (union-find), maps raw nodes to logical
  nets via `node_to_net`, and "C / anything else: ignored for connectivity."
- `types.DeviceGraph` carries `node_to_net: Dict[str,str]`; `types.Derivation`
  is the (value, reason, stage) provenance wrapper; `InitializationResult` has
  `required_state`, `stimulus`, `precycle_count`, `probes`.
- `stage1_ccc`: builds `gate_nets`, finds storage as feedback SCCs intersected
  with gate-nets, explicitly noting series-stack nodes "are drains/sources only
  -- never gates."
- `stage2_sensitize`: `product(*choices)` enumeration, `break` on first P1 hit,
  masked-pin "value non-critical."
- LPE cap-line syntax (from `_gen_sdf_lpe.py`): `C<name> nodeA nodeB farads`,
  e.g. grounded `CA1 XMLA0#g VSS 1.2e-18`, coupling `CF1 XMLA0#g XSLA0#g 3.4e-19`.
  Cap endpoints are raw extracted nodes mapped to logical nets via `node_to_net`.
