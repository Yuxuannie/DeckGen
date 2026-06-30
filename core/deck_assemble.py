"""deck_assemble.py -- assemble a runnable SPICE deck for a COMBINATIONAL delay/
slew arc from collateral + the Phase-A measurement recipe + an engine-derived
side-pin bias. No per-cell template. stdlib only, ASCII only, simulator-free.

Sequential arcs are out of scope here (B2/B3): they are detected and returned as a
named ERROR, never assembled."""
from __future__ import annotations


def engine_bias_section(side_bias: dict) -> list:
    """Voltage sources tying each non-toggling input to a rail at its derived value.
    side_bias: {pin: 0|1}. 1 -> vdd_value, 0 -> vss_value. Sorted for determinism."""
    lines = ["* ===== ENGINE-DERIVED side-pin bias ====="]
    for pin in sorted(side_bias):
        rail = "vdd_value" if side_bias[pin] else "vss_value"
        lines.append("V%s %s 0 '%s'" % (pin, pin, rail))
    return lines


def collateral_section(arc_info: dict) -> list:
    """Collateral lines with REAL values (Phase-A 'collateral' class). Order mirrors
    the golden template: waveform/model/netlist .inc, corner, slew/load, rails."""
    g = lambda k: arc_info.get(k, "")
    return [
        "* ===== COLLATERAL (resolved from manifest) =====",
        "* Waveform",
        ".inc '%s'" % g("WAVEFORM_FILE"),
        "* Model include file",
        ".inc '%s'" % g("INCLUDE_FILE"),
        "* Netlist path",
        ".inc '%s'" % g("NETLIST_PATH"),
        "* Library information",
        ".param vdd_value = '%s'" % g("VDD_VALUE"),
        ".param vss_value = 0",
        ".temp %s" % g("TEMPERATURE"),
        "* Slew and load information",
        ".param cl = '%s'" % g("INDEX_2_VALUE"),
        ".param rel_pin_slew = '%s'" % g("INDEX_1_VALUE"),
        "* Voltage",
        "VVDD VDD 0 'vdd_value'",
        "VVSS VSS 0 'vss_value'",
        "VVPP VPP 0 'vdd_value'",
        "VVBB VBB 0 'vss_value'",
    ]
