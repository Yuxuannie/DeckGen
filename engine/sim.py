"""
engine/sim.py -- run HSPICE on a deck and evaluate P2 (initial state correct).

The engine runs ON the server (via --netlist), so it can invoke hspice itself,
read the .mt0, and turn measured node voltages into a P2 PASS/FAIL. P1 needs no
simulator; this module is only for P2 (and later P3).

Flow:
  build P2 deck -> write deck.sp -> `hspice deck.sp` -> parse deck.mt0
  -> threshold each node at VDD/2 -> compare to derived required state.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from engine import golden_env as G
from engine.mt0 import parse_mt0
from engine.p2_deck import build as build_p2
from engine.types import Arc, CCCResult, InitializationResult, SensitizationResult


@dataclass
class P2NodeResult:
    node: str
    role: str
    measured_v: Optional[float]
    measured_bit: Optional[int]
    expected_bit: Optional[int]
    ok: bool


@dataclass
class P2Result:
    ran: bool
    passed: bool
    nodes: List[P2NodeResult]
    note: str = ""


def _bit(v: Optional[float], vdd: float) -> Optional[int]:
    if v is None:
        return None
    return 1 if v >= vdd / 2.0 else 0


def run_p2(arc: Arc, ccc: CCCResult, sens: SensitizationResult,
           init: InitializationResult, workdir: str,
           hspice_cmd: str = "hspice", mt0_path: Optional[str] = None) -> P2Result:
    """Build the P2 deck, run hspice (unless mt0_path is supplied), evaluate P2.

    mt0_path lets you skip the run and evaluate an existing .mt0 (debug / offline).
    """
    os.makedirs(workdir, exist_ok=True)
    deck_path = os.path.join(workdir, "p2_deck.sp")
    probe_nodes = list(init.probes)
    deck_text, meas_map = build_p2(arc, sens, init, probe_nodes)
    with open(deck_path, "w", encoding="ascii") as fh:
        fh.write(deck_text)

    if mt0_path is None:
        mt0_path = os.path.join(workdir, "p2_deck.mt0")
        try:
            subprocess.run([hspice_cmd, "p2_deck.sp"], cwd=workdir,
                           capture_output=True, text=True, timeout=1800, check=False)
        except FileNotFoundError:
            return P2Result(False, False, [], f"hspice not found ({hspice_cmd!r})")
        except subprocess.TimeoutExpired:
            return P2Result(False, False, [], "hspice timed out")
    if not os.path.isfile(mt0_path):
        return P2Result(False, False, [], f"no .mt0 produced ({mt0_path})")

    with open(mt0_path, "r", encoding="ascii", errors="replace") as fh:
        meas = parse_mt0(fh.read())

    vdd = float(G.VDD_VALUE)
    role_of = {sn.net: sn.role for sn in ccc.state_nodes}
    # map probe node -> logical net (strip x1. and #suffix)
    results: List[P2NodeResult] = []
    all_ok = True
    for node in probe_nodes:
        net = node.replace("x1.", "").split("#")[0]
        exp_d = init.required_state.get(net)
        exp = exp_d.value if exp_d else None
        mv = meas.get(meas_map[node])
        mb = _bit(mv, vdd)
        ok = (mb is not None and exp is not None and mb == exp)
        all_ok = all_ok and ok
        results.append(P2NodeResult(net, role_of.get(net, "?"), mv, mb, exp, ok))
    return P2Result(True, all_ok, results, "")
