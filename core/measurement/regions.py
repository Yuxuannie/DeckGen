"""Classify each template line into collateral / recipe / bias and extract the
recipe region (the fixed methodology body the grammar owns). Content-based, not
position-based, so interleaved sections (recipe options at top, collateral in the
middle, recipe nodeset/meas at the bottom) classify correctly. stdlib, ASCII."""
from __future__ import annotations

# Collateral: supplied by the flow / corner; filled per (cell, corner).
_COLLATERAL_PREFIXES = (
    ".inc", ".temp",
    ".param vdd_value", ".param vss_value", ".param cl",
    ".param rel_pin_slew", ".param constr_pin_slew",
    "vvdd", "vvss", "vvpp", "vvbb",
    "x1 ",
)
# Section comments that head collateral blocks (kept out of the recipe region).
_COLLATERAL_COMMENTS = (
    "* waveform", "* model include", "* netlist path", "* library information",
    "* slew and load", "* voltage", "* output load", "* subckt definition",
)
# Comments marking where engine WHEN/side-pin biases go (Phase B owns these).
_BIAS_COMMENTS = ("* unspecified pins", "* pin definitions")


def classify_line(line: str) -> str:
    s = line.strip()
    if not s:
        return "blank"
    low = s.lower()
    if low in _BIAS_COMMENTS:
        return "bias"
    if low.startswith(_COLLATERAL_COMMENTS):
        return "collateral"
    if low.startswith(_COLLATERAL_PREFIXES):
        return "collateral"
    return "recipe"


def extract_recipe(text: str) -> list[str]:
    """Ordered recipe lines (the methodology body the grammar owns). Drops
    collateral, bias-section, and blank lines so two templates that differ only
    in collateral compare equal."""
    out = []
    for raw in text.splitlines():
        if classify_line(raw) == "recipe":
            out.append(raw.rstrip())
    return out
