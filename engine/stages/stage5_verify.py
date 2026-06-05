"""
Stage 5 -- Verification harness, P1/P2/P3 verdicts (spec SS6).
  in : Deck + sim result (None in SEGMENT 1) + upstream stage outputs
  out: Verdict

STUB. With no simulator and stubbed derivations every property reports STUB,
but the verdict is fully structured and self-describing: it shows each derived
value WITH its reason, so a single screenshot is judge-able (spec SS7.4/7.5).
The check each property WILL run is named explicitly.
"""
from __future__ import annotations

from typing import Optional

from engine.types import (
    Arc,
    CCCResult,
    Deck,
    InitializationResult,
    Property,
    PStatus,
    SensitizationResult,
    Verdict,
)

STAGE = "S5.verify"


def p2_property(p2res) -> Property:
    """Build the real P2 Property from a sim.P2Result (differential)."""
    if not p2res.ran:
        return Property("P2", "Initial state", PStatus.STUB,
                        detail=[f"sim not run: {p2res.note}"])
    status = PStatus.PASS if p2res.passed else PStatus.FAIL
    detail = []
    for n in p2res.nodes:
        vc = f"{n.v_cap:.3f}" if n.v_cap is not None else "n/a"
        vi = f"{n.v_inv:.3f}" if n.v_inv is not None else "n/a"
        verd = "ok" if n.ok else "FAIL"
        detail.append(f"{n.role:<6} {n.node:<8} D={p2res.d_cap}:{vc}(={n.bit_cap}) "
                      f"D={p2res.d_inv}:{vi}(={n.bit_inv})  {n.behavior}  [{verd}]")
    detail.append(f"complementary pairs: {'ok' if p2res.complementary else 'FAIL'}")
    detail.append(f"check : drive D={p2res.d_cap} vs D={p2res.d_inv}; master must follow D, "
                  f"slave must not -- RAN")
    return Property("P2", "Initial state", status, detail=detail)


def verify(
    deck: Deck,
    sim_result: Optional[dict],
    arc: Arc,
    ccc: CCCResult,
    sens: SensitizationResult,
    init: InitializationResult,
) -> Verdict:
    # P1 -- Sensitization correct (Boolean difference over the switch-level model).
    p1 = Property(
        "P1", "Sensitization", PStatus.PASS if sens.proven else PStatus.FAIL,
        detail=(
            [f"obligation : {sens.p1_obligation}"]
            + [f"bias {pin:<3}: {d.value}  <= {d.reason}"
               for pin, d in sens.side_biases.items()]
            + [f"masked     : {', '.join(sens.masked_paths) or '(none)'}"]
            + [f"arc-check  : {sens.arc_check}"]
            + [f"check      : switch-level Boolean difference, {sens.clock_phase or 'n/a'} "
               f"-- {'PROVEN' if sens.proven else 'NOT PROVEN'}"]
        ),
    )

    # P2 -- Initial state correct (probe state nodes vs derived required values).
    # This is the property the incumbent flow cannot provide (spec SS6/SS9).
    by_role: dict = {}
    for sn in ccc.state_nodes:
        by_role.setdefault(sn.role, []).append(sn.net)
    structural = "; ".join(f"{role}={nodes}" for role, nodes in sorted(by_role.items())) or "none"
    p2 = Property(
        "P2", "Initial state", PStatus.STUB,
        detail=(
            [f"state nodes: {structural}  <= structural (name-blind, Stage 1)"]
            + [f"{node} expect: {d.value}  <= {d.reason}"
               for node, d in init.required_state.items()]
            + [f"measured   : n/a ({'no simulator' if sim_result is None else 'sim present'})"]
            + [f"check      : probe {','.join(init.probes)} at settle vs derived -- NOT RUN"]
        ),
    )

    # P3 -- Measurement context consistent (window/edge alignment, steady state).
    p3 = Property(
        "P3", "Meas context", PStatus.STUB,
        detail=[
            f"window     : capturing {arc.rel_pin} edge then {arc.constr_pin} change (hold bisect)",
            f"precycle   : {init.precycle_count.value}  <= {init.precycle_count.reason}",
            "check      : steady-state-before-edge -- NOT RUN (skeleton)",
        ],
    )

    return Verdict(p1=p1, p2=p2, p3=p3)
