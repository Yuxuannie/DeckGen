"""
engine/pipeline.py -- Wire Stages 0-5 into one deterministic run (spec SS5).

run_pipeline() is the single data-flow spine: parse -> ccc -> sensitize ->
initialize -> deckgen -> verify. It takes an arc id and a DataAccess backend;
it knows nothing about fixture-vs-real (that choice is made before it is called).
"""
from __future__ import annotations

from engine.dataaccess import DataAccess
from engine.stages import (
    stage0_parse,
    stage1_ccc,
    stage2_sensitize,
    stage3_initialize,
    stage4_deckgen,
    stage5_verify,
)
from engine.types import Arc, PipelineResult


def run_pipeline(arc_id: str, da: DataAccess) -> PipelineResult:
    log: list[str] = []

    record = da.read_arc(arc_id)
    arc = Arc.from_record(record)

    src = da.read_netlist(arc.cell)
    graph = stage0_parse.parse(src, arc.cell)
    bridges = sum(1 for c in graph.checks if "BRIDGE" in c)
    log.append(f"S0 parse    : {graph.checks[0]} "
               f"[LPE R-merge; bridges={bridges}]")

    ccc = stage1_ccc.decompose(graph)
    roles = {}
    for s in ccc.state_nodes:
        roles.setdefault(s.role, []).append(s.net)
    log.append(f"S1 ccc      : {len(ccc.components)} CCC(s); storage "
               f"{ {r: v for r, v in sorted(roles.items())} } [Bryant, structural]")

    sens = stage2_sensitize.derive(graph, arc)
    log.append(f"S2 sensitize: biases {{{', '.join(f'{k}={v.value}' for k, v in sens.side_biases.items())}}} "
               f"[STUB -> SAT]")

    init = stage3_initialize.derive(ccc, arc)
    log.append(f"S3 init     : probes {init.probes}, precycle={init.precycle_count.value} [STUB]")

    meas = da.read_measurement_block(record)
    model = da.read_model()
    deck = stage4_deckgen.assemble(graph, arc, sens, init, meas, model)
    log.append(f"S4 deckgen  : {deck.line_count()} lines, measurement passed-through [WIRED]")

    verdict = stage5_verify.verify(deck, None, arc, ccc, sens, init)
    log.append(f"S5 verify   : overall={verdict.overall.value} (no simulator) [STUB]")

    return PipelineResult(
        arc=arc, graph=graph, ccc=ccc, sens=sens, init=init,
        deck=deck, verdict=verdict, backend_name=da.name, stage_log=log,
    )
