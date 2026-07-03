"""
Stage 0 -- Parse LPE netlist + recover logical nets (spec SS5; SEGMENT 2).
  in : netlist text (.subckt, LPE / parasitic-extracted)
  out: DeviceGraph  (transistors with LOGICAL-net terminals + provenance)

Method (technique survey, Layer A -- de-parasitic):
  Real cells ship only as LPE: device terminals are private extracted nodes
  (`XMSA2#d`) and connectivity is carried entirely by parasitic R; C is
  to-ground/coupling and irrelevant to DC connectivity. So:
    1. parse macro-subckt transistors `X<name> d g s b nch/pch_svt_mac`,
       parasitic R (2 nodes), and C (ignored for connectivity);
    2. SHORT every R and union-find contract -> node clusters = logical nets;
    3. name each cluster by its port, else the common `netbase` of `netbase#k`
       nodes (`X<Dev>#pin` nodes are device pins -- they do not name a net).
  Self-check: a cluster with two distinct signal ports (or mixed rails) means an
  R bridged two nets -- recorded as a FAIL-grade derivation for the verdict.

This is intentionally PDK-blind and name-blind: nothing keys off `ml_*`/`sl_*`.
"""
from __future__ import annotations

import re
from typing import Dict, List

from engine.types import Cap, Device, DeviceGraph

RAILS = {"VDD", "VSS", "VPP", "VBB", "0"}   # "0" = SPICE global ground
_TERM_SUFFIX = re.compile(r"#.*$")

# SPICE engineering suffixes for capacitor values (Layer B). "meg" before "m"/"g".
_SI_SUFFIX = {"meg": 1e6, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
              "m": 1e-3, "k": 1e3, "g": 1e9, "t": 1e12}


def _cap_value(tok: str):
    """Parse a capacitor value token tolerantly; None if unparseable (recorded,
    never silently dropped). Handles plain floats, `C=...`, and SPICE suffixes."""
    t = tok.split("=")[-1].strip().lower()
    try:
        return float(t)
    except ValueError:
        pass
    for suf in ("meg", "f", "p", "n", "u", "m", "k", "g", "t"):
        if t.endswith(suf):
            try:
                return float(t[:-len(suf)]) * _SI_SUFFIX[suf]
            except ValueError:
                return None
    return None


class _UF:
    def __init__(self) -> None:
        self.parent: Dict[str, str] = {}

    def add(self, x: str) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:    # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # deterministic: smaller name becomes root
            hi, lo = (ra, rb) if ra > rb else (rb, ra)
            self.parent[hi] = lo


def _kind(model: str) -> str:
    m = model.lower()
    if "pch" in m or "pmos" in m:
        return "pmos"
    if "nch" in m or "nmos" in m:
        return "nmos"
    return "placeholder"


def _base(node: str) -> str:
    return _TERM_SUFFIX.sub("", node)


def _is_model_tok(t: str) -> bool:
    tl = t.lower()
    return "mac" in tl or tl.startswith(("nch", "pch", "nmos", "pmos"))


def _logical_lines(source: str) -> List[str]:
    """Join HSPICE `+` continuation lines into single logical lines."""
    out: List[str] = []
    for raw in source.splitlines():
        st = raw.strip()
        if not st:
            continue
        if st.startswith("+"):
            if out:
                out[-1] = out[-1] + " " + st[1:].strip()
            continue
        out.append(st)
    return out


def _split_device(toks: List[str]):
    """Return (terminals, model) for an X-device line, or None if unparseable.

    Finds the model token (first non-param token that looks like a model);
    terminals are the node tokens between the name and the model. Robust to
    3- or 4-terminal macro devices and to long param columns.
    """
    midx = None
    for i in range(1, len(toks)):
        if "=" in toks[i]:
            break                       # reached params; model is before here
        if _is_model_tok(toks[i]):
            midx = i
            break
    if midx is None:                    # fallback: last non-param token = model
        j = 1
        while j < len(toks) and "=" not in toks[j]:
            j += 1
        midx = j - 1
    if midx <= 0:
        return None
    terms = toks[1:midx]
    if len(terms) < 3:                  # need at least d g s to be a transistor
        return None
    return terms, toks[midx]


