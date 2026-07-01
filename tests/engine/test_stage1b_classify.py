from engine.stages.storage_view import StorageCore
from engine.stages.stage1b_classify import peel_bits, _pair


def _core(dist, cone):
    # nets are irrelevant to peel_bits; distinct placeholders keep them unequal.
    return StorageCore(nets=frozenset({"n%d_a" % dist, "n%d_b" % dist}),
                       dist_to_out=dist, cone=frozenset(cone))


def _mb8_cores():
    # Transcribed from the real MB8 report: 8 slaves (dist 1) + 8 masters (dist 4),
    # cones nest because the scan chain links bit k into every later bit's cone.
    def qs(k):
        return frozenset("Q%d" % i for i in range(k, 9))
    cores = []
    for k in range(1, 9):                       # slaves, dist 1
        cores.append(StorageCore(frozenset({"sl%d_a" % k, "sl%d_b" % k}), 1, qs(k)))
    for k in range(1, 9):                       # masters, dist 4
        cores.append(StorageCore(frozenset({"ml%d_a" % k, "ml%d_b" % k}), 4, qs(k)))
    return cores


def test_peel_single_bit_two_cores():
    cores = [_core(1, {"Q"}), _core(2, {"Q"})]
    bits, dangling = peel_bits(cores)
    assert len(bits) == 1
    assert bits[0]["cores"] == {0, 1}
    assert bits[0]["outputs"] == ["Q"]
    assert dangling == set()


def test_peel_mb8_recovers_eight_bits():
    cores = _mb8_cores()
    bits, dangling = peel_bits(cores)
    assert len(bits) == 8
    assert dangling == set()
    # smallest cone first: bit for Q8 = {slave8(idx7), master8(idx15)}
    by_output = {b["outputs"][0]: b["cores"] for b in bits}
    assert by_output["Q8"] == {7, 15}
    assert by_output["Q1"] == {0, 8}
    # each bit owns exactly its slave+master pair
    assert all(len(v) == 2 for v in by_output.values())


def test_peel_dangling_core_has_empty_cone():
    cores = [_core(1, {"Q"}), _core(2, set())]   # second core reaches no output
    bits, dangling = peel_bits(cores)
    assert dangling == {1}
    assert len(bits) == 1
    assert bits[0]["cores"] == {0}


def test_peel_complementary_output_joins_same_bit():
    # Q and QN share the same reacher set -> QN attaches to the existing bit.
    cores = [_core(1, {"Q", "QN"}), _core(2, {"Q", "QN"})]
    bits, dangling = peel_bits(cores)
    assert len(bits) == 1
    assert sorted(bits[0]["outputs"]) == ["Q", "QN"]
    assert bits[0]["cores"] == {0, 1}


def test_pair_single_core_is_latch():
    cores = [_core(1, {"Q"})]
    bit = {"cores": {0}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 1
    assert bc.ff_depth == 0
    assert bc.paired_cleanly is True
    assert bc.stages[0].role == "latch"
    assert bc.outputs == ("Q",)


def test_pair_dff_two_cores_depth_one():
    cores = [_core(1, {"Q"}), _core(2, {"Q"})]      # slave dist1, master dist2
    bit = {"cores": {0, 1}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 2
    assert bc.ff_depth == 1
    assert bc.paired_cleanly is True
    # stages emitted master-first
    assert [s.role for s in bc.stages] == ["master", "slave"]
    assert bc.stages[0].dist_to_out == 2 and bc.stages[1].dist_to_out == 1


def test_pair_sync_depth_two():
    cores = [_core(1, {"Q"}), _core(2, {"Q"}), _core(3, {"Q"}), _core(4, {"Q"})]
    bit = {"cores": {0, 1, 2, 3}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 4
    assert bc.ff_depth == 2
    assert bc.paired_cleanly is True
    assert [s.role for s in bc.stages] == ["master", "slave", "master", "slave"]


def test_pair_odd_core_count_unpaired():
    cores = [_core(1, {"Q"}), _core(2, {"Q"}), _core(3, {"Q"})]
    bit = {"cores": {0, 1, 2}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 3
    assert bc.ff_depth == 1
    assert bc.paired_cleanly is False
    assert "unpaired" in [s.role for s in bc.stages]


import os
from engine.stages import stage0_parse
from engine.stages.stage1b_classify import classify_cores, classify

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SDFX = os.path.join(_REPO, "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt")


def test_classify_cores_latch():
    r = classify_cores([_core(1, {"Q"})])
    assert r.verdict == "latch"
    assert len(r.bits) == 1 and r.bits[0].ff_depth == 0


def test_classify_cores_ff_chain():
    r = classify_cores([_core(1, {"Q"}), _core(2, {"Q"})])
    assert r.verdict == "ff_chain"
    assert r.bits[0].ff_depth == 1


def test_classify_cores_multibit_mb8():
    r = classify_cores(_mb8_cores(), "MB8SRLSDFQSXGZ2422MZD1BWP130HPNPN3P48CPD")
    assert r.verdict == "multibit"
    assert len(r.bits) == 8
    assert all(b.ff_depth == 1 for b in r.bits)
    assert r.divergence == ""                    # name family 'mb' agrees


def test_classify_cores_odd_is_reviewed_ff_chain():
    r = classify_cores([_core(1, {"Q"}), _core(2, {"Q"}), _core(3, {"Q"})])
    assert r.verdict == "ff_chain"
    assert r.bits[0].paired_cleanly is False
    assert "odd" in r.reason.lower()


def test_classify_cores_dangling_unsupported():
    r = classify_cores([_core(1, {"Q"}), _core(2, set())])
    assert r.verdict == "recognized_unsupported"
    assert "drive no output" in r.reason


def test_classify_cores_no_cores_is_combinational():
    r = classify_cores([])
    assert r.verdict == "combinational"


def test_classify_cores_name_divergence():
    # name 'DFFX1' -> family flop -> implies ff_chain, but structure is a latch.
    r = classify_cores([_core(1, {"Q"})], "DFFX1")
    assert r.verdict == "latch"                  # structure wins
    assert r.divergence != ""
    assert "flop" in r.divergence


def test_classify_never_raises_on_bad_cores():
    class Bad:
        cone = frozenset({"Q"})
        # missing dist_to_out / nets -> _pair blows up
    r = classify_cores([Bad()])
    assert r.verdict == "recognized_unsupported"
    assert r.reason.startswith("internal:")


def test_classify_graph_sdfx_is_ff_chain_depth_one():
    g = stage0_parse.parse(open(_SDFX).read(), "SDFX_LPE_PLACEHOLDER")
    r = classify(g)
    assert r.verdict == "ff_chain"
    assert len(r.bits) == 1
    assert r.bits[0].ff_depth == 1
    assert [s.role for s in r.bits[0].stages] == ["master", "slave"]
