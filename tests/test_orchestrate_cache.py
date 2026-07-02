"""Per-cell engine cache: parse + CCC-decompose (+ classify) run once per cell,
not once per work item.

generate() expands to N work items spread over few cells; the expensive engine
pipeline (stage0 parse -> stage1 CCC -> classify) depends only on
(cell, netlist), so it must run once per cell. These tests prove the cache is
(a) byte-transparent -- decks and error rows are identical to the uncached path
-- and (b) actually elides the redundant re-parses.
"""
import os

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDFX = os.path.join(_REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")


def _arc_info(cell, arc_type, rel_dir="fall"):
    return {
        "CELL_NAME": cell, "ARC_TYPE": arc_type,
        "REL_PIN": "CP", "REL_PIN_DIR": rel_dir,
        "CONSTR_PIN": "D", "CONSTR_PIN_DIR": "fall",
        "PROBE_PIN_1": "Q", "WHEN": "NO_CONDITION",
        "VDD": "0.75", "TEMP": "25",
        "MAX_SLEW": "1.0000e-11", "OUTPUT_LOAD": "1.0000e-15",
    }


def test_engine_cache_transparent_sequential():
    # SDFX assembles OK; the cached path must produce byte-identical decks.
    from core.deck_assemble import assemble_sequential
    from core.measurement.emit import load_grammar
    src = open(_SDFX, encoding="latin-1").read()
    g = load_grammar()
    ai = _arc_info("SDFX_LPE_PLACEHOLDER", "hold")
    fresh = assemble_sequential(dict(ai), src, g)
    assert fresh["status"] == "OK", fresh["error"]
    cache = {}
    a = assemble_sequential(dict(ai), src, g, engine_cache=cache)
    b = assemble_sequential(dict(ai), src, g, engine_cache=cache)
    assert a["status"] == "OK" and b["status"] == "OK"
    assert a["deck_text"] == fresh["deck_text"]
    assert b["deck_text"] == fresh["deck_text"]


def test_engine_cache_transparent_combinational_errpath():
    # SDFX is sequential, so the combinational emitter returns a named error.
    # Transparency must hold on the error path too: cached == fresh.
    from core.deck_assemble import assemble_combinational
    from core.measurement.emit import load_grammar
    src = open(_SDFX, encoding="latin-1").read()
    g = load_grammar()
    ai = _arc_info("SDFX_LPE_PLACEHOLDER", "combinational")
    fresh = assemble_combinational(dict(ai), src, g)
    cache = {}
    a = assemble_combinational(dict(ai), src, g, engine_cache=cache)
    b = assemble_combinational(dict(ai), src, g, engine_cache=cache)
    assert a == b == fresh


def test_generate_parses_each_cell_once(tmp_path, monkeypatch):
    # Fixture collateral = single cell DFFQ1 expanded to 50 work items. The
    # netlist parse must run ONCE for that cell, not once per work item.
    import shutil
    from tools.scan_collateral import build_manifest
    fixture = os.path.join(_REPO, "tests", "fixtures", "collateral")
    dest = tmp_path / "collateral"
    shutil.copytree(fixture, str(dest))
    build_manifest(str(dest), "N2P_v1.0", "test_lib")

    import engine.stages.stage0_parse as sp
    seen = []
    orig = sp.parse
    monkeypatch.setattr(sp, "parse",
                        lambda src, cell: (seen.append(cell), orig(src, cell))[1])

    from core import orchestrate
    res = orchestrate.generate(str(dest), "N2P_v1.0", "test_lib",
                               str(tmp_path / "out"))
    assert len(res["rows"]) == 50            # 50 work items, all one cell
    assert seen.count("DFFQ1") == 1          # parsed once, not 50x
