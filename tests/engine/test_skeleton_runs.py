"""
Skeleton smoke test: the full pipeline runs end-to-end on the placeholder
fixture and emits a structured P1/P2/P3 verdict. Asserts wiring + determinism,
NOT correctness of derivations (those are SEGMENT 2 stubs).
"""
import os

from engine.config import ENGINE_DIR, load_config
from engine.dataaccess import make_data_access
from engine.pipeline import run_pipeline
from engine.types import PStatus
from engine.verdict import render


def _result():
    config = load_config(os.path.join(ENGINE_DIR, "config.fixture.json"))
    da = make_data_access(config, base_dir=ENGINE_DIR)
    return run_pipeline(config["arc"], da)


def test_pipeline_runs_end_to_end():
    r = _result()
    assert r.backend_name == "fixture"
    assert len(r.stage_log) == 6                  # one line per stage S0..S5
    assert r.graph.devices                        # parser produced devices
    assert r.deck.line_count() > 0                # deck assembled


def test_emits_three_verdicts():
    r = _result()
    assert [r.verdict.p1.name, r.verdict.p2.name, r.verdict.p3.name] == ["P1", "P2", "P3"]
    assert r.verdict.overall == PStatus.STUB      # skeleton: stages not implemented


def test_measurement_block_passed_through_unchanged():
    r = _result()
    # The Liberate block must appear verbatim in the deck (engine never edits it).
    assert "hold_cp_d" in r.deck.sections["measurement"]


def test_deterministic():
    a, b = _result(), _result()
    assert render(a) == render(b)                 # same inputs -> identical output


def test_every_derived_value_carries_a_reason():
    r = _result()
    for d in r.sens.side_biases.values():
        assert d.reason and d.stage
    for d in r.init.required_state.values():
        assert d.reason and d.stage
