"""core/engine_present.py -- GUI data layer over the v2 engine.
Spec: docs/superpowers/specs/2026-06-10-gui-all-features-showcase-design.md
"""
import os
import xml.dom.minidom as minidom

from core.engine_present import topology_view

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDFX = os.path.join(REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")


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
