"""
engine/sim.py -- run HSPICE and evaluate P2 (initial state correct), differentially.

The first real run showed why a static polarity prediction is fragile: a tristate
latch's transparent value depends on inversion parity the stateless evaluator can
miscount. So P2 is evaluated against SILICON, relationally:

  Run the P2 deck twice -- D driven to the captured value, and to its inverse,
  with the SAME pre-cycle (same prior loaded). At the settle point:
    - DEFINITE : every storage node is a clean 0/1 (settled, not X);
    - MASTER tracks D : master node(s) differ between the two runs
                        (the dynamic analog of P1's d(capture)/d(D)=1);
    - SLAVE holds prior: slave node(s) are unchanged between the two runs
                        (already latched; independent of current D);
    - COMPLEMENTARY : each cross-coupled pair holds opposite values.
  P2 PASS iff all hold. This is robust to inversion parity and also fixes the
  slave polarity that the derive-only stage left tentative.

The engine runs on-server, so it invokes hspice itself. P1 needs no simulator.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from engine import golden_env as G
from engine.mt0 import parse_mt0
from engine.p2_deck import build as build_p2
from engine.types import Arc, CCCResult, InitializationResult, SensitizationResult

MARGIN = 0.35     # fraction of VDD; outside [m, 1-m]*VDD = a definite bit, else X


@dataclass
class P2NodeResult:
    node: str
    role: str
    v_cap: Optional[float]      # voltage with D = captured value
    v_inv: Optional[float]      # voltage with D = inverted
    bit_cap: Optional[int]
    bit_inv: Optional[int]
    behavior: str               # "tracks-D" (master) | "holds-prior" (slave)
    ok: bool


@dataclass
class P2Result:
    ran: bool
    passed: bool
    nodes: List[P2NodeResult] = field(default_factory=list)
    complementary: bool = True
    note: str = ""


def _bit(v: Optional[float], vdd: float) -> Optional[int]:
    if v is None:
        return None
    if v >= vdd * (1 - MARGIN):
        return 1
    if v <= vdd * MARGIN:
        return 0
    return None                 # mid-rail -> X (not definite)


def _run_once(arc, sens, init, probe_nodes, final_d, workdir, tag,
              hspice_cmd, mt0_path):
    deck, meas_map = build_p2(arc, sens, init, probe_nodes, final_d=final_d)
    dp = os.path.join(workdir, f"p2_{tag}.sp")
    with open(dp, "w", encoding="ascii") as fh:
        fh.write(deck)
    if mt0_path is None:
        mp = os.path.join(workdir, f"p2_{tag}.mt0")
        try:
            subprocess.run([hspice_cmd, f"p2_{tag}.sp"], cwd=workdir,
                           capture_output=True, text=True, timeout=1800, check=False)
        except FileNotFoundError:
            return None, meas_map, f"hspice not found ({hspice_cmd!r})"
        except subprocess.TimeoutExpired:
            return None, meas_map, "hspice timed out"
    else:
        mp = mt0_path
    if not os.path.isfile(mp):
        return None, meas_map, f"no .mt0 produced ({mp})"
    with open(mp, "r", encoding="ascii", errors="replace") as fh:
        return parse_mt0(fh.read()), meas_map, ""


def run_wave(arc: Arc, sens: SensitizationResult, init: InitializationResult,
             workdir: str, out_svg: str, hspice_cmd: str = "hspice",
             tr0_path: Optional[str] = None) -> str:
    """Run the P2 wave deck and render its transient to an SVG (open with eog).
    tr0_path lets you render an existing CSDF .tr0 without re-running hspice."""
    from engine.wave import parse_csdf, render_svg
    os.makedirs(workdir, exist_ok=True)
    probe_nodes = list(init.probes)
    deck, info = build_p2(arc, sens, init, probe_nodes, wave=True)
    with open(os.path.join(workdir, "p2_wave.sp"), "w", encoding="ascii") as fh:
        fh.write(deck)
    if tr0_path is None:
        tr0_path = os.path.join(workdir, "p2_wave.tr0")
        try:
            subprocess.run([hspice_cmd, "p2_wave.sp"], cwd=workdir,
                           capture_output=True, text=True, timeout=1800, check=False)
        except FileNotFoundError:
            return f"hspice not found ({hspice_cmd!r})"
        except subprocess.TimeoutExpired:
            return "hspice timed out"
    if not os.path.isfile(tr0_path):
        return f"no .tr0 produced ({tr0_path}); check the wave deck ran"
    with open(tr0_path, "r", encoding="ascii", errors="replace") as fh:
        times, traces = parse_csdf(fh.read())
    marks = [(info["t_settle"], "settle"), (info["t_cap_edge"], "cap-edge")]
    svg = render_svg(times, traces, float(G.VDD_VALUE), marks,
                     title=f"{arc.cell} {arc.label()} P2 transient")
    with open(out_svg, "w", encoding="ascii") as fh:
        fh.write(svg)
    return f"wrote {out_svg} ({len(times)} points); open: eog {out_svg}"


def run_p2(arc: Arc, ccc: CCCResult, sens: SensitizationResult,
           init: InitializationResult, workdir: str,
           hspice_cmd: str = "hspice",
           mt0_path: Optional[str] = None,
           mt0_inv_path: Optional[str] = None) -> P2Result:
    """Differential P2. mt0_path/mt0_inv_path let you evaluate existing .mt0s
    (offline debug) for the captured-D and inverted-D runs respectively."""
    os.makedirs(workdir, exist_ok=True)
    cap = 1 if arc.constr_dir == "fall" else 0
    probe_nodes = list(init.probes)

    meas_cap, mmap, err = _run_once(arc, sens, init, probe_nodes, cap, workdir,
                                    "cap", hspice_cmd, mt0_path)
    if meas_cap is None:
        return P2Result(False, False, note=err)
    meas_inv, _, err = _run_once(arc, sens, init, probe_nodes, 1 - cap, workdir,
                                 "inv", hspice_cmd, mt0_inv_path)
    if meas_inv is None:
        return P2Result(False, False, note=err)

    vdd = float(G.VDD_VALUE)
    role_of = {sn.net: sn.role for sn in ccc.state_nodes}
    nodes: List[P2NodeResult] = []
    all_ok = True
    for node in probe_nodes:
        net = node.replace("x1.", "").split("#")[0]
        role = role_of.get(net, "?")
        vc, vi = meas_cap.get(mmap[node]), meas_inv.get(mmap[node])
        bc, bi = _bit(vc, vdd), _bit(vi, vdd)
        definite = bc is not None and bi is not None
        if role == "master":
            behavior, ok = "tracks-D", definite and bc != bi
        else:
            behavior, ok = "holds-prior", definite and bc == bi
        all_ok = all_ok and ok
        nodes.append(P2NodeResult(net, role, vc, vi, bc, bi, behavior, ok))

    # complementary: each role's pair holds opposite bits in the captured run
    comp = True
    for role in ("master", "slave"):
        bits = [n.bit_cap for n in nodes if n.role == role and n.bit_cap is not None]
        if len(bits) >= 2 and len(set(bits)) != 2:
            comp = False
    return P2Result(True, all_ok and comp, nodes, comp, "")
