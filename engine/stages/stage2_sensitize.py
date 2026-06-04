"""
Stage 2 -- Sensitization derivation + P1 obligation (spec SS5, SS9).
  in : DeviceGraph + Arc        out: SensitizationResult

STUB. Production ADOPTS a SAT solver (z3-solver) and encodes the
Boolean-difference obligation: prove the measured path is live and competing
paths are masked under the chosen side-pin biases. SEGMENT 1 emits placeholder
biases for the hold(CP,D) when=SE example so Stage 4/5 have typed inputs.
"""
from __future__ import annotations

from engine.types import Arc, DeviceGraph, Derivation, SensitizationResult

STAGE = "S2.sens"


def derive(graph: DeviceGraph, arc: Arc) -> SensitizationResult:
    # PLACEHOLDER: biases inferred from the arc's when-string, not from topology+SAT.
    side_biases = {
        "SE": Derivation(
            1, f"PLACEHOLDER: when='{arc.when}' reads as 'select functional D path'", STAGE),
        "SI": Derivation(
            0, "PLACEHOLDER: scan input held to a non-interfering value", STAGE),
    }
    masked_paths = ["scan path via SI (PLACEHOLDER -- not proven)"]
    p1_obligation = (
        f"sensitize {arc.constr_pin}->capture path; mask scan(SI) path "
        f"under SE={side_biases['SE'].value} [to be discharged by SAT]"
    )
    return SensitizationResult(
        side_biases=side_biases,
        masked_paths=masked_paths,
        p1_obligation=p1_obligation,
    )
