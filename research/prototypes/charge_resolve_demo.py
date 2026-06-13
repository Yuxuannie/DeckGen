#!/usr/bin/env python3
"""
charge_resolve_demo.py -- UNVALIDATED research prototype for Pillar 3.

THIS IS NOT PRODUCTION CODE. It does not import engine/ and is not in the pytest
suite. It exists only to show that the charge-resolution math in
docs/research/findings.md actually runs and produces numbers. RUNNING AND
PRINTING NUMBERS PROVES NOTHING ABOUT PHYSICAL CORRECTNESS -- no SPICE
cross-check has been performed. Every number this prints is UNVERIFIED.

What it demonstrates:
  D1. A minimal LPE parser that RETAINS C lines (the half stage0_parse drops),
      and aggregates caps to logical nets via the same R-merge node_to_net map.
  D2. The two-step charge resolve from findings.md Direction 3:
        (a) contract ON-connected floating nodes into super-nodes using the
            grounded-cap charge-conservation sum (scalar formula);
        (b) assemble the coupling matrix over super-nodes + fixed nodes and
            solve C v = b with a pure-Python dense solver (no numpy).
  D3. The scalar formula and the matrix solve AGREE when there is no free-free
      coupling, and DISAGREE when there is -- the boundary the spec's 2.4
      conflates.
  D4. The singular (floating coupling-island) degeneracy is detected and
      returned as X, never as a fabricated voltage.

Pure stdlib. Python 3.8+.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}
_SUFFIX = re.compile(r"#.*$")


# ---------------------------------------------------------------------------
# D1. Minimal LPE parse: R-merge for connectivity, RETAIN C lines.
# (Standalone re-implementation; mirrors engine/stages/stage0_parse.py Layer A
#  but adds Layer B. NOT imported from engine.)
# ---------------------------------------------------------------------------
class _UF:
    def __init__(self) -> None:
        self.p: Dict[str, str] = {}

    def add(self, x: str) -> None:
        self.p.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        r = x
        while self.p[r] != r:
            r = self.p[r]
        while self.p[x] != r:
            self.p[x], x = r, self.p[x]
        return r

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            hi, lo = (ra, rb) if ra > rb else (rb, ra)
            self.p[hi] = lo


def parse_lpe(text: str):
    """Return (node_to_net, caps) where caps = [(net_a, net_b, farads, raw)]."""
    uf = _UF()
    raw_caps: List[Tuple[str, str, float, str]] = []
    ports: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        low = line.lower()
        if low.startswith(".subckt"):
            ports = line.split()[2:]
            for p in ports:
                uf.add(p)
            continue
        if line.startswith("."):
            continue
        toks = line.split()
        head = line[0].upper()
        if head == "X":               # device: register its terminal nodes
            for t in toks[1:5]:
                uf.add(t)
        elif head == "R":             # short -> connectivity
            uf.union(toks[1], toks[2])
        elif head == "C":             # RETAIN (Layer B) -- the whole point
            raw_caps.append((toks[1], toks[2], float(toks[3]), line))
    node_to_net: Dict[str, str] = {}
    groups: Dict[str, List[str]] = {}
    for node in uf.p:
        groups.setdefault(uf.find(node), []).append(node)
    for _, members in groups.items():
        sig = sorted({m for m in members if m in ports and m not in RAILS})
        rail = sorted({m for m in members if m in RAILS})
        if sig:
            name = sig[0]
        elif rail:
            name = rail[0]
        else:
            bases = [_SUFFIX.sub("", m) for m in members if "#" in m]
            name = max(set(bases), key=bases.count) if bases else "net_" + min(members)
        for m in members:
            node_to_net[m] = name
    caps = [(node_to_net.get(a, a), node_to_net.get(b, b), f, raw)
            for a, b, f, raw in raw_caps]
    return node_to_net, caps


def cap_network(caps):
    """Aggregate to logical nets. Returns (Cg, Cc) where
    Cg[net] = grounded farads, Cc[(n,m)] = coupling farads (n<m), intra-net dropped."""
    Cg: Dict[str, float] = {}
    Cc: Dict[Tuple[str, str], float] = {}
    for a, b, f, _ in caps:
        if a == b:                              # intra-net -> vanishes
            continue
        if a in RAILS and b in RAILS:
            continue
        if a in RAILS or b in RAILS:
            sig = b if a in RAILS else a
            Cg[sig] = Cg.get(sig, 0.0) + f
        else:
            key = tuple(sorted((a, b)))
            Cc[key] = Cc.get(key, 0.0) + f
    return Cg, Cc


# ---------------------------------------------------------------------------
# Pure-Python dense linear solve (Gaussian elimination, partial pivot).
# Returns None if singular (degenerate floating island).
# ---------------------------------------------------------------------------
def solve(A: List[List[float]], b: List[float], eps: float = 1e-30):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < eps:
            return None                         # singular -> X
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col:
                fac = M[r][col] / M[col][col]
                for c in range(col, n + 1):
                    M[r][c] -= fac * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


# ---------------------------------------------------------------------------
# D2. Two-step charge resolve (findings.md Direction 3).
# ---------------------------------------------------------------------------
def charge_resolve(free_groups: List[List[str]],
                   Cg: Dict[str, float],
                   Cc: Dict[Tuple[str, str], float],
                   entry_V: Dict[str, float],
                   fixed_V: Dict[str, float]) -> Dict[str, Optional[float]]:
    """
    free_groups : lists of nets that are ON-connected (each list merges to a super-node).
    Cg, Cc      : grounded / coupling caps (farads), logical-net keyed.
    entry_V     : voltage each free net carried INTO this phase (trapped charge / Cg).
    fixed_V     : voltages of fixed (driven/rail/held) nets coupling into the free set.

    Step (a): contract each free group via grounded-cap charge sum (scalar).
    Step (b): assemble coupling matrix over super-nodes, solve.
    """
    # ---- Step (a): scalar contraction of each ON-connected group ----
    supernode_of: Dict[str, int] = {}
    sn_Cg: List[float] = []
    sn_Q: List[float] = []      # trapped charge to ground
    sn_members: List[List[str]] = []
    for gi, grp in enumerate(free_groups):
        cg = sum(Cg.get(n, 0.0) for n in grp)
        q = sum(Cg.get(n, 0.0) * entry_V[n] for n in grp)
        for n in grp:
            supernode_of[n] = gi
        sn_Cg.append(cg)
        sn_Q.append(q)
        sn_members.append(grp)
    nsn = len(free_groups)

    # ---- Step (b): coupling matrix among super-nodes + RHS from fixed nodes ----
    A = [[0.0] * nsn for _ in range(nsn)]
    b = [sn_Q[i] for i in range(nsn)]
    for i in range(nsn):
        A[i][i] += sn_Cg[i]
    for (na, nb), c in Cc.items():
        ga = supernode_of.get(na)
        gb = supernode_of.get(nb)
        if ga is not None and gb is not None:
            if ga == gb:
                continue                       # intra-supernode coupling vanishes
            A[ga][gb] -= c
            A[gb][ga] -= c
            A[ga][ga] += c
            A[gb][gb] += c
        elif ga is not None and nb in fixed_V:
            A[ga][ga] += c                     # coupling to a fixed node
            b[ga] += c * fixed_V[nb]
        elif gb is not None and na in fixed_V:
            A[gb][gb] += c
            b[gb] += c * fixed_V[na]
        # else: coupling to an unknown node -> ignored here (flagged in real engine)

    sol = solve(A, b)
    out: Dict[str, Optional[float]] = {}
    for n, gi in supernode_of.items():
        out[n] = None if sol is None else sol[gi]
    return out


def scalar_share(nets, Cg, entry_V):
    """The spec 2.4 scalar formula, for cross-checking the matrix solve."""
    num = sum(Cg.get(n, 0.0) * entry_V[n] for n in nets)
    den = sum(Cg.get(n, 0.0) for n in nets)
    return num / den if den else None


# ---------------------------------------------------------------------------
# Demonstrations
# ---------------------------------------------------------------------------
def banner(s):
    print("\n" + "=" * 70 + "\n" + s + "\n" + "=" * 70)


def demo_scalar():
    banner("D2a. Scalar charge share (two grounded nodes merge through ON device)")
    Cg = {"dyn": 1.0e-15, "tap": 0.3e-15}      # farads
    entry = {"dyn": 0.45, "tap": 0.0}          # dyn precharged to VDD=0.45, tap at 0
    nets = ["dyn", "tap"]
    v_scalar = scalar_share(nets, Cg, entry)
    v_matrix = charge_resolve([["dyn", "tap"]], Cg, {}, entry, {})["dyn"]
    print(f"  Cg = {Cg}")
    print(f"  entry_V = {entry}  (VDD=0.45)")
    print(f"  scalar  V = (C_dyn*0.45 + C_tap*0)/(C_dyn+C_tap) = {v_scalar:.6f} V")
    print(f"  matrix  V = {v_matrix:.6f} V")
    print(f"  AGREE: {abs(v_scalar - v_matrix) < 1e-12}  "
          f"(no free-free coupling -> scalar is exact)")
    print("  [UNVERIFIED -- no SPICE cross-check]")


def demo_coupled():
    banner("D3. Free-free coupling: scalar formula is WRONG, matrix is needed")
    # Two SEPARATE floating nodes f1, f2 (NOT channel-connected), coupled to each
    # other AND each grounded. f1 precharged high, f2 low.
    Cg = {"f1": 1.0e-15, "f2": 1.0e-15}
    Cc = {("f1", "f2"): 0.8e-15}
    entry = {"f1": 0.45, "f2": 0.0}
    # Naive scalar (treating them as one merged group) -- WRONG, they are not merged:
    v_naive = scalar_share(["f1", "f2"], Cg, entry)
    # Correct: two super-nodes (each its own group), coupling matrix:
    res = charge_resolve([["f1"], ["f2"]], Cg, Cc, entry, {})
    print(f"  Cg = {Cg}")
    print(f"  Cc(f1,f2) = {Cc[('f1','f2')]}")
    print(f"  entry_V = {entry}")
    print(f"  NAIVE scalar-merge V = {v_naive:.6f} V  (WRONG: f1,f2 are not shorted)")
    print(f"  MATRIX  f1 = {res['f1']:.6f} V , f2 = {res['f2']:.6f} V")
    print(f"  -> f1 holds near its trapped value, f2 is bumped UP by coupling;")
    print(f"     they do NOT equalize. Scalar averaging would erase this.")
    print("  [UNVERIFIED -- no SPICE cross-check]")


def demo_singular():
    banner("D4. Degenerate floating island (no Cg, coupling-only) -> X, not a number")
    # f1, f2 couple ONLY to each other, neither has a grounded cap or a fixed
    # coupling. Absolute level is undetermined.
    Cg: Dict[str, float] = {}
    Cc = {("f1", "f2"): 0.8e-15}
    entry = {"f1": 0.45, "f2": 0.0}
    res = charge_resolve([["f1"], ["f2"]], Cg, Cc, entry, {})
    print(f"  Cg = {{}} (no node referenced to a rail)")
    print(f"  Cc(f1,f2) = {Cc[('f1','f2')]}")
    print(f"  matrix solve -> {res}")
    print(f"  Singular detected: {res['f1'] is None}  -> emit X / needs-evidence")
    print("  [UNVERIFIED -- no SPICE cross-check]")


def demo_fixed_coupling():
    banner("D2b. Coupling to a FIXED swinging aggressor (the 2.5 coupling bump)")
    # One floating node f, grounded cap, coupled to aggressor 'agg' held at dV.
    Cg = {"f": 1.0e-15}
    Cc = {("agg", "f"): 0.5e-15}
    entry = {"f": 0.0}
    fixed = {"agg": 0.45}     # aggressor swung to 0.45 after f was released at 0
    res = charge_resolve([["f"]], Cg, Cc, entry, fixed)
    alpha = Cc[("agg", "f")] / (Cg["f"] + Cc[("agg", "f")])
    print(f"  Cg(f)={Cg['f']}, Cc(agg,f)={Cc[('agg','f')]}, agg swing dV=0.45")
    print(f"  divider alpha = Cc/(Cg+Cc) = {alpha:.4f}")
    print(f"  predicted bump dV_f = alpha*dV = {alpha*0.45:.6f} V")
    print(f"  matrix V_f = {res['f']:.6f} V")
    print(f"  AGREE: {abs(res['f'] - alpha*0.45) < 1e-9}")
    print("  [UNVERIFIED -- no SPICE cross-check]")


def demo_parse():
    banner("D1. LPE parse retains C and aggregates to logical nets")
    lpe = """\
