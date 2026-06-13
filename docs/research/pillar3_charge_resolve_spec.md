# DeckGen v2 / topo_core -- Research Spec: Pillar 3, Floating-Node LPE Charge Resolution

Status: research + design, pre-implementation. Hand to Claude Code as the spec.
Scope: the initialization theory (Pillar 3 of the sensitization/initialization
story). ASCII-only to match repo convention (CLAUDE.md: zero non-ASCII bytes).

-----

## 0. One-paragraph summary

A floating internal node has no DC operating point: with no resistive path to a
rail its row in the conductance matrix is singular. Its voltage is therefore an
INITIAL CONDITION set by the charge trapped on its capacitance when it was last
driven, held until it is reconnected or perturbed by coupling. The switch-level
resolver already tells us WHICH nodes float (it returns X for them). The missing
half is WHAT VOLTAGE they hold, and that is fixed by the LPE capacitance network
plus the pre-conditioning history. Pillar 3 builds that missing half. It is a
charge/history computation, not an operating-point computation, and it is the
integrity floor of the golden: a wrong internal initial charge makes the golden
delay wrong, which makes the reference we validate Liberate/PrimeLib against
itself wrong.

-----

## 1. Current-state assessment (feat/phase-2b-engine, read 2026-06-13)

What exists and is reusable as-is:

- `engine/switchlevel.py` -- union-find switch-level Boolean resolver, "Bryant
  minus strengths". Resolves each net to 0/1/X by conduction to a unique strong
  driver. Breaks cross-coupled feedback for latch data-path analysis. KEY LINE:
  undriven channel-connected groups are left as X ("undriven -> leave as-is").
  This is exactly the hook point for Pillar 3.
- `engine/stages/stage0_parse.py` -- Layer A de-parasitic parse. Shorts every
  parasitic R, union-find contracts raw extracted nodes (`Xdev#d`) into logical
  nets. CORRECT for connectivity. BUT: it explicitly DISCARDS parasitic C
  ("C is to-ground/coupling and irrelevant to DC connectivity"). For Pillar 3
  the C is not irrelevant -- it is the entire answer for a floating node.
- `engine/types.py` -- IR with a `Derivation` provenance wrapper (value + reason
  + stage). `DeviceGraph.node_to_net` maps raw extracted node -> logical net.
    `InitializationResult.required_state` is Derivation-keyed.
- `engine/stages/stage3_initialize.py` -- DERIVE-ONLY. Handles SEQUENTIAL
  state-node initialization only (master/slave latch logic values via
  drive-and-settle, feedback broken). Does NOT resolve the analog voltage of
  floating COMBINATIONAL internal nodes (series-stack internal nodes, dynamic
  nodes, isolated taps).

The precise gap: there is a logical resolver and a sequential-state planner, but
no parasitic-charge resolver for floating combinational internal nodes, because
the C network is thrown away at parse time.

-----

## 2. Theory

### 2.1 The reframe: floating = initial condition, not operating point

DC nodal analysis solves G v = i for node voltages. A node with no resistive
path to any source contributes a zero row/column to G; the system is singular
and the node voltage is undefined. SPICE only resolves it through `.ic` (forced
initial value, capacitor holds it) or by a real drive path in the stimulus.

Physically the node is a capacitor that retains the charge Q = C * V_lastdriven
from the last time it was connected to a driver, and floats at V = Q / C until
(a) it is reconnected to a driver, (b) it shares charge with another node when an
intervening transistor turns on, or (c) a coupling cap to a switching neighbor
injects charge. All three are computable from the switch-level history plus the
LPE C network.

Consequence for the engine: Pillar 3 does NOT run a DC solve on floating nodes.
It replays the switch-level state across the pre-conditioning phases to find each
node's last-driven charge, then applies charge conservation and coupling at the
measured instant.

### 2.2 Two layers of the same LPE data

- Layer A (exists): short R, contract -> logical-net connectivity graph. Used
  for CCC and switch-level resolve. C dropped.
