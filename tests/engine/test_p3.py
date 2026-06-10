"""P3 (measurement context consistent) -- spec section 4 of
docs/superpowers/specs/2026-06-09-v2-audit-sidecar-design.md.
Worked example: mpw/template__CP__rise__fall__1.sp with max_slew=1n."""
from engine.stages.stage5_verify import MeasContext, p3_property
from engine.types import Arc, Derivation, InitializationResult, PStatus

# stdvs_mpw_rise_fall_rise_fall with t01=10n t02=20n t03=50n t04=55n (ms=1n)
EDGES = [("t01", 10.0, "rise"), ("t02", 20.0, "fall"),
         ("t03", 50.0, "rise"), ("t04", 55.0, "fall")]


def _arc(rel_dir="rise"):
    return Arc(cell="X", arc_type="hold", rel_pin="CP", rel_dir=rel_dir,
               constr_pin="D", constr_dir="fall", when="", measurement="")


def _init(precycles=1, probes=("x1.ml_a",)):
    return InitializationResult(
        required_state={}, stimulus=[],
        precycle_count=Derivation(precycles, "test", "S3.init"),
        probes=list(probes))


def _ctx(**over):
    kw = dict(rel_edges=EDGES, trig_cross=3, trig_td_ns=0.0,
              capture_t_ns=50.0, capture_dir="rise", vdd=0.45, notes=[])
    kw.update(over)
    return MeasContext(**kw)


def test_static_pass_is_stub_without_sim():
    p3 = p3_property(_ctx(), _init(), _arc())
    assert p3.status is PStatus.STUB          # (a),(b) green; (c) NOT RUN
    assert any("ALIGNED" in d for d in p3.detail)
    assert any("NOT RUN" in d for d in p3.detail)


def test_misaligned_capture_dir_fails():
    p3 = p3_property(_ctx(capture_dir="fall"), _init(), _arc("rise"))
    assert p3.status is PStatus.FAIL
    assert any("MISALIGNED" in d for d in p3.detail)


def test_precycle_mismatch_fails():
    # capture at t01: zero full cycles before it, S3 derived 1
    p3 = p3_property(_ctx(capture_t_ns=10.0), _init(precycles=1), _arc())
    assert p3.status is PStatus.FAIL
    assert any("MISMATCH" in d for d in p3.detail)


def test_unresolved_context_is_stub_with_reason():
    p3 = p3_property(_ctx(capture_t_ns=None,
                          notes=["UNRESOLVED: .param weird = 'a*b'"]),
                     _init(), _arc())
    assert p3.status is PStatus.STUB
    assert any("UNRESOLVED" in d for d in p3.detail)


def test_no_context_is_stub():
    p3 = p3_property(None, _init(), _arc())
    assert p3.status is PStatus.STUB


def test_sim_present_but_zero_vdd_is_stub_not_fail():
    # vdd=0 -> no rail reference -> check (c) unevaluable -> STUB, never FAIL
    sim = ([0.0, 4.0e-8], {"v(x1.ml_a)": [0.0, 0.45]})
    p3 = p3_property(_ctx(vdd=0.0), _init(probes=("x1.ml_a",)), _arc(), sim)
    assert p3.status is PStatus.STUB
    assert any("no VDD reference" in d for d in p3.detail)


from engine.wave import parse_csdf

CSDF_SETTLED = """#H
#N 'v(x1.ml_a)' 'v(x1.sl_a)'
#C 0.0 2  0.0 0.45
#C 4.0e-8 2  0.448 0.002
#C 6.0e-8 2  0.45 0.0
"""

CSDF_MIDRAIL = """#H
#N 'v(x1.ml_a)' 'v(x1.sl_a)'
#C 0.0 2  0.0 0.45
#C 4.0e-8 2  0.225 0.002
#C 6.0e-8 2  0.45 0.0
"""


def test_settled_nodes_pass_with_sim():
    sim = parse_csdf(CSDF_SETTLED)
    p3 = p3_property(_ctx(), _init(probes=("x1.ml_a", "x1.sl_a")), _arc(), sim)
    assert p3.status is PStatus.PASS
    assert any("RAN" in d for d in p3.detail)


def test_midrail_node_fails_with_sim():
    # x1.ml_a sits at VDD/2 at the last sample before capture (50ns)
    sim = parse_csdf(CSDF_MIDRAIL)
    p3 = p3_property(_ctx(), _init(probes=("x1.ml_a", "x1.sl_a")), _arc(), sim)
    assert p3.status is PStatus.FAIL
    assert any("mid-rail" in d for d in p3.detail)


def test_missing_trace_fails_with_sim():
    sim = parse_csdf(CSDF_SETTLED)
    p3 = p3_property(_ctx(), _init(probes=("x1.nope",)), _arc(), sim)
    assert p3.status is PStatus.FAIL
    assert any("MISSING" in d for d in p3.detail)
