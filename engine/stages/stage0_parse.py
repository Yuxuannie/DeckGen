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

from engine.types import Device, DeviceGraph

RAILS = {"VDD", "VSS", "VPP", "VBB"}
_TERM_SUFFIX = re.compile(r"#.*$")


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


def parse(source: str, cell: str) -> DeviceGraph:
    ports: List[str] = []
    raw_devices: List[tuple] = []          # (name, kind, model, [d,g,s,b])
    device_names: set = set()
    uf = _UF()

    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        low = line.lower()
        if low.startswith(".subckt"):
            ports = line.split()[2:]
            for p in ports:
                uf.add(p)
            continue
        if low.startswith(".ends"):
            continue
        head = line[0].upper()
        toks = line.split()
        if head == "X":
            # X<name> d g s b <model> <params...>
            name, terms, model = toks[0], toks[1:5], toks[5]
            kind = _kind(model)
            raw_devices.append((name, kind, model, terms))
            device_names.add(name)
            for t in terms:
                uf.add(t)
        elif head == "R":
            # R<name> n1 n2 value [$active]   -> short it (intra-net interconnect)
            uf.union(toks[1], toks[2])
        # C / anything else: ignored for connectivity

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

    nets = sorted(set(node_to_net.values()))
    n_r = sum(1 for ln in source.splitlines() if ln.strip()[:1] in ("R", "r"))
    checks.insert(0, f"R-merge: {len(uf.parent)} raw nodes -> {len(nets)} logical "
                     f"nets via {n_r} resistors; {len(devices)} transistors")

    return DeviceGraph(
        cell=cell, ports=ports, devices=devices, nets=nets,
        node_to_net=node_to_net, checks=checks, source=source,
    )
