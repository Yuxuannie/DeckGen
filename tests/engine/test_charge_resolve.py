"""
Pillar 3 step 3: charge-conservation resolve (engine/charge.resolve / resolve_checked)
and its one-screen viz. These are the spec SS7 "degeneration-first" hand-calc gates:
every expected number is hand-derived in the comment so a reviewer can check it
WITHOUT SPICE. The built-in invariants (residual / hull bound / scalar cross-check)
are asserted to PASS on valid cases, and the singular island is asserted to emit X.

ALL voltages here are model predictions, UNVERIFIED against SPICE -- these tests
gate ARITHMETIC and invariant correctness, not physical fidelity.
"""
import pytest

from engine.charge import resolve, resolve_checked
from engine import charge_viz


# --- Case 1: scalar charge share (two grounded nodes merge through ON device) ---
# V = (Cg_dyn*0.45 + Cg_tap*0) / (Cg_dyn + Cg_tap) = 0.45e-15/1.3e-15 = 0.346153...
CASE1 = dict(
    free_groups=[["dyn", "tap"]],
    Cg={"dyn": 1.0e-15, "tap": 0.3e-15}, Cc={},
    entry_V={"dyn": 0.45, "tap": 0.0}, fixed_V={},
)


def test_scalar_share_value():
    v = resolve(**CASE1)
    assert v["dyn"] == pytest.approx(0.45e-15 / 1.3e-15)
    assert v["tap"] == pytest.approx(v["dyn"])      # merged -> equal


def test_scalar_share_derivation_and_invariants():
    r = resolve_checked(**CASE1)
    assert r.ok
    assert "charge-share scalar" in r.derivations["dyn"].reason
    assert any(c.startswith("scalar cross-check") and c.endswith("PASS") for c in r.checks)
    assert any(c.startswith("hull bound") and c.endswith("PASS") for c in r.checks)


# --- Case 2: coupling divider bump to a FIXED aggressor (spec 2.5) ---
# V_f = Cc*Vagg/(Cg+Cc) = 0.5e-15*0.45/1.5e-15 = 0.15
CASE2 = dict(
    free_groups=[["f"]],
    Cg={"f": 1.0e-15}, Cc={("agg", "f"): 0.5e-15},
    entry_V={"f": 0.0}, fixed_V={"agg": 0.45},
)


def test_coupling_divider_bump():
    v = resolve(**CASE2)
    assert v["f"] == pytest.approx(0.15)


# --- Case 3: free-free coupling -> distinct voltages, NOT the average ---
# A=[[1.8,-0.8],[-0.8,1.8]]e-15, b=[0.45,0]e-15 -> f1=0.81/2.6=0.311538, f2=0.36/2.6=0.138461
CASE3 = dict(
    free_groups=[["f1"], ["f2"]],
    Cg={"f1": 1.0e-15, "f2": 1.0e-15}, Cc={("f1", "f2"): 0.8e-15},
    entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={},
)


def test_free_free_split_not_average():
    v = resolve(**CASE3)
    assert v["f1"] == pytest.approx(0.81 / 2.6)     # 0.311538...
    assert v["f2"] == pytest.approx(0.36 / 2.6)     # 0.138461...
    # the naive average would be 0.225; the split must differ from it
    assert abs(v["f1"] - 0.225) > 1e-3


def test_free_free_invariants_and_matrix_derivation():
    r = resolve_checked(**CASE3)
    assert r.ok
    assert "coupled charge balance" in r.derivations["f1"].reason
    assert any(c.startswith("residual") and c.endswith("PASS") for c in r.checks)
    assert any(c.startswith("hull bound") and c.endswith("PASS") for c in r.checks)


# --- Case 4: degenerate isolated coupling island -> X, never a number ---
CASE4 = dict(
    free_groups=[["f1"], ["f2"]],
    Cg={}, Cc={("f1", "f2"): 0.8e-15},
    entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={},
)


def test_singular_island_emits_X():
    v = resolve(**CASE4)
    assert v["f1"] is None and v["f2"] is None


def test_singular_resolve_checked_flags_review():
    r = resolve_checked(**CASE4)
    assert r.singular
    assert not r.ok
    assert r.voltages["f1"] is None
    assert "undetermined" in r.derivations["f1"].reason
    assert any("singular" in c and c.endswith("PASS") for c in r.checks)  # X-by-design


def test_resolve_deterministic():
    assert resolve(**CASE3) == resolve(**CASE3)


# --- viz: the one-screen report ---
def test_viz_renders_resolved_values_and_pass():
    r = resolve_checked(**CASE3)
    txt = charge_viz.render(r, CASE3["Cg"], CASE3["Cc"],
                            CASE3["entry_V"], CASE3["fixed_V"], title="free-free split")
    assert "CHARGE RESOLVE -- free-free split" in txt
    assert "+0.31154" in txt and "+0.13846" in txt
    assert "VERDICT: OK" in txt
    assert "PASS" in txt


def test_viz_singular_shows_X_and_review():
    r = resolve_checked(**CASE4)
    txt = charge_viz.render(r, CASE4["Cg"], CASE4["Cc"],
                            CASE4["entry_V"], CASE4["fixed_V"], title="island")
    assert "X" in txt
    assert "REVIEW" in txt


def test_viz_is_ascii():
    r = resolve_checked(**CASE2)
    txt = charge_viz.render(r, CASE2["Cg"], CASE2["Cc"],
                            CASE2["entry_V"], CASE2["fixed_V"], title="divider")
    assert txt.isascii()
