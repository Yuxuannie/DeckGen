"""core/engine_present.py -- GUI data layer over the v2 engine.
Spec: docs/superpowers/specs/2026-06-10-gui-all-features-showcase-design.md
"""
import os
import xml.dom.minidom as minidom

from core.engine_present import topology_view, combinational_sensitization_view

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDFX = os.path.join(REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
AIOI21 = os.path.join(REPO, "engine", "fixtures", "AIOI21_RECON.subckt")


class TestTopologyView:
    def test_ok_on_engine_fixture(self):
        r = topology_view(SDFX, "SDFX_LPE_PLACEHOLDER", when="notSE_SI")
        assert r["status"] == "OK"
        minidom.parseString(r["svg"])
        assert 'data-net="' in r["svg"]
        assert r["p1"]["status"] == "PASS"
        assert any("bias" in d.lower() or "=" in d for d in r["p1"]["detail"])
        assert len(r["stage_log"]) >= 5
        assert "master" in r["ccc"]["roles"] or "slave" in r["ccc"]["roles"]

    def test_force_bias_fails_and_names_si(self):
        r = topology_view(SDFX, "SDFX_LPE_PLACEHOLDER", when="notSE_SI",
                          force_bias={"SE": 1})
        assert r["status"] == "OK"
        assert r["p1"]["status"] == "FAIL"
        assert "SI" in " ".join(r["p1"]["detail"]) or "SI" in r.get("obligation", "")

    def test_error_path_does_not_raise(self, tmp_path):
        bad = tmp_path / "bad.spi"
        bad.write_text(".subckt BAD a b\n.ends\n", encoding="ascii")
        r = topology_view(str(bad), "BAD")
        assert r["status"] in ("ERROR", "NA")
        assert "error" in r or "p1" in r


import shutil
from core.engine_present import audit_arcs, audit_csv

FIXTURE_COLLATERAL = os.path.join(REPO, "tests", "fixtures", "collateral")
_NODE, _LIB = "N2P_v1.0", "test_lib"
_CORNER = "ssgnp_0p450v_m40c_cworst_CCworst_T"


def _collateral_root(tmp_path):
    dest = tmp_path / "collateral"
    shutil.copytree(os.path.join(FIXTURE_COLLATERAL, _NODE, _LIB),
                    str(dest / _NODE / _LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), _NODE, _LIB)
    return str(dest)


class TestAudit:
    def test_rows_and_summary(self, tmp_path):
        croot = _collateral_root(tmp_path)
        out = audit_arcs(node=_NODE, lib_type=_LIB, corner=_CORNER,
                         arc_ids=["hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1"],
                         collateral_root=croot)
        assert out["rows"], "expected at least one row"
        row = out["rows"][0]
        for k in ("cell", "arc", "corner", "P1", "P2", "P3",
                  "bias_match", "arc_check", "notes"):
            assert k in row
        assert row["cell"] == "DFFQ1"
        s = out["summary"]
        assert s["total"] == len(out["rows"])

    def test_csv_columns_exact_order(self, tmp_path):
        croot = _collateral_root(tmp_path)
        out = audit_arcs(node=_NODE, lib_type=_LIB, corner=_CORNER,
                         arc_ids=["hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1"],
                         collateral_root=croot)
        csv = audit_csv(out["rows"])
        header = csv.splitlines()[0]
        assert header == "cell,arc,corner,P1,P2,P3,bias_match,arc_check,notes"


def test_topology_view_returns_pins():
    r = topology_view(SDFX, "SDFX_LPE_PLACEHOLDER", when="notSE_SI")
    assert "pins" in r and isinstance(r["pins"], list)
    # the SDFX subckt ports include these
    for p in ("CP", "D", "SE", "SI", "Q"):
        assert p in r["pins"]


def test_topology_view_custom_rel_constr():
    # explicit pins must flow through (no hard-coded D)
    r = topology_view(SDFX, "SDFX_LPE_PLACEHOLDER", rel_pin="CP", rel_dir="rise",
                      constr_pin="D", constr_dir="fall", when="notSE_SI")
    assert r["status"] in ("OK", "NA")


def test_audit_accepts_structured_arc_dicts(tmp_path):
    croot = _collateral_root(tmp_path)
    arc = {"arc_id": "hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION",
           "cell": "DFFQ1", "arc_type": "hold", "rel_pin": "CP",
           "rel_dir": "rise", "probe_pin": "Q", "when": "NO_CONDITION"}
    out = audit_arcs(node=_NODE, lib_type=_LIB, corner=_CORNER,
                     arc_ids=[arc], collateral_root=croot)
    assert out["rows"], "structured arc should produce a row"
    assert out["rows"][0]["cell"] == "DFFQ1"
    # must NOT be the unparseable-arc error path
    assert out["rows"][0]["notes"] != "unparseable arc id"


class TestCombinationalSensitizationView:
    def test_exposes_region_sig_and_match_verdict(self):
        # AIOI21 B->ZN with correct collateral -when -> MATCH; region + SIG present.
        r = combinational_sensitization_view(
            AIOI21, "AIOI21", rel_pin="B", output="ZN",
            when_strings=["A1&!A2", "!A1&A2", "!A1&!A2"])
        assert r["status"] == "OK"
        assert r["rel_pin"] == "B" and r["output"] == "ZN"
        sens = {s["label"] for s in r["sensitizing"]}
        assert sens == {"!A1&!A2", "!A1&A2", "A1&!A2"}
        assert {b["label"] for b in r["blocked"]} == {"A1&A2"}
        # every sensitizing state carries a SIG (partition hook, demoable)
        assert all(len(s["sig"]) > 0 for s in r["sensitizing"])
        assert r["needs_split"] is True
        assert r["verdict"]["status"] == "MATCH"

    def test_catch_divergence_names_states(self):
        # kit asserts timing on the BLOCKED state A1&A2 -> DIVERGENCE in the JSON.
        r = combinational_sensitization_view(
            AIOI21, "AIOI21", rel_pin="B", output="ZN",
            when_strings=["A1&!A2", "!A1&A2", "A1&A2"])
        assert r["verdict"]["status"] == "DIVERGENCE"
        assert "A1&A2" in r["verdict"]["extra"]
        assert "!A1&!A2" in r["verdict"]["missing"]

    def test_unsupported_when_not_divergence(self):
        r = combinational_sensitization_view(
            AIOI21, "AIOI21", rel_pin="B", output="ZN",
            when_strings=["!A1 | !A2"])
        assert r["verdict"]["status"] == "UNSUPPORTED-WHEN"

    def test_missing_netlist_returns_error_not_raise(self):
        r = combinational_sensitization_view(
            "/no/such/file.subckt", "AIOI21", rel_pin="B", output="ZN")
        assert r["status"] == "ERROR"
