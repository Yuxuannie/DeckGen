"""
Stage 0 (LPE parse + R-merge) and Stage 1 (CCC + storage id) against the
synthetic LPE fixture whose ground truth we know from the generator. These
assert the ALGORITHM recovers the right topology -- it never keys off the
`ml_*`/`sl_*` names; the names are only the test's known-answer.
"""
import os

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc

FIXTURE = os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
EXPECTED_NETS = {
    "clkb", "seb", "mi", "ml_a", "ml_b", "sl_a", "sl_b", "Q",
    "D", "SI", "SE", "CP", "VDD", "VSS", "VPP", "VBB",
}


def _graph():
    with open(FIXTURE, "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")


# ---- Stage 0 -------------------------------------------------------------
def test_parses_all_transistors_with_kind():
    g = _graph()
    assert len(g.devices) == 22
    assert all(d.kind in ("nmos", "pmos") for d in g.devices)


def test_r_merge_recovers_logical_nets():
    g = _graph()
    assert set(g.nets) == EXPECTED_NETS          # 89 raw nodes -> 16 logical nets
    assert not any("BRIDGE" in c for c in g.checks)


def test_device_terminals_map_to_logical_nets():
    g = _graph()
    by_name = {d.name: d for d in g.devices}
    # output inverter pair both drive Q
    assert by_name["XOUT0"].terminals["d"] == "Q"
    assert by_name["XOUT1"].terminals["d"] == "Q"
    # master forward inverter: ml_b = NOT ml_a
    assert by_name["XMLA0"].terminals["d"] == "ml_b"
    assert by_name["XMLA0"].terminals["g"] == "ml_a"


def test_parse_deterministic():
    assert _graph().node_to_net == _graph().node_to_net


# ---- Stage 1 -------------------------------------------------------------
def test_finds_two_crosscoupled_storage_bits():
    ccc = stage1_ccc.decompose(_graph())
    roles = {}
    for sn in ccc.state_nodes:
        roles.setdefault(sn.role, set()).add(sn.net)
    assert roles.get("master") == {"ml_a", "ml_b"}
    assert roles.get("slave") == {"sl_a", "sl_b"}


def test_every_state_node_carries_structural_reason():
    ccc = stage1_ccc.decompose(_graph())
    assert len(ccc.state_nodes) == 4
    for sn in ccc.state_nodes:
        assert "cross-coupled feedback loop" in sn.derivation.reason
        assert sn.derivation.stage == "S1.ccc"
