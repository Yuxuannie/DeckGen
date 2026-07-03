"""Parse real arc identifiers (demo dir-name format), anchored on the cell name."""
from engine.arc_id import parse_arc_id

CELL = "SDFQSXG0MZD1BWP130HPNPN3P48CPD"


def test_d_hold_arc():
    r = parse_arc_id(f"hold_{CELL}_D_fall_CP_rise_notSE_SI_2-4", CELL)
    assert r["arc_type"] == "hold"
    assert (r["constr_pin"], r["constr_dir"]) == ("D", "fall")
    assert (r["rel_pin"], r["rel_dir"]) == ("CP", "rise")
    assert r["when"] == "notSE_SI"
    assert r["_idx"] == "2-4"


def test_se_hold_arc():
    r = parse_arc_id(f"hold_{CELL}_SE_rise_CP_rise_D_notSI_3-3", CELL)
    assert (r["constr_pin"], r["constr_dir"]) == ("SE", "rise")
    assert r["when"] == "D_notSI"
    assert r["_idx"] == "3-3"


def test_cell_mismatch_raises():
    try:
        parse_arc_id(f"hold_OTHERCELL_D_fall_CP_rise_notSE_SI_2-4", CELL)
    except ValueError:
        return
    assert False, "expected ValueError on cell mismatch"
