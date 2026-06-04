"""Graphviz .dot and SVG generation produce valid, non-empty output."""
import os
import xml.dom.minidom as minidom

from engine.config import ENGINE_DIR
from engine.draw import render_dot, render_svg
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine.types import Arc


def _setup():
    with open(os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt"),
              "r", encoding="ascii") as fh:
        g = stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell="SDFX_LPE_PLACEHOLDER", arc_type="hold", rel_pin="CP",
              rel_dir="rise", constr_pin="D", constr_dir="fall", when="notSE_SI",
              measurement="")
    sens = stage2_sensitize.derive(g, arc, ccc)
    return g, ccc, sens, arc


def test_dot_has_clusters_and_edges():
    g, ccc, sens, arc = _setup()
    dot = render_dot(g, ccc, sens, arc)
    assert dot.startswith("digraph")
    assert "master latch" in dot and "slave latch" in dot
    assert '"CP" -> "clkb"' in dot          # collapsed clock edge present


def test_svg_is_valid_xml():
    g, ccc, sens, arc = _setup()
    svg = render_svg(g, ccc, sens, arc)
    minidom.parseString(svg)                # raises if malformed
    assert "ml_a" in svg and "sl_a" in svg