.subckt TINY A Q VDD VSS
XINV0 XINV0#d XINV0#g XINV0#s VDD pch_svt_mac
XINV1 XINV1#d XINV1#g XINV1#s VSS nch_svt_mac
R1 A XINV0#g 1.0
R2 XINV0#g XINV1#g 1.0
R3 Q XINV0#d 1.0
R4 XINV0#d XINV1#d 1.0
CA1 XINV0#g VSS 1.2e-18
CC1 XINV0#g XINV0#d 3.4e-19
.ends TINY
"""
    n2net, caps = parse_lpe(lpe)
    Cg, Cc = cap_network(caps)
    print("  caps mapped to logical nets:")
    for a, b, f, _ in caps:
        print(f"    {a:<6} {b:<6} {f}")
    print(f"  grounded Cg = {Cg}")
    print(f"  coupling Cc = {Cc}")
    print("  (CA1 on gate-net A -> grounded; CC1 A<->Q -> coupling)")


if __name__ == "__main__":
    print("UNVALIDATED RESEARCH PROTOTYPE -- numbers prove nothing physical.")
    demo_parse()
    demo_scalar()
    demo_fixed_coupling()
    demo_coupled()
    demo_singular()
    print("\nAll demos ran. Every printed value is UNVERIFIED (no SPICE).")