def parse(source: str, cell: str) -> DeviceGraph:
    ports: List[str] = []
    raw_devices: List[tuple] = []          # (name, kind, model, [d,g,s,b])
    raw_caps: List[tuple] = []             # Layer B: (rawnode_a, rawnode_b, farads, line)
    cap_skips: List[str] = []              # unparseable C lines (recorded, never dropped silently)
    device_names: set = set()
    uf = _UF()

    for line in _logical_lines(source):
        if line.startswith("*"):
            continue
        low = line.lower()
        if low.startswith(".subckt"):
            ports = line.split()[2:]
            for p in ports:
                uf.add(p)
            continue
        if low.startswith("."):            # .ends / .param / other directives
            continue
        head = line[0].upper()
        toks = line.split()
        if head == "X":
            parsed = _split_device(toks)
            if parsed is None:
                continue                   # not a transistor (e.g. subckt call)
            terms, model = parsed
            d, g, s = terms[0], terms[1], terms[2]
            b = terms[3] if len(terms) > 3 else terms[2]
            terms4 = [d, g, s, b]
            raw_devices.append((toks[0], _kind(model), model, terms4))
            device_names.add(toks[0])
            for t in terms4:
                uf.add(t)
        elif head == "R":
            # R<name> n1 n2 value [$active]   -> short it (intra-net interconnect)
            uf.union(toks[1], toks[2])
        elif head == "C":
            # C<name> n1 n2 value   -> Layer B: retain (mapped to logical nets
            # AFTER clustering below). Layer A connectivity is untouched.
            if len(toks) < 4:
                cap_skips.append(f"C-skip: too few tokens -- {line}")
                continue
            val = _cap_value(toks[3])
            if val is None:
                cap_skips.append(f"C-skip: unparseable value -- {line}")
                continue
            raw_caps.append((toks[1], toks[2], val, line))
        # anything else: ignored for connectivity

    # --- name each cluster (logical net) ---
    groups: Dict[str, List[str]] = {}
    for node in uf.parent:
        groups.setdefault(uf.find(node), []).append(node)

    node_to_net: Dict[str, str] = {}
    checks: List[str] = []
    for root, members in groups.items():
        sig_ports = sorted({m for m in members if m in ports and m not in RAILS})
        rail_ports = sorted({m for m in members if m in RAILS})
        if len(sig_ports) > 1:
            checks.append(f"BRIDGE(FAIL): signal ports {sig_ports} shorted by R "
                          f"into one net -- topology error")
        if len(rail_ports) > 1:
            checks.append(f"BRIDGE(FAIL): rails {rail_ports} shorted by R")

        if sig_ports:
            name = sig_ports[0]
        elif rail_ports:
            name = rail_ports[0]
        else:
            net_bases = [_base(m) for m in members
                         if "#" in m and _base(m) not in device_names]
            if net_bases:
                name = max(set(net_bases), key=net_bases.count)
            else:
                name = "net_" + min(members)   # stable anonymous id
        for m in members:
            node_to_net[m] = name

    # --- map device terminals to logical nets ---
    devices: List[Device] = []
    for name, kind, model, terms in raw_devices:
        d, g, s, b = (node_to_net.get(t, t) for t in terms)
        devices.append(Device(name=name, kind=kind, model=model,
                              terminals={"d": d, "g": g, "s": s, "b": b}))

    # --- Layer B: map retained caps onto logical nets (connectivity untouched) ---
    caps: List[Cap] = [
        Cap(a=node_to_net.get(a, a), b=node_to_net.get(b, b), farads=val, raw=line)
        for a, b, val, line in raw_caps
    ]
    grounded = sum(1 for c in caps if c.a in RAILS or c.b in RAILS)
    intra = sum(1 for c in caps if c.a == c.b)
    coupling = len(caps) - grounded - intra

    nets = sorted(set(node_to_net.values()))
    n_r = sum(1 for ln in source.splitlines() if ln.strip()[:1] in ("R", "r"))
    checks.insert(0, f"R-merge: {len(uf.parent)} raw nodes -> {len(nets)} logical "
                     f"nets via {n_r} resistors; {len(devices)} transistors")
    checks.append(f"Layer B: {len(caps)} parasitic C retained "
                  f"({grounded} grounded, {coupling} coupling, {intra} intra-net); "
                  f"{len(cap_skips)} unparseable")
    checks.extend(cap_skips)

    return DeviceGraph(
        cell=cell, ports=ports, devices=devices, nets=nets,
        node_to_net=node_to_net, caps=caps, checks=checks, source=source,
    )
