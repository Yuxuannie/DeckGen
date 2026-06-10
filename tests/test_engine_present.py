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
