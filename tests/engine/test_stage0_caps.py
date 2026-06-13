"""
Stage 0 Layer-B retention (parasitic C) against the synthetic LPE fixture whose
cap ground truth we know from the generator (_gen_sdf_lpe.py):
    CA1 XMLA0#g VSS 1.2e-18   -> grounded on ml_a
    CA2 XSLA0#g VSS 1.1e-18   -> grounded on sl_a
    CF1 XMLA0#g XSLA0#g 3.4e-19 -> coupling ml_a <-> sl_a
    CA3 XOUT0#d VSS 2.0e-18   -> grounded on Q
These assert the parser RETAINS the C network and maps its endpoints to LOGICAL
nets via the same R-merge map -- the half stage0 used to drop (spec SS2.2/Pillar 3
step 1). Layer A (connectivity) must be unchanged.
"""
import os

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse

FIXTURE = os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
EXPECTED_NETS = {
    "clkb", "seb", "mi", "ml_a", "ml_b", "sl_a", "sl_b", "Q",
    "D", "SI", "SE", "CP", "VDD", "VSS", "VPP", "VBB",
}


def _graph():
    with open(FIXTURE, "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")


def _by_endpoints(caps):
    return {tuple(sorted((c.a, c.b))): c for c in caps}


def test_all_caps_retained():
    assert len(_graph().caps) == 4


def test_cap_endpoints_mapped_to_logical_nets():
    caps = _by_endpoints(_graph().caps)
    assert ("VSS", "ml_a") in caps      # CA1 grounded on master node
    assert ("VSS", "sl_a") in caps      # CA2 grounded on slave node
    assert ("Q", "VSS") in caps         # CA3 grounded on output
    assert ("ml_a", "sl_a") in caps     # CF1 coupling between two signal nets


def test_cap_values_parsed():
    caps = _by_endpoints(_graph().caps)
    assert caps[("VSS", "ml_a")].farads == 1.2e-18
    assert caps[("VSS", "sl_a")].farads == 1.1e-18
    assert caps[("Q", "VSS")].farads == 2.0e-18
    assert caps[("ml_a", "sl_a")].farads == 3.4e-19


def test_grounded_vs_coupling_distinguishable_by_rail_endpoint():
    rails = {"VDD", "VSS", "VPP", "VBB", "0"}
    caps = _graph().caps
    grounded = [c for c in caps if c.a in rails or c.b in rails]
    coupling = [c for c in caps if c.a not in rails and c.b not in rails]
    assert len(grounded) == 3
    assert len(coupling) == 1
    assert {coupling[0].a, coupling[0].b} == {"ml_a", "sl_a"}


def test_cap_provenance_kept():
    for c in _graph().caps:
        assert c.raw.strip().upper().startswith("C")


def test_layer_b_selfcheck_in_checks():
    checks = _graph().checks
    assert any("Layer B" in c and "4 parasitic C retained" in c for c in checks)
    assert not any("C-skip" in c for c in checks)   # fixture caps are all parseable


def test_layer_a_connectivity_unchanged():
    # Regression: retaining C must not alter R-merge nets or introduce bridges.
    g = _graph()
    assert set(g.nets) == EXPECTED_NETS
    assert not any("BRIDGE" in c for c in g.checks)
    assert g.checks[0].startswith("R-merge:")        # pipeline relies on checks[0]


def test_caps_deterministic():
    a = [(c.a, c.b, c.farads) for c in _graph().caps]
    b = [(c.a, c.b, c.farads) for c in _graph().caps]
    assert a == b


def test_value_suffix_parsing():
    # SPICE engineering suffixes tolerated (real LPE may use them).
    src = (".subckt T A VSS\n"
           "XINV A A A VSS nch_svt_mac\n"
           "C1 A VSS 1.2f\n"        # femto
           "C2 A VSS 3p\n"          # pico
           "C3 A VSS 1.0e-18\n"     # plain float
           ".ends T\n")
    g = stage0_parse.parse(src, "T")
    vals = sorted(c.farads for c in g.caps)
    assert vals == [1.0e-18, 1.2e-15, 3.0e-12]
