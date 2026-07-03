"""B3 step 1 -- precycle_count derived from the B2 structural class.

Verifies stage3's _precycle_from_seq mapping (latch=0, ff_chain=depth,
multibit=deepest bit, unsupported/None=1 flagged) and that the SDFX fixture
end-to-end still yields precycle 1 (depth-1 ff_chain -- regression guard).
"""
import os

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize, stage3_initialize
from engine.stages.stage3_initialize import _precycle_from_seq
from engine.stages.storage_view import StorageCore
from engine.stages.stage1b_classify import classify_cores, classify
from engine.types import Arc


def _C(dist, cone, tag):
    return StorageCore(nets=frozenset({tag + "_a", tag + "_b"}),
                       dist_to_out=dist, cone=frozenset(cone))


def test_precycle_latch_is_zero():
    seq = classify_cores([_C(1, {"Q"}, "s")])
    assert seq.verdict == "latch"
    assert _precycle_from_seq(seq).value == 0


def test_precycle_ff_chain_depth_one():
    seq = classify_cores([_C(1, {"Q"}, "s"), _C(2, {"Q"}, "m")])
    assert seq.verdict == "ff_chain"
    assert _precycle_from_seq(seq).value == 1


def test_precycle_sync_depth_two():
    seq = classify_cores([_C(1, {"Q"}, "a"), _C(2, {"Q"}, "b"),
                          _C(3, {"Q"}, "c"), _C(4, {"Q"}, "d")])
    assert seq.verdict == "ff_chain" and seq.bits[0].ff_depth == 2
    assert _precycle_from_seq(seq).value == 2


def test_precycle_multibit_uses_deepest_bit():
    # two independent depth-1 bits -> deepest depth is 1.
    seq = classify_cores([_C(1, {"Qa"}, "sa"), _C(2, {"Qa"}, "ma"),
                          _C(1, {"Qb"}, "sb"), _C(2, {"Qb"}, "mb")])
    assert seq.verdict == "multibit" and len(seq.bits) == 2
    assert _precycle_from_seq(seq).value == 1


def test_precycle_unsupported_defaults_one_with_reason():
    seq = classify_cores([_C(1, {"Q"}, "s"), _C(2, set(), "d")])   # dangling core
    assert seq.verdict == "recognized_unsupported"
    d = _precycle_from_seq(seq)
    assert d.value == 1
    assert "recognized_unsupported" in d.reason


def test_precycle_none_is_legacy_one():
    assert _precycle_from_seq(None).value == 1


def test_stage3_sdfx_precycle_via_classify():
    # SDFX is a depth-1 master/slave FF-chain; passing seq keeps precycle 1.
    with open(os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt"),
              "r", encoding="ascii") as fh:
        g = stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell="SDFX_LPE_PLACEHOLDER", arc_type="hold",
              rel_pin="CP", rel_dir="rise", constr_pin="D", constr_dir="fall",
              when="notSE_SI", measurement="")
    sens = stage2_sensitize.derive(g, arc, ccc)
    seq = classify(g, "SDFX_LPE_PLACEHOLDER")
    assert seq.verdict == "ff_chain"
    init = stage3_initialize.derive(g, ccc, arc, sens, seq)
    assert init.precycle_count.value == 1
