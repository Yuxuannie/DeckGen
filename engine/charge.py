"""
engine/charge.py -- Layer-B cap-graph aggregation (Pillar 3 step 2; spec SS2.2/SS3).

Reduces the retained parasitic C network (DeviceGraph.caps, already logical-net
keyed by stage0) into the two objects the charge resolve (step 3) consumes:

  Cg[net]        -- grounded capacitance (farads): node-to-rail / AC ground.
                    Summed across all rail-terminated caps regardless of which
                    rail (VDD/VSS/...) -- at AC every rail is ground (spec SS2.2).
  Cc[(lo, hi)]   -- coupling capacitance (farads) between two signal nets, keyed
                    by the sorted net pair so (a,b) and (b,a) accumulate together.

Caps whose endpoints land on the SAME logical net (intra-net) vanish -- their
charge is internal to one conductor and does not affect its rail-referenced
potential (see docs/research/findings.md 3.1). Rail-to-rail caps are dropped
(not a signal-node cap).

Pure function, no PDK, stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engine.types import Derivation, DeviceGraph

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}   # "0" = SPICE global ground
STAGE = "S3.charge"


def cap_network(graph: DeviceGraph) -> Tuple[Dict[str, float], Dict[Tuple[str, str], float]]:
    """Aggregate graph.caps -> (Cg grounded farads, Cc coupling farads)."""
    Cg: Dict[str, float] = {}
    Cc: Dict[Tuple[str, str], float] = {}
    for c in graph.caps:
        a, b = c.a, c.b
        if a == b:
            continue                                   # intra-net -> vanishes
        a_rail, b_rail = a in RAILS, b in RAILS
        if a_rail and b_rail:
            continue                                   # rail-to-rail -> not a signal cap
        if a_rail or b_rail:
            sig = b if a_rail else a
            Cg[sig] = Cg.get(sig, 0.0) + c.farads
        else:
            key = (a, b) if a < b else (b, a)
            Cc[key] = Cc.get(key, 0.0) + c.farads
    return Cg, Cc


# ===========================================================================
# Pillar 3 step 3 -- charge-conservation resolve (two-step: contract + matrix).
# Theory + derivations: docs/research/findings.md Direction 3.
# ===========================================================================
@dataclass
class ChargeResolve:
    """Result of a floating-node charge resolve, self-describing for review.

    voltages    : net -> resolved V (None means X / undetermined, e.g. a
                  singular isolated-coupling island; never a fabricated number).
    derivations : net -> the charge math that produced it (provenance).
    checks      : SPICE-free invariant results (hull bound, scalar cross-check,
                  residual). Each line ends in PASS or FAIL.
    singular    : True if any node was left undetermined.
    ok          : True iff no invariant FAILed and nothing singular.
    """
    voltages: Dict[str, Optional[float]]
    derivations: Dict[str, Derivation] = field(default_factory=dict)
    checks: List[str] = field(default_factory=list)
    singular: bool = False

    @property
    def ok(self) -> bool:
        return not self.singular and not any(c.endswith("FAIL") for c in self.checks)


def _solve(A: List[List[float]], b: List[float], eps: float = 1e-30):
    """Dense Gaussian elimination, partial pivot. None if singular. Stdlib only
    (numpy is not a repo dependency; standard cells give tiny dense systems)."""
    n = len(A)
    if n == 0:
        return []
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < eps:
            return None                          # singular -> caller emits X
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col:
                fac = M[r][col] / M[col][col]
                for c in range(col, n + 1):
                    M[r][c] -= fac * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def _assemble(free_groups, Cg, Cc, entry_V, fixed_V):
    """Step A (contract ON-connected groups via grounded-cap charge sum) + step B
    (assemble coupling matrix over super-nodes). Deterministic ordering."""
    groups = sorted((sorted(g) for g in free_groups if g), key=lambda g: g[0])
    supernode_of: Dict[str, int] = {}
    sn_Cg: List[float] = []
    sn_Q: List[float] = []
    for gi, grp in enumerate(groups):
        for n in grp:
            supernode_of[n] = gi
        sn_Cg.append(sum(Cg.get(n, 0.0) for n in grp))
        sn_Q.append(sum(Cg.get(n, 0.0) * entry_V[n] for n in grp))
    nsn = len(groups)
    A = [[0.0] * nsn for _ in range(nsn)]
    b = list(sn_Q)
    for i in range(nsn):
        A[i][i] += sn_Cg[i]
    coupling_touch = [False] * nsn               # does this super-node have any coupling?
    for (na, nb), c in sorted(Cc.items()):
        ga, gb = supernode_of.get(na), supernode_of.get(nb)
        if ga is not None and gb is not None:
            if ga == gb:
                continue                         # intra-supernode coupling vanishes
            A[ga][gb] -= c
            A[gb][ga] -= c
            A[ga][ga] += c
            A[gb][gb] += c
            coupling_touch[ga] = coupling_touch[gb] = True
        elif ga is not None and nb in fixed_V:
            A[ga][ga] += c
            b[ga] += c * fixed_V[nb]
            coupling_touch[ga] = True
        elif gb is not None and na in fixed_V:
            A[gb][gb] += c
            b[gb] += c * fixed_V[na]
            coupling_touch[gb] = True
    return groups, supernode_of, sn_Cg, sn_Q, A, b, coupling_touch


def resolve(free_groups, Cg, Cc, entry_V, fixed_V) -> Dict[str, Optional[float]]:
    """Numeric two-step charge resolve. net -> V (None = undetermined/X).

    free_groups : lists of nets that are ON-connected at the resolved instant
                  (each list merges into one super-node).
    Cg, Cc      : grounded / coupling caps from cap_network().
    entry_V     : voltage each free net carried INTO this phase (trapped charge).
    fixed_V     : voltages of fixed (driven/rail/held) nets coupling into the set.
    """
    groups, supernode_of, _, _, A, b, _ = _assemble(
        free_groups, Cg, Cc, entry_V, fixed_V)
    sol = _solve(A, b)
    return {n: (None if sol is None else sol[gi]) for n, gi in supernode_of.items()}


def _scalar_share(grp, Cg, entry_V):
    num = sum(Cg.get(n, 0.0) * entry_V[n] for n in grp)
    den = sum(Cg.get(n, 0.0) for n in grp)
    return (num / den) if den else None


def resolve_checked(free_groups, Cg, Cc, entry_V, fixed_V) -> ChargeResolve:
    """resolve() plus self-describing derivations and SPICE-free invariant checks.
    This is the reviewer-facing entry point (feeds the viz + the eventual P3)."""
    groups, supernode_of, sn_Cg, sn_Q, A, b, coupling_touch = _assemble(
        free_groups, Cg, Cc, entry_V, fixed_V)
    sol = _solve(A, b)
    singular = sol is None
    voltages = {n: (None if singular else sol[gi]) for n, gi in supernode_of.items()}

    derivations: Dict[str, Derivation] = {}
    for gi, grp in enumerate(groups):
        if singular:
            reason = ("undetermined: isolated coupling island with no rail "
                      "reference (singular cap matrix) -> X, not a fabricated value")
            for n in grp:
                derivations[n] = Derivation(None, reason, STAGE)
            continue
        v = sol[gi]
        merged = "" if len(grp) == 1 else f" [merged group {grp}]"
        if not coupling_touch[gi]:
            terms = " + ".join(f"{Cg.get(n, 0.0):.3g}*{entry_V[n]:.4g}" for n in grp)
            den = sum(Cg.get(n, 0.0) for n in grp)
            reason = (f"charge-share scalar: V = ({terms}) / {den:.3g} "
                      f"= {v:.6g}{merged}")
        else:
            reason = (f"coupled charge balance (matrix solve over "
                      f"{len(groups)} super-node(s)); V = {v:.6g}{merged}")
        for n in grp:
            derivations[n] = Derivation(v, reason, STAGE)

    checks = _invariants(groups, sn_Cg, sn_Q, A, b, sol, Cg, entry_V, fixed_V,
                         coupling_touch, singular)
    return ChargeResolve(voltages=voltages, derivations=derivations,
                         checks=checks, singular=singular)


def _invariants(groups, sn_Cg, sn_Q, A, b, sol, Cg, entry_V, fixed_V,
                coupling_touch, singular) -> List[str]:
    """Three SPICE-free correctness invariants (findings.md): residual,
    convex-hull bound, scalar cross-check. Each line ends PASS or FAIL."""
    out: List[str] = []
    if singular:
        out.append("singular: isolated coupling island -> X emitted (by design) -- PASS")
        return out

    # 1. Residual: the solver actually solved its own system, ||A v - b|| ~ 0.
    n = len(sol)
    maxres = 0.0
    for i in range(n):
        r = sum(A[i][j] * sol[j] for j in range(n)) - b[i]
        maxres = max(maxres, abs(r))
    scale = max((abs(x) for x in b), default=0.0) + 1e-300
    out.append(f"residual ||Av-b||={maxres:.2e} (scale {scale:.2e}) -- "
               + ("PASS" if maxres <= 1e-6 * scale else "FAIL"))

    # 2. Convex-hull bound: a cap M-matrix solution is a weighted average of the
    # boundary potentials; any resolved V outside [lo, hi] is a bug.
    bounds = list(entry_V.values()) + list(fixed_V.values())
    if bounds:
        lo, hi = min(bounds), max(bounds)
        eps = 1e-9 * (hi - lo + 1.0)
        worst = max(((v, max(lo - v, v - hi)) for v in sol), key=lambda t: t[1],
                    default=(None, -1.0))
        ok = all(lo - eps <= v <= hi + eps for v in sol)
        out.append(f"hull bound: all V in [{lo:.6g}, {hi:.6g}] "
                   f"(worst margin {worst[1]:.2e}) -- " + ("PASS" if ok else "FAIL"))

    # 3. Scalar cross-check: an uncoupled super-node must equal the closed form.
    mism = []
    for gi, grp in enumerate(groups):
        if coupling_touch[gi]:
            continue
        s = _scalar_share(grp, Cg, entry_V)
        if s is not None and abs(s - sol[gi]) > 1e-9 * (abs(s) + 1e-30):
            mism.append(f"{grp}: scalar {s:.6g} != matrix {sol[gi]:.6g}")
    if mism:
        out.append("scalar cross-check: " + "; ".join(mism) + " -- FAIL")
    else:
        out.append("scalar cross-check: uncoupled groups match closed form -- PASS")
    return out
