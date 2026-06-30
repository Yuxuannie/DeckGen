# tests/test_deck_assemble_check.py
import os
from core.deck_assemble import assemble_combinational
from core.deck_assemble_check import check_against_template
from core.measurement.mine import mine

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")
_TMPL = os.path.join(_REPO,
    "templates/N2P_v1.0/delay/template_common_inpin_rise_delay_rise.sp")


def _arc_info():
    return {"CELL_NAME": "AOI22", "ARC_TYPE": "delay", "REL_PIN": "A1",
            "REL_PIN_DIR": "rise", "PROBE_PIN_1": "ZN", "WHEN": "NO_CONDITION",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2n",
            "INDEX_2_VALUE": "0.5f", "MAX_SLEW": "0.1u",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22, "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}


def test_check_passes_for_assembled_deck():
    g = mine(os.path.join(_REPO, "templates/N2P_v1.0/delay"))
    r = assemble_combinational(_arc_info(), open(_AOI22).read(), g)
    assert r["status"] == "OK", r["error"]
    chk = check_against_template(r["deck_text"], _TMPL, r["bias"], "A1")
    assert chk["no_unresolved_placeholder"] is True, chk["detail"]
    assert chk["bias_structural_ok"] is True, chk["detail"]


def test_check_flags_unresolved_placeholder():
    chk = check_against_template("X1 a b\n.param vdd_value = '$VDD_VALUE'\n",
                                 _TMPL, {}, "A1")
    assert chk["no_unresolved_placeholder"] is False


def test_check_flags_toggling_pin_in_bias():
    bad = "VA1 A1 0 'vdd_value'\n"      # toggling pin must NOT be biased
    chk = check_against_template(bad, _TMPL, {}, "A1")
    assert chk["bias_structural_ok"] is False


def test_check_flags_missing_bias_source():
    # side pin A2 is expected biased exactly once but is absent from the deck
    chk = check_against_template("X1 a b\n", _TMPL, {"A2": 1}, "A1")
    assert chk["bias_structural_ok"] is False
