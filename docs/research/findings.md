# Charge / Electrostatic -- Working Derivations (findings.md)

> Referenced by `ARCHITECTURE.md` section 8 and by `engine/charge.py` (which cites
> "docs/research/findings.md 3.1" and "Direction 3"). This file holds the charge
> derivations the code relies on, plus the Demo-3 storage-node disturbance model.
> Research notes -- assumptions are stated; conjecture is marked.

## 3. Cap-graph reduction (the substrate `engine/charge.py` implements)

### 3.1 Why intra-net caps vanish

A retained parasitic cap whose two endpoints map to the **same logical net** (after
Stage-0 R-merge) stores charge internal to one conductor. It cannot change that
conductor's rail-referenced potential, so it is dropped. Rail-to-rail caps are not
signal caps and are dropped. Every other cap is either **grounded** (one rail
endpoint -> `Cg[net]`) or **coupling** (two distinct signal nets -> `Cc[(lo,hi)]`).
At AC, every rail is ground, so all rail endpoints fold into `Cg` regardless of
which rail. (This is exactly `cap_network()`.)

### Direction 3 -- charge-conservation resolve

For a set of nets that are *floating* (no DC path) at the analyzed instant, charge
is conserved on each isolated super-node. `resolve()` contracts ON-connected nets
into super-nodes, assembles the coupling cap matrix, and solves
`C . V = Q_trapped + (coupling from fixed nets)`. Three SPICE-free invariants guard
it: residual `||Av-b|| ~ 0`, convex-hull bound (a cap M-matrix solution is a
weighted average of boundary potentials -- any V outside `[min,max]` is a bug), and
a scalar cross-check for uncoupled super-nodes. A singular system (isolated coupling
island with no rail reference) returns **X**, never a fabricated number.

## 4. Demo-3 storage-node disturbance model (sequential)

> Full treatment + worked example in `docs/research/sequential_fingerprint.md`
> (Layer 2). Summary of the load-bearing result here for the charge file.

A Layer-1-identified storage node `s`, floating while its keeper is momentarily
weak, holding trapped charge `Cg_s . V_s0`, disturbed by an aggressor net swinging
`dV_agg` through `Cc(s,agg)`:

    dV_s = Cc(s,agg) / (Cg_s + sum Cc_s) . dV_agg
         (Eq. 2.1, DERIVED -- capacitive divider in the engine's own Cg/Cc)

**Worked (SDFX, real fixture caps):** `Cg[ml_a]=1.2aF`, `Cc(ml_a,sl_a)=0.34aF`,
`dV_agg = VDD = 0.45 V`  =>  `dV_ml_a = 0.34/(1.2+0.34) . 0.45 = 0.099 V ~ 22% VDD`.
`resolve_checked` independently gives the same 0.0994 V (invariants PASS).

**Use:** a **relative susceptibility / ordering** signal -- which storage nodes and
arcs are most coupling-sensitive -- **not** an absolute setup/hold time (that is the
FMC deck's job; ARCHITECTURE.md section 8 boundary). Conjectural extensions (flip
threshold ~ VDD/2; RC-ordered vulnerability window) are marked as conjecture in
`sequential_fingerprint.md` section 2.5.
