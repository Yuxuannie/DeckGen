import os
import pytest
from core.measurement.mine import mine
from core.measurement.emit import select_entry, SelectionError, emit

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _grammar():
    return mine(os.path.join(_REPO, "templates/N2P_v1.0/mpw"))


def test_select_by_tag_and_dirs():
    e = select_entry(_grammar(), arc_type="mpw", rel_dir="fall",
                     other_dir="rise", cluster_tag="AO2")
    assert "template__AO2__fall__rise__1.sp" in e["provenance"]


def test_select_no_match_raises_with_tried_info():
    with pytest.raises(SelectionError) as ei:
        select_entry(_grammar(), arc_type="mpw", rel_dir="rise",
                     other_dir="rise", cluster_tag="NOPE")
    msg = str(ei.value)
    assert "NOPE" in msg and "tried" in msg.lower()


def test_emit_fills_arc_identity_only_by_default():
    e = select_entry(_grammar(), arc_type="mpw", rel_dir="fall",
                     other_dir="rise", cluster_tag="CP.syncx.D")
    arc_info = {"REL_PIN": "CP", "CONSTR_PIN": "D", "PROBE_PIN_1": "Q"}
    lines = emit(e, arc_info)
    text = "\n".join(lines)
    assert "v(CP)" in text and "$REL_PIN" not in text
    assert "$VDD_VALUE" in text or "vdd_value" in text   # corner left for deck_builder
    assert "$MAX_SLEW" in text   # slew/load placeholders left for deck_builder


def test_emit_fill_values_resolves_corner():
    e = select_entry(_grammar(), arc_type="mpw", rel_dir="fall",
                     other_dir="rise", cluster_tag="CP.syncx.D")
    arc_info = {"REL_PIN": "CP", "CONSTR_PIN": "D", "PROBE_PIN_1": "Q",
                "VDD_VALUE": "0.45", "INDEX_1_VALUE": "1n", "INDEX_2_VALUE": "2f",
                "MAX_SLEW": "0.1u", "OUTPUT_LOAD": "0.5f", "TEMPERATURE": "-40"}
    text = "\n".join(emit(e, arc_info, fill_values=True))
    assert "$INDEX_1_VALUE" not in text and "$PUSHOUT_PER" not in text
    assert "$MAX_SLEW" not in text   # fill_values resolved the recipe-region value placeholder
