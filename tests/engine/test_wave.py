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


# real PrimeSim CSDF: values begin on the #C line; many signals to filter down
REAL = """#H
SOURCE='PrimeSim HSPICE' VERSION='Y-2026.03'
TITLE='deck'
NODES=' 5'
#N 'V(cp)' 'V(d)' 'V(x1.ml_ax)' 'V(x1.sl_a)' 'i(vdd)'
#C 0.00000e+00 5  0.0 0.0 0.45 0.0 1e-9
#C 1.00000e-08 5  0.45 0.0 0.0 0.45 2e-9
"""


def test_parse_primesim_csdf_values_on_c_line():
    from engine.wave import select
    t, tr = parse_csdf(REAL)
    assert t == [0.0, 1.0e-8]
    assert tr["V(x1.ml_ax)"] == [0.45, 0.0]
    sel = select(tr, ["CP", "D", "x1.ml_ax", "x1.sl_a"])
    assert list(sel.keys()) == ["V(cp)", "V(d)", "V(x1.ml_ax)", "V(x1.sl_a)"]
    assert "i(vdd)" not in sel