- Layer B (to add): retain the C network on the raw extracted nodes, aggregated
  up to logical nets via `node_to_net`. Two kinds of cap:
  - grounded cap C_g(n): node n to a rail / AC ground (sum of its to-substrate
    and to-rail caps);
  - coupling cap C_c(n,m): between two signal nodes n and m.
    Layer B is only consulted for nodes Layer A could not drive to a rail. The two
    layers are the concrete form of the "double-layer IR".

### 2.3 Node classification at the measured pre-edge instant

Given the sensitization vector S* and the pre-edge logic state, run the
switch-level resolver. Classify every net:

1. DRIVEN -- in a channel-connected group with a unique strong driver. V = rail.
   The simulator sets this naturally from the stimulus; no `.ic` needed.
1. SETTLE-REACHABLE FLOATING -- X at the measured instant, but a drive path
   existed in an earlier pre-conditioning phase, so it carries a known
   last-driven charge. V = last-driven value. Preferred realization: extend the
   drive-and-settle so a real path charges it, then release (most
   golden-defensible -- the simulator computes the charge with full device
   physics, nothing is hand-asserted).
1. TRULY FLOATING / CHARGE-SHARED -- never reachable by any stimulus drive path,
   or a set of mutually isolated nodes that equalize through an ON transistor
   with no rail path. V is fixed by charge conservation over Layer B; emit `.ic`.

### 2.4 Charge-conservation resolve (class 3)

For a group of nodes that become channel-connected through ON transistors but
have no path to a rail, each entering the phase at voltage V_i with total
grounded capacitance C_i:

```
V_settled = (sum_i C_i * V_i) / (sum_i C_i)
```

This is the classic charge-sharing result. C_i is taken from the extracted LPE
(Layer B), not estimated -- that is the whole reason this is golden-grade and
IRSIM's per-node estimated caps are not.

General case (coupling to nodes held fixed at u_k during the settle): write the
nodal charge-balance for each free node n,

```
sum_m C(n,m) * (V_n - V_m) + C_g(n) * (V_n - V_rail(n)) = Q_trapped(n)
```

where m ranges over capacitively-coupled neighbors (free or fixed). This is a
small dense linear system; assemble the capacitance matrix and solve with numpy.
Most standard-cell internal-node cases collapse to the scalar formula above; keep
the linear solve for groups with genuine internal coupling structure.

### 2.5 Coupling bump -- where Pillar 3 feeds back into Pillar 2

A floating node f coupled by C_c to a neighbor that swings by dV between the
settle and the measured edge receives a capacitive-divider kick:

```
dV_f = (C_c / C_total(f)) * dV ,  C_total(f) = C_g(f) + sum coupling caps of f
```

This can push f across a device threshold, changing sub-threshold conduction or
the next charge-share. Because topo_core holds the coupling caps from LPE
(IRSIM, using lumped per-node caps, cannot), it can both compute the bump and
choose the worst-case sensitizing vector that maximizes/minimizes it. This is the
concrete mechanism by which "parasitic-aware" upgrades worst-case vector
selection -- the promise Pillar 2 made, discharged here with real numbers.

### 2.6 Translation to the SPICE deck

- PRIMARY -- drive-and-settle. Extend pre-conditioning so every class-2 node is
  physically driven to its target charge by a real path, then released. No
  hand-asserted `.ic`; the simulator computes the charge. Generalizes the
  existing stage3 sequential plan to all internal nodes, and VERIFIES (by
  replaying switch-level history) that the plan actually reaches each node.
- FALLBACK -- `.ic v(node)=V` with transient UIC for class-3 nodes that no
  stimulus path can reach. Each `.ic` is wrapped in a Derivation carrying the
  charge math, so the deck is auditable.
- DO NOT use `.nodeset` for held charge. `.nodeset` only biases DC convergence
  and the solver may relax away from it; it does not model trapped charge on a
  floating node. (`.nodeset`'s legitimate use -- breaking a bistable latch's DC
  symmetry -- is already handled by feedback-breaking, a separate concern.)
