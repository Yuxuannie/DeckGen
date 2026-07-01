from engine.stages.storage_view import StorageCore
from engine.stages.stage1b_classify import peel_bits


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
