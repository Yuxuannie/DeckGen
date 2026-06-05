"""
engine/p2_deck.py -- build a runnable HSPICE deck that checks P2 (initial state).

P2 asks: at the settle point before the capturing edge, do the CCC storage nodes
sit at the derived required values? This deck:
  - REUSES the golden collateral (.inc model/netlist/waveform, corner) so the run
    matches the golden environment;
  - applies the P1-proven sensitization biases (SE/SI static);
  - drives an explicit drive-and-settle CP/D sequence (PROTOTYPE timing from the
    golden slews + a simple cycle) that loads the prior value, then sets the
    captured value;
  - measures each storage node's voltage at the settle point with `.meas ... find
    v(x1.<node>) at='t_settle'` -> parsed back from the .mt0.

The drive-and-settle TIMING here is prototype-level (explicit PWL, not the golden
stdvs bisection machinery); it is enough to confirm the flop reaches the derived
state. It is clearly separated from the passed-through measurement domain.
"""
from __future__ import annotations

from typing import List

from engine import golden_env as G
from engine.types import Arc, InitializationResult, SensitizationResult

STAGE = "S4.p2deck"

# Prototype cycle timing (ns). Edges spaced well beyond the golden slews so the
# flop settles between transitions.
_CYC = 2.0          # clock period (ns)
_TR = 0.05          # edge transition (ns)


def _v(value) -> str:
    return "vdd_value" if value == 1 else "0"


def build(arc: Arc, sens: SensitizationResult, init: InitializationResult,
          probe_nodes: List[str]) -> tuple[str, dict]:
    """Return (deck_text, meas_name_map) where meas_name_map: probe_node -> meas name."""
    cap = 1 if arc.constr_dir == "fall" else 0   # captured value (hold convention)
    prev = 1 - cap                               # prior value loaded in pre-cycle
    rel = arc.rel_pin

    # Timeline (ns):
    #   pre-cycle: D=prev, one full CP cycle loads prior into the latch
    #   capture  : D=cap before the capturing CP edge
    #   t_settle : just before the capturing edge, after the master is transparent
    t_pre_clk_r = 1.0
    t_pre_clk_f = t_pre_clk_r + _CYC / 2
    t_dchange = t_pre_clk_f + 0.5            # set D=cap after prior is stored
    t_settle = t_dchange + 0.4               # probe here (master transparent, settled)
    t_cap_edge = t_settle + 0.2              # the capturing CP edge
    t_end = t_cap_edge + _CYC

    def pwl(name, node, seq):
        pts = " ".join(f"{t}n {_v(v)}" for t, v in seq)
        return f"V{name} {node} 0 pwl({pts})"

    lines: List[str] = []
    lines.append("** DeckGen v2 -- P2 (initial state) check deck **")
    lines.append(f"* cell {arc.cell} | arc {arc.label()} | captured={cap} prior={prev}")
    lines.append("")
    lines.append("* ===== COLLATERAL (golden, reused) =====")
    lines.append(f".inc '{G.INC_WAVEFORM}'")
    lines.append(f".inc '{G.INC_MODEL}'")
    lines.append(f".inc '{G.INC_NETLIST}'")
    lines.append(f".param vdd_value = '{G.VDD_VALUE}'")
    lines.append(f".param vss_value = {G.VSS_VALUE}")
    lines.append(f".temp {G.TEMP}")
    lines.append(f".param cl = '{G.CL}'")
    lines.append("VVDD VDD 0 'vdd_value'")
    lines.append("VVSS VSS 0 'vss_value'")
    lines.append("VVPP VPP 0 'vdd_value'")
    lines.append("VVBB VBB 0 'vss_value'")
    lines.append("CQ Q 0 'cl'")
    lines.append("")
    lines.append(f"X1 {' '.join(G.PORTS)} {arc.cell}")
    lines.append("")
    lines.append(f"* ===== sensitization (P1 {'PROVEN' if sens.proven else 'UNPROVEN'}) =====")
    for pin, d in sens.side_biases.items():
        lines.append(f"V{pin} {pin} 0 '{_v(d.value)}'   $ {pin}={d.value}")
    lines.append("")
    lines.append("* ===== drive-and-settle (prototype PWL) =====")
    lines.append(pwl("CP", rel, [(0, 0), (t_pre_clk_r, 0), (t_pre_clk_r + _TR, 1),
                                 (t_pre_clk_f, 1), (t_pre_clk_f + _TR, 0),
                                 (t_cap_edge, 0), (t_cap_edge + _TR, 1), (t_end, 1)]))
    lines.append(pwl("Ddata", arc.constr_pin, [(0, prev), (t_dchange, prev),
                                               (t_dchange + _TR, cap), (t_end, cap)]))
    lines.append("")
    lines.append(f"* ===== P2 probes @ settle t={t_settle}n =====")
    meas_map = {}
    for node in probe_nodes:
        nm = "p2_" + node.replace("x1.", "").replace("#", "_").replace(".", "_")
        meas_map[node] = nm
        lines.append(f".meas tran {nm} find v({node}) at='{t_settle}n'")
    lines.append("")
    lines.append(f".tran 1p {t_end}n")
    lines.append(".option post")
    lines.append(".end")
    return "\n".join(lines) + "\n", meas_map
