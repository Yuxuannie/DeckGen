"""Tests for core.report (build_report + render_html)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.report import build_report, render_html


def _sample_rows():
    return [
        {
            "cell": "DFFQ1", "arc_type": "hold", "rel_pin": "CP",
            "rel_dir": "rise", "probe_pin": "Q", "constr_dir": "fall",
            "when": "!SE&SI", "corner": "ssgnp_0p450v_m40c",
            "template": "min_pulse_width/template__CP__rise__fall__1.sp",
            "status": "OK", "reason": "", "index_1": "3", "index_2": "2",
            "deck_path": "/out/DFFQ1.sp",
            "deck_text": ".title hold deck\n.end",
        },
        {
            "cell": "AOI22X1", "arc_type": "delay", "rel_pin": "A1",
            "rel_dir": "fall", "probe_pin": "ZN", "constr_dir": "rise",
            "when": "NO_CONDITION", "corner": "ttgnp_0p800v_25c",
            "template": "template__delay.sp",
            "status": "FAIL", "reason": "no template match for AOI22X1",
            "index_1": "1", "index_2": "1",
            "deck_path": "", "deck_text": "",
        },
        {
            "cell": "MUX2X1", "arc_type": "slew", "rel_pin": "S",
            "rel_dir": "rise", "probe_pin": "Z", "constr_dir": "rise",
            "when": "", "corner": "ffgnp_0p900v_125c",
            "template": "tmpl.sp",
            "status": "SKIP", "reason": "no LUT point for index pair",
            "index_1": "9", "index_2": "9",
            "deck_path": "", "deck_text": "",
        },
    ]


def _context():
    return {
        "node": "n7", "lib_type": "hpnpn3", "corner": "ssgnp_0p450v_m40c",
        "collateral_root": "/coll", "output_dir": "/out",
        "tool_version": "deckgen-2.0",
    }


def test_summary_counts():
    rep = build_report(_sample_rows(), _context())
    s = rep["summary"]
    assert s["total"] == 3
    assert s["ok"] == 1
    assert s["fail"] == 1
    assert s["skip"] == 1
    assert s["error"] == 0
    assert s["by_status"]["OK"] == 1
    assert s["by_status"]["FAIL"] == 1
    assert s["by_status"]["SKIP"] == 1


def test_failures_only_fail_or_error():
    rep = build_report(_sample_rows(), _context())
    assert len(rep["failures"]) == 1
    for r in rep["failures"]:
        assert r["status"] in ("FAIL", "ERROR")
    assert rep["failures"][0]["cell"] == "AOI22X1"


def test_by_arc_type_and_by_cell_present():
    rep = build_report(_sample_rows(), _context())
    s = rep["summary"]
    assert "hold" in s["by_arc_type"]
    assert "delay" in s["by_arc_type"]
    assert "slew" in s["by_arc_type"]
    assert s["by_arc_type"]["hold"]["ok"] == 1
    assert s["by_arc_type"]["delay"]["fail"] == 1
    assert s["by_cell"]["DFFQ1"]["ok"] == 1
    assert s["by_cell"]["AOI22X1"]["fail"] == 1


def test_warnings_capture_skip():
    rep = build_report(_sample_rows(), _context())
    assert any("MUX2X1" in w and "SKIP" in w for w in rep["warnings"])


def test_unmatched_templates():
    rep = build_report(_sample_rows(), _context())
    # The FAIL row mentions "template" in its reason.
    assert "template__delay.sp" in rep["unmatched_templates"]


def test_malformed_row_not_raised():
    rows = _sample_rows()
    rows.append({"cell": "ONLYCELL"})        # missing status + most keys
    rows.append("not a dict at all")          # entirely malformed
    rows.append({"status": "WEIRD", "cell": "X"})  # unknown status
    rep = build_report(rows, _context())
    s = rep["summary"]
    assert s["total"] == 6
    # The three malformed/unknown rows all become ERROR.
    assert s["error"] == 3
    # Each appears in failures (ERROR counts as actionable).
    assert len([r for r in rep["failures"] if r["status"] == "ERROR"]) == 3
    # They carry a reason.
    for r in rep["failures"]:
        if r["status"] == "ERROR":
            assert r["reason"]


def test_empty_rows():
    rep = build_report([], {})
    assert rep["summary"]["total"] == 0
    assert rep["failures"] == []
    html = render_html(rep)
    assert html.startswith("<!")
    assert html.rstrip().endswith("</html>")


def test_render_html_structure():
    rep = build_report(_sample_rows(), _context())
    html = render_html(rep)
    assert html.startswith("<!")
    assert html.rstrip().endswith("</html>")
    assert "<style" in html
    assert "<script" in html
    assert ("Coverage" in html) or ("Summary" in html)
    # Every cell name appears.
    for cell in ("DFFQ1", "AOI22X1", "MUX2X1"):
        assert cell in html
    # Failure reason text appears.
    assert "no template match for AOI22X1" in html
    # Expand/collapse controls.
    assert "Expand all" in html
    assert "Collapse all" in html


def test_render_html_escapes_deck_text():
    rows = _sample_rows()
    rows[0]["deck_text"] = "<script>alert(1)</script>"
    rep = build_report(rows, _context())
    html = render_html(rep)
    # The raw injection must NOT survive unescaped...
    assert "<script>alert(1)</script>" not in html
    # ...but its escaped form must be present.
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_html_ascii_only():
    rows = _sample_rows()
    # Inject a non-ASCII char into input WITHOUT putting one in this source file.
    rows[0]["cell"] = "CELL" + chr(0xE9) + "NON"  # latin small e with acute
    rows[0]["reason"] = "deg " + chr(0x00B0)
    rep = build_report(rows, _context())
    html = render_html(rep)
    encoded = html.encode("ascii", "strict")  # raises if any byte > 127
    assert all(b <= 127 for b in encoded)