- Probe every resolved node for P2 so the verdict can confirm the held voltage
  matched intent.

-----

## 3. Algorithm (implementable)

Inputs: DeviceGraph (with Layer-B caps), CCCResult, Arc, SensitizationResult
(side biases + pre-edge logic state + the drive-and-settle phase list).

1. Build cap graph Cg: map each raw-node cap to its logical net via
   `node_to_net`; accumulate grounded caps C_g(net) and coupling caps
   C_c(net_a, net_b). Caps whose both ends land on the same logical net vanish
   (intra-net); record that as a derivation.
1. Switch-level resolve at the measured instant with S* (reuse
   `switchlevel.evaluate`). Collect nets that come back X.
1. For each X net, replay `evaluate` across the pre-conditioning phases (earliest
   to latest). If DRIVEN in some phase and not contradicted afterward -> class 2,
   last-driven value. Else -> class 3.
1. For class-3 nets, group by ON-transistor connectivity at the measured instant;
   run the charge-conservation resolve (2.4) per group -> settled V.
1. Apply coupling bumps (2.5) for any neighbor that switches between settle and
   measured instant.
1. Emit: extend drive-and-settle stimulus for class 2; Derivation-wrapped `.ic`
   for class 3; probes for all resolved nets. Extend the existing sequential
   logic exactly as today (do not regress it).

Determinism: sort nets/groups by name before solving so output is stable
(matches the existing deterministic-derivation contract).

-----

## 4. IR / data-structure changes (engine/types.py, stage0_parse.py)

- `DeviceGraph`: add `caps: List[Cap]`, where
  `Cap = (a: str, b: str, farads: float, raw: str)` with `b == "0"`/rail for a
  grounded cap. Keep raw provenance. Optionally a derived
  `cap_network: Dict[net, {"g": float, "c": Dict[net, float]}]` aggregated to
  logical nets.
- `stage0_parse.py`: stop discarding the `C...` lines. Record them into
  `DeviceGraph.caps`. Leave Layer A (R-short connectivity) untouched.
- `InitializationResult`: add
  `ic_lines: List[Derivation]` (value = `"v(x1.<node>)=<V>"`, reason = charge
  math) and `node_class: Dict[str, str]` (driven/settle/floating) for the
  inspectable screenshot. Extend `required_state` to include resolved internal
  nets.

Keep everything PDK-blind and name-blind: classification must come from structure

- extracted caps, never from net-name heuristics (matches the stage0 ethos).

-----

## 5. Reusable repos and how to use each

