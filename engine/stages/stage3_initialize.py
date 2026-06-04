"""
Stage 3 -- Initialization derivation (drive-and-settle) + P2 probes (spec SS5, SS9).
  in : CCCResult + Arc        out: InitializationResult

STUB. Production derives each state node's required pre-edge value from the
measured transition, then synthesizes a multi-cycle drive-and-settle stimulus
that walks the cell into that state (init is partly hidden in the pre-cycle
waveform, not only in .nodeset -- spec SS3). SEGMENT 1 emits placeholder
required states + a placeholder stimulus so Stage 4/5 have typed inputs.
P2 (initial state correct) is the load-bearing property for this milestone.
"""
from __future__ import annotations

from engine.types import Arc, CCCResult, Derivation, InitializationResult

STAGE = "S3.init"


def derive(ccc: CCCResult, arc: Arc) -> InitializationResult:
    # State nodes now come from Stage 1 STRUCTURALLY (cross-coupled SCCs), not by
    # name. Required pre-edge VALUES are still a stub (SEGMENT-2-next: derive from
    # the measured transition + drive-and-settle).
    required_state = {
        sn.net: Derivation(
            1, f"PLACEHOLDER value; node is structural {sn.role} state node "
               f"(from Stage 1)", STAGE)
        for sn in ccc.state_nodes
    }
    if not required_state:
        required_state = {"<none>": Derivation(
            None, "PLACEHOLDER: Stage 1 found no storage node", STAGE)}
    stimulus = [
        "* PLACEHOLDER drive-and-settle pre-cycle (SEGMENT 2 synthesizes the real one)",
        "VCP CP 0 PULSE(0 vdd 0 50p 50p 1n 2n)",
        "VD  D  0 PWL(0 0 1n 0 1.05n vdd)",
    ]
    precycle_count = Derivation(
        2, "PLACEHOLDER: pre-cycles to settle the latch before the capturing edge", STAGE)
    probes = [sn.net for sn in ccc.state_nodes]   # probe each identified state node for P2
    return InitializationResult(
        required_state=required_state,
        stimulus=stimulus,
        precycle_count=precycle_count,
        probes=probes,
    )
