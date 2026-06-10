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

# Drive-and-settle timing (ns). The first real run was at ss/0.45V/-40C (a SLOW
# corner: golden max_slew ~8ns), where a 2ns cycle / 0.35ns settle left storage
# nodes mid-transition. Scale to the golden slews: ~0.5ns edges (golden rel/constr
# slew) and a generous multi-ns settle window so nodes fully settle before probing.
_TR = 0.5           # edge transition (ns) ~ golden rel/constr slew
_SET = 20.0         # settle window (ns) >> a few * golden max_slew


def _v(value) -> str:
    return "vdd_value" if value == 1 else "0"


def build(arc: Arc, sens: SensitizationResult, init: InitializationResult,
          probe_nodes: List[str], final_d: int = None,
          wave: bool = False) -> tuple[str, dict]:
    """Return (deck_text, meas_name_map) where meas_name_map: probe_node -> meas name.

    final_d overrides the value driven on the constraint pin at the settle point
    (used for the differential P2 check: run with final_d=1 and final_d=0 and
    compare which storage nodes track D vs hold the prior). Default = captured.
    """
    cap = 1 if arc.constr_dir == "fall" else 0   # captured value (hold convention)
    prev = 1 - cap                               # prior loaded in pre-cycle (FIXED)
    d_settle = cap if final_d is None else final_d   # D driven at the settle point
    rel = arc.rel_pin

    # Timeline (ns), slow-corner spaced (each event gets _SET to settle):
    #   0..t_load_r : CP=0 (master transparent), D=prev -> master tracks prev
    #   t_load_r    : CP rises  -> slave captures prev (Q=prev)
    #   t_load_f    : CP falls  -> master transparent again, slave holds prev
    #   t_dchange   : D -> d_settle while master is transparent
    #   t_settle    : PROBE -- master settled to d_settle, slave still holds prev
    #   t_cap_edge  : CP rises  -> would capture d_settle (after the probe)
    t_load_r = 5.0
    t_load_f = t_load_r + _SET
    t_dchange = t_load_f + 5.0
    t_settle = t_dchange + _SET
    t_cap_edge = t_settle + 5.0
    t_end = t_cap_edge + _SET

    def pwl(name, node, seq):
        pts = " ".join(f"{t}n {_v(v)}" for t, v in seq)
        return f"V{name} {node} 0 pwl({pts})"

    lines: List[str] = []
    lines.append("** DeckGen v2 -- P2 (initial state) check deck **")
    lines.append(f"* cell {arc.cell} | arc {arc.label()} | prior={prev} D@settle={d_settle}")
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
    lines.append(pwl("CP", rel, [(0, 0), (t_load_r, 0), (t_load_r + _TR, 1),
                                 (t_load_f, 1), (t_load_f + _TR, 0),
                                 (t_cap_edge, 0), (t_cap_edge + _TR, 1), (t_end, 1)]))
    lines.append(pwl("Ddata", arc.constr_pin, [(0, prev), (t_dchange, prev),
                                               (t_dchange + _TR, d_settle), (t_end, d_settle)]))
    lines.append("")
    lines.append(f"* ===== P2 probes @ settle t={t_settle}n =====")
    meas_map = {}
    for node in probe_nodes:
        nm = "p2_" + node.replace("x1.", "").replace("#", "_").replace(".", "_")
        meas_map[node] = nm
        lines.append(f".meas tran {nm} find v({node}) at='{t_settle}n'")
    lines.append("")
    lines.append(f".tran 1p {t_end}n")
    if wave:
        # ASCII CSDF transient of the probe nodes + stimulus, for an eog waveform.
        lines.append(f".print tran {rel} {arc.constr_pin} "
                     + " ".join(f"v({n})" for n in probe_nodes))
        lines.append(".option post=1 csdf=1")
    else:
        lines.append(".option nomod")       # .meas/.mt0 only; no waveform dump
    lines.append(".end")
    info = {"meas_map": meas_map, "t_settle": t_settle * 1e-9,
            "t_cap_edge": t_cap_edge * 1e-9,
            "rel_edges_ns": [("load_r", t_load_r, "rise"),
                             ("load_f", t_load_f, "fall"),
                             ("cap", t_cap_edge, "rise")]}
    return "\n".join(lines) + "\n", (info if wave else meas_map)
