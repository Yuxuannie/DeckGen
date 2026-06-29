import os
import pytest
from core.measurement.mine import mine
from core.measurement.emit import select_entry, SelectionError

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
