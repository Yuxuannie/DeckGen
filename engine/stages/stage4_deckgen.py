"""
Stage 4 -- Deck generation (spec SS5).
  in : DeviceGraph + Arc + Sensitization + Initialization + measurement + model
  out: Deck

The data-flow wiring here is REAL (string assembly); the section *contents*
come from upstream stubs. The measurement block enters as an opaque, pre-formed
unit and is inserted UNCHANGED -- the engine positions it, never authors it.
"""
from __future__ import annotations

from engine.types import (
    Arc,
    Deck,
    DeviceGraph,
    InitializationResult,
    SensitizationResult,
)

STAGE = "S4.deck"


def assemble(
    graph: DeviceGraph,
    arc: Arc,
    sens: SensitizationResult,
    init: InitializationResult,
    measurement_block: str,
    model_text: str,
) -> Deck:
    sections: dict[str, str] = {}

    sections["header"] = (
        f"* DeckGen v2 (SEGMENT 1 skeleton) -- {arc.label()}  cell={arc.cell}\n"
        f"* PLACEHOLDER deck: derivations are stubs.\n"
        f".include generic_mos.model"
    )
    sections["sensitization"] = "\n".join(
        ["* --- sensitization (side-pin static biases) ---"]
        + [f"V{pin} {pin} 0 {d.value}*vdd  $ {d.reason}"
           for pin, d in sens.side_biases.items()]
    )
    sections["initialization"] = "\n".join(
        ["* --- initialization (drive-and-settle + probes) ---"]
        + init.stimulus
        + [f".probe v({node})  $ P2 state-node probe" for node in init.probes]
    )
    sections["measurement"] = (
        "* --- measurement block (Liberate, passed through UNCHANGED) ---\n"
        + measurement_block.rstrip("\n")
    )

    text = "\n".join([
        sections["header"],
        sections["sensitization"],
        sections["initialization"],
        sections["measurement"],
        ".end",
    ]) + "\n"

    return Deck(cell=arc.cell, text=text, sections=sections)
