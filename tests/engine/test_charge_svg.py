"""
The charge-resolve SVG figure must be generated FROM the engine, not hardcoded:
every resolved voltage drawn on the card must equal resolve_checked(...).voltages
(so the slide can never drift from what engine.charge actually resolves).
"""
import xml.dom.minidom as minidom

from engine.charge import resolve_checked
from engine.charge_svg import card, render_svg

# the same canonical inputs charge_viz._demo() uses (kept in sync structurally)
CASES = {
    "scalar share": dict(
        free_groups=[["dyn", "tap"]], Cg={"dyn": 1.0e-15, "tap": 0.3e-15},
        Cc={}, entry_V={"dyn": 0.45, "tap": 0.0}, fixed_V={}),
    "coupling divider to fixed aggressor": dict(
        free_groups=[["f"]], Cg={"f": 1.0e-15}, Cc={("agg", "f"): 0.5e-15},
        entry_V={"f": 0.0}, fixed_V={"agg": 0.45}),
    "free-free split": dict(
        free_groups=[["f1"], ["f2"]], Cg={"f1": 1.0e-15, "f2": 1.0e-15},
        Cc={("f1", "f2"): 0.8e-15}, entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={}),
    "singular island -> X": dict(
        free_groups=[["f1"], ["f2"]], Cg={}, Cc={("f1", "f2"): 0.8e-15},
        entry_V={"f1": 0.45, "f2": 0.0}, fixed_V={}),
}


def _svg(kw):
    r = resolve_checked(**kw)
    return r, render_svg(r, kw["Cg"], kw["Cc"], kw["entry_V"], kw["fixed_V"], "t")


def test_render_svg_is_wellformed_for_every_case():
    for kw in CASES.values():
        _, svg = _svg(kw)
        assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
        minidom.parseString(svg)            # raises on malformed XML


def test_embedded_voltages_equal_resolve_checked():
    """Each resolved value printed on the card == resolve_checked().voltages,
    recomputed independently. A hardcoded number would not match."""
    for kw in CASES.values():
        r, svg = _svg(kw)
        fresh = resolve_checked(**kw).voltages           # independent recompute
        for net, v in fresh.items():
            token = "X" if v is None else f"{v:+.5f}"
            assert token in svg, f"{net}={token!r} missing from figure"


def test_singular_case_shows_X_not_a_number():
    kw = CASES["singular island -> X"]
    r, svg = _svg(kw)
    assert r.singular and all(v is None for v in r.voltages.values())
    assert "X" in svg
    # no fabricated rail-referenced number sneaks in for the island
    assert "+0.00000" not in svg and "+0.45000" not in svg


def test_card_returns_positive_height():
    kw = CASES["free-free split"]
    r = resolve_checked(**kw)
    g, h = card(r, kw["Cg"], kw["Cc"], kw["entry_V"], kw["fixed_V"], "t")
    assert "<g" or "<rect" in g
    assert h > 0
