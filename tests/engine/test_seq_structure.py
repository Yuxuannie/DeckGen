"""
Layer 1 (Demo 3 research lane) -- sequential STRUCTURE extraction.

These ARE test-covered (ARCHITECTURE.md sec 5: CCC+SCC structure extraction is a
real, demoable layer). Layers 2-3 are derivations, not tests.

Worked example: SDFX_LPE_PLACEHOLDER (synthetic scan-DFF). Ground truth from the
generator: master cross-couple ml_a/ml_b, slave cross-couple sl_a/sl_b, clock CP
buffered to clkb. The extractor must recover this BLIND (no name matching).

Agreement check (Red Line D extended): the SCC-based discriminator must AGREE with
the engine core's stage2_sensitize.is_combinational_arc on every combinational
fixture, and must REFINE (not contradict) it on the DFF's CP->Q arc.
"""
import glob
import os

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc
from engine.stages import stage2_sensitize as s2
from engine import seq_structure as ss
from engine.types import Arc

FIXDIR = os.path.join(ENGINE_DIR, "fixtures")
SDFX = os.path.join(FIXDIR, "SDFX_LPE_PLACEHOLDER.subckt")


def _graph(path, cell):
    with open(path, "r", encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), cell)


# ---- sequential cell: SDFX ----------------------------------------------
def test_sdfx_is_sequential():
    st = ss.extract(_graph(SDFX, "SDFX_LPE_PLACEHOLDER"))
    assert st.is_sequential is True


def test_sdfx_two_storage_loops_master_slave():
    st = ss.extract(_graph(SDFX, "SDFX_LPE_PLACEHOLDER"))
    loops = {l.role: set(l.nets) for l in st.storage_loops}
    assert loops.get("master") == {"ml_a", "ml_b"}
    assert loops.get("slave") == {"sl_a", "sl_b"}


def test_sdfx_loops_ordered_master_then_slave():
    st = ss.extract(_graph(SDFX, "SDFX_LPE_PLACEHOLDER"))
    assert [l.role for l in st.storage_loops] == ["master", "slave"]


def test_sdfx_clock_pin_and_path():
    st = ss.extract(_graph(SDFX, "SDFX_LPE_PLACEHOLDER"))
    assert st.clock_pin == "CP"
    assert st.clock_path == ["clkb"]


def test_sdfx_cp_to_q_arc_traverses_storage():
    g = _graph(SDFX, "SDFX_LPE_PLACEHOLDER")
    st = ss.extract(g)
    assert ss.arc_traverses_storage(g, "CP", "Q", st) is True


def test_sdfx_state_nodes_carry_structural_reason():
    st = ss.extract(_graph(SDFX, "SDFX_LPE_PLACEHOLDER"))
    for l in st.storage_loops:
        assert "cross-coupled feedback loop" in l.derivation.reason


# ---- combinational fixtures: no SCC, discriminator AGREES ----------------
def _comb_fixtures():
    return sorted(glob.glob(os.path.join(FIXDIR, "*_RECON.subckt")))


def test_combinational_fixtures_have_no_storage():
    for fx in _comb_fixtures():
        name = os.path.basename(fx).replace(".subckt", "")
        st = ss.extract(_graph(fx, name))
        assert st.is_sequential is False, f"{name} wrongly flagged sequential"
        assert st.storage_loops == []
        assert st.clock_pin is None


def test_discriminator_agrees_on_combinational():
    """Red Line D extended: SCC-based seq signal agrees with engine-core
    is_combinational_arc on every combinational cell."""
    for fx in _comb_fixtures():
        name = os.path.basename(fx).replace(".subckt", "")
        g = _graph(fx, name)
        st = ss.extract(g)
        ccc = stage1_ccc.decompose(g)
        driven = {d.terminals["d"] for d in g.devices}
        rails = {"VDD", "VSS", "VPP", "VBB", "0"}
        ins = [p for p in g.ports if p not in rails and p not in driven]
        outs = [p for p in g.ports if p in driven and p not in rails]
        rel, out = ins[0], outs[0]
        arc = Arc(cell=name, arc_type="combinational", rel_pin=rel, rel_dir="rise",
                  constr_pin=out, constr_dir="fall", when="NO_CONDITION",
                  measurement="", raw={"probe_pin": out})
        loc = s2.is_combinational_arc(g, arc, ccc)
        note = ss.check_discriminator(g, rel, out, loc, st)
        assert note.startswith("discriminator AGREE"), f"{name}: {note}"


def test_discriminator_refines_on_dff_cp_to_q():
    """The DFF CP->Q arc is whole-arc sequential, while the engine core's
    CCC-LOCAL check calls Q's own inverter combinational. The check must REFINE
    (document the scope difference), never crash or claim contradiction."""
    g = _graph(SDFX, "SDFX_LPE_PLACEHOLDER")
    st = ss.extract(g)
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell="SDFX", arc_type="delay", rel_pin="CP", rel_dir="rise",
              constr_pin="D", constr_dir="fall", when="NO_CONDITION",
              measurement="", raw={"probe_pin": "Q"})
    loc = s2.is_combinational_arc(g, arc, ccc)
    note = ss.check_discriminator(g, "CP", "Q", loc, st)
    assert note.startswith("discriminator REFINE")


def test_extract_is_deterministic():
    g = _graph(SDFX, "SDFX_LPE_PLACEHOLDER")
    a, b = ss.extract(g), ss.extract(g)
    assert [l.nets for l in a.storage_loops] == [l.nets for l in b.storage_loops]
    assert a.clock_pin == b.clock_pin and a.clock_path == b.clock_path
