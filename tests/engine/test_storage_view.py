import os
from engine.stages import stage0_parse
from engine.stages.storage_view import build_storage_view

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SYNTH = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/SYNTH_LATCH.spi")
_SDFX = os.path.join(_REPO, "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt")


def test_synth_latch_one_core_cone_q():
    g = stage0_parse.parse(open(_SYNTH).read(), "SYNTH_LATCH")
    view = build_storage_view(g)
    assert view.outputs == ("Q",)
    assert len(view.cores) == 1
    core = view.cores[0]
    assert len(core.nets) == 2                 # cross-coupled pair
    assert core.cone == frozenset({"Q"})
    assert core.dist_to_out == 1


def test_sdfx_two_cores_distinct_distance():
    g = stage0_parse.parse(open(_SDFX).read(), "SDFX_LPE_PLACEHOLDER")
    view = build_storage_view(g)
    assert view.outputs == ("Q",)
    assert len(view.cores) == 2
    # cores sorted by dist_to_out ascending: slave (nearer) then master (farther)
    assert view.cores[0].dist_to_out == 1
    assert view.cores[1].dist_to_out == 2
    assert all(c.cone == frozenset({"Q"}) for c in view.cores)
