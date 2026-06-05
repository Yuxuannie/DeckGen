"""CSDF transient parsing + SVG waveform rendering."""
import xml.dom.minidom as minidom

from engine.wave import parse_csdf, render_svg

CSDF = """#H
'SIMULATOR' 'HSPICE'
#N 'v(cp)' 'v(d)' 'v(x1.ml_ax)'
#C 0.0 3
 0.0 0.0 0.0
#C 1.0e-9 3
 0.45 0.0 0.0
#C 2.0e-9 3
 0.45 0.45 0.37
"""


def test_parse_csdf():
    t, tr = parse_csdf(CSDF)
    assert t == [0.0, 1.0e-9, 2.0e-9]
    assert tr["v(cp)"] == [0.0, 0.45, 0.45]
    assert tr["v(x1.ml_ax)"][-1] == 0.37


def test_render_svg_valid():
    t, tr = parse_csdf(CSDF)
    svg = render_svg(t, tr, 0.45, [(2.0e-9, "settle")], "demo")
    minidom.parseString(svg)
    assert "v(cp)" in svg and "settle" in svg


def test_render_empty_is_safe():
    svg = render_svg([], {}, 0.45)
    minidom.parseString(svg)