- IRSIM (opencircuitdesign.com, maintained by T. Edwards). The canonical
  switch-level + charge-sharing simulator. Two models: switch (logic; used for
  initialization/functionality) and linear (transistor = R in series with a
  switch, each node a C; RC network -> node values and transition times via
  C.-Y. Chu's model). USE AS ALGORITHMIC REFERENCE ONLY for the charge-share
  resolve. CAVEATS that make it unusable as a drop-in for golden: (a) it uses
  ESTIMATED per-node caps from a `.prm` process file, not the extracted LPE C;
  (b) it treats isolated nodes as holding a constant value and its own docs call
  charge-sharing-dependent circuits "non-realistic"; (c) it is GPL C -- do not
  link into the TSMC tool. Reimplement the resolve in Python against the real
  LPE caps.
- eda-netlist-parser (PyPI, pure Python): parses SPICE/Spectre/CDL/DSPF including
  parasitic R and C. Candidate for Layer-B retention IF its DSPF coverage matches
  the kit's LPE subckt format. If not, the smaller change is to extend the
  existing stage0 parser to keep the C lines it already sees (no new dependency,
  no format risk).
- networkx (or plain numpy): build the cap graph / assemble the small dense
  capacitance matrix for the 2.4 linear solve. numpy alone is enough for the
  scalar and small-system cases; networkx only if grouping logic gets large.
- OpenTimer/Parser-SPEF (C++ header-only): only relevant if any input arrives as
  standalone SPEF rather than embedded-DSPF subckt. Likely not needed.

License note: keep the implementation clean-room. Study IRSIM's algorithm and
Chu's model; do not copy GPL source into the repo.

-----

## 6. Literature anchors (provenance for SCLD trust)

The point of citing these is that the resolve is grounded theory, not invented:

- Bryant switch-level model: steady-state node resolution by driver strength,
  X for unresolved. `switchlevel.py` is "Bryant minus strengths"; Pillar 3 adds
  the charge layer Bryant's pure-logic model leaves as X.
- C.-Y. Chu, "Improved Models for Switch-Level Simulation" (the model IRSIM's
  linear mode implements): Thevenin + node-capacitance treatment of the
  surrounding network. Closest formal treatment of the floating-node / charge-
  share resolve; cite as the theoretical basis for 2.4.
- Switch-level charge-sharing via series-parallel / tree bicomponent
  decomposition with driving-point resistance and Elmore delay (the classic
  switch-level-timing patents): the algorithmic structure for decomposing the
  resolve efficiently if a group is large.
- StatCHAR (Cheng et al., ASP-DAC 2024): represents transistors + parasitic RC as
  heterogeneous graph nodes with parasitic-RC reduction. External validation that
  retaining and reducing the LPE RC network is the right substrate; also the
  bridge to the AIQC cross-node feature story (same Layer-B object).

-----

## 7. Validation plan (degeneration first -- earns the right to the hard cases)

- Scalar hand-calc: a two-node charge share (precharged dynamic node C1 at V1,
  isolated cap C2 at V2) must match V = (C1 V1 + C2 V2)/(C1+C2) to numerical tol.
- Series-stack internal node: a NAND/AOI PDN internal node, precharged then
  isolated, resolved by topo_core must match a SPICE drive-and-settle transient
  (no `.ic`) settling value within tol. This is the "reproduce known-good" gate.
- --verify cross-check: generate the deck twice -- once with topo_core `.ic`,
  once with a long pre-conditioning and no `.ic` -- and confirm P2 sees the same
  measured edge. Divergence means the charge model or the stimulus is wrong; it
  must be surfaced, never hidden (matches the CLAUDE.md "never drop arcs
  silently" rule).
- Reuse the AIOI21 ground-truth discipline already in tests/: add an internal-
  node initialization assertion for a cell whose stack internal node is known.

-----

## 8. Scope guards (what NOT to build)

- This is initialization (t=0 charge state) resolve, NOT a transient RC
  simulator. The FMC SPICE run computes the dynamics; topo_core only sets the
  correct starting charge and proves which nodes need it. Do not reimplement
  Elmore / transition-time -- that is the simulator's job and duplicates
  IRSIM/SPICE.
- Do not run a DC operating-point solve on floating nodes; that is the singular
  case the whole reframe avoids.
- Stay PDK-blind / name-blind; no net-name heuristics for classification.
- Do not regress the existing sequential state-node path; Pillar 3 extends it to
  combinational internal nodes, it does not replace it.

-----

## 9. Suggested implementation order

1. Layer-B retention in stage0_parse + IR fields (small, unblocks everything).
1. Cap-graph builder (raw caps -> logical-net aggregation).
1. Charge-conservation resolve (scalar then linear) with the hand-calc tests.
1. Node classification (driven / settle / floating) via history replay.
1. Deck emission: drive-and-settle extension + `.ic` fallback + probes.
1. Coupling-bump pass (couples Pillar 3 back into Pillar 2 worst-case).
1. --verify cross-check and the series-stack degeneration test.

Steps 1-3 + the hand-calc test are the minimum to demonstrate the theory is
real and correct on a known cell. That is the trust artifact for the Wednesday
discussion; 4-7 are the depth behind it.
