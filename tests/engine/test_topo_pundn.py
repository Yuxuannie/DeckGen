"""core/topo_pundn.py -- PUN/PDN series-parallel extraction + conducting set.

Asserts the engine recovers the textbook pull-network structure of each anchor
from the .subckt alone (the basis for the audit detail topology figure), and that
the conducting-device set under a state is correct (the per-state highlight).
"""
import os

import pytest

from engine.stages import stage0_parse
from core import topo_pundn as T


def _graph(cell):
    with open(os.path.join(os.path.dirname(__file__), "..", "..",
                           "engine", "fixtures", cell + "_RECON.subckt"),
              encoding="ascii") as fh:
        return stage0_parse.parse(fh.read(), cell)


def _block(graph, net):
    for b in T.pull_networks(graph):
        if b["net"] == net:
            return b
    raise AssertionError("no block for net %s" % net)


def _shape(sp):
    """(tag, child-tags-sorted) for order-insensitive structural assertions."""
    if not sp or sp[0] == "dev":
        return ("dev",)
    return (sp[0], tuple(sorted(c[0] for c in sp[1])))


class TestAOI22Structure:
    def test_pun_is_series_of_two_parallels(self):
        b = _block(_graph("AOI22"), "ZN")
        assert _shape(b["pun"]) == ("series", ("parallel", "parallel"))
        assert set(T.device_names(b["pun"])) == {"XPA1", "XPA2", "XPB1", "XPB2"}

    def test_pdn_is_parallel_of_two_series(self):
        b = _block(_graph("AOI22"), "ZN")
        assert _shape(b["pdn"]) == ("parallel", ("series", "series"))
        assert set(T.device_names(b["pdn"])) == {"XNA1", "XNA2", "XNB1", "XNB2"}


class TestOAI22IsDual:
    def test_oai22_swaps_series_parallel(self):
        b = _block(_graph("OAI22"), "ZN")
        assert _shape(b["pun"]) == ("parallel", ("series", "series"))
        assert _shape(b["pdn"]) == ("series", ("parallel", "parallel"))


class TestAIOI21MultiStage:
    def test_two_driven_nets_output_and_bbar(self):
        nets = {b["net"]: b for b in T.pull_networks(_graph("AIOI21"))}
        outs = [n for n, b in nets.items() if b["is_output"]]
        assert outs == ["ZN"]
        assert len(nets) == 2                       # ZN + the internal B-inverter

    def test_output_stage_is_aoi21_core(self):
        b = _block(_graph("AIOI21"), "ZN")
        # PUN: (A1 || A2) in series with the bbar PMOS
        assert _shape(b["pun"]) == ("series", ("dev", "parallel"))


class TestConducting:
    def test_aioi21_parallel_pmos_state(self):
        # !A1 & !A2, B rising: both stage-1 PMOS conduct (the fast parallel path)
        on = T.conducting(_graph("AIOI21"), {"A1": 0, "A2": 0, "B": 1})
        assert {"XPA1", "XPA2"}.issubset(on)        # parallel PMOS both on

    def test_aoi22_blocked_state_has_no_pdn_path(self):
        # A1=0 -> the A1-A2 series pulldown cannot conduct via A1
        on = T.conducting(_graph("AOI22"), {"A1": 0, "A2": 1, "B1": 0, "B2": 0})
        assert "XNA1" not in on                      # A1 nmos off


class TestTextHelpers:
    def test_device_names_and_text(self):
        b = _block(_graph("AOI22"), "ZN")
        assert "||" in T.sp_to_text(b["pun"])
        assert "-" in T.sp_to_text(b["pun"])


class TestRenderSvg:
    def test_valid_svg_with_on_highlight(self):
        import xml.dom.minidom as md
        g = _graph("AIOI21")
        blocks = T.pull_networks(g)
        on = T.conducting(g, {"A1": 0, "A2": 0, "B": 1})
        svg = T.render_svg(blocks, on=on, rel_pin="B", output="ZN")
        md.parseString(svg)                       # raises on malformed XML
        assert 'class="dev on"' in svg            # conducting devices highlighted
        assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
        for pin in ("A1", "A2", "B"):
            assert pin in svg

    def test_parallel_pmos_both_lit_vs_single(self):
        # the partition signal, made visible: B rising at !A1&!A2 lights BOTH
        # stage-1 PMOS (parallel, fast); at !A1&A2 only one of them lights.
        g = _graph("AIOI21")
        blocks = T.pull_networks(g)
        par = T.render_svg(blocks, on=T.conducting(g, {"A1": 0, "A2": 0, "B": 1}))
        single = T.render_svg(blocks, on=T.conducting(g, {"A1": 0, "A2": 1, "B": 1}))

        def lit(svg, dev):
            return ('class="dev on" data-dev="%s"' % dev) in svg
        assert lit(par, "XPA1") and lit(par, "XPA2")          # both PMOS lit
        assert [lit(single, d) for d in ("XPA1", "XPA2")].count(True) == 1
