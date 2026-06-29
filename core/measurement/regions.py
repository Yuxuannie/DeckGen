"""Classify each template line into collateral / recipe / bias and extract the
recipe region (the fixed methodology body the grammar owns). Content-based, not
position-based, so interleaved sections (recipe options at top, collateral in the
middle, recipe nodeset/meas at the bottom) classify correctly. stdlib, ASCII."""
from __future__ import annotations

import os as _os

# Collateral: supplied by the flow / corner; filled per (cell, corner).
# .param entries carry a trailing space so they match only at a word boundary
# (e.g. ".param cl " matches ".param cl = '...'" but NOT ".param clk_period").
_COLLATERAL_PREFIXES = (
    ".inc", ".temp",
    ".param vdd_value ", ".param vss_value ", ".param cl ",
    ".param rel_pin_slew ", ".param constr_pin_slew ",
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


def partition(text: str) -> dict:
    """Partition all lines of *text* into classification buckets.
    Returns {"recipe": [...], "collateral": [...], "bias": [...], "blank": [...]}.
    Every source line appears in exactly one bucket (raw, not rstripped).
    Used as a regression guard: sum(len(v) for v in result.values()) must equal
    len(text.splitlines()), catching any future classify_line divergence."""
    buckets: dict = {"recipe": [], "collateral": [], "bias": [], "blank": []}
    for raw in text.splitlines():
        buckets[classify_line(raw)].append(raw)
    return buckets


_DIRS = ("rise", "fall")


def parse_template_key(path: str) -> dict:
    """Derive (arc_type, rel_dir, other_dir, cluster_tag) from a template path.
    Two filename schemes: delay = template_common_inpin_<rel>_delay_<probe>.sp;
    mpw = template__<tag tokens>__<d1>__<d2>__<N>.sp (tag may be multi-token).
    Unknown/odd names degrade to cluster_tag=<stem>, dirs='' (round-trip still
    keys them uniquely by provenance)."""
    arc_type = _os.path.basename(_os.path.dirname(path))
    stem = _os.path.basename(path)[:-3] if path.endswith(".sp") else _os.path.basename(path)

    if arc_type == "delay" and stem.startswith("template_common_inpin_") and "_delay_" in stem:
        body = stem[len("template_"):]                 # common_inpin_rise_delay_fall
        head, probe = body.rsplit("_", 1)              # common_inpin_rise_delay | fall
        head2, _delay = head.rsplit("_delay", 1) if "_delay" in head else (head, "")
        tag, rel = head2.rsplit("_", 1)                # common_inpin | rise
        return {"arc_type": arc_type, "rel_dir": rel, "other_dir": probe,
                "cluster_tag": tag}

    if stem.startswith("template__"):
        toks = [t for t in stem[len("template__"):].split("__") if t != ""]
        # drop a trailing numeric index token if present
        if toks and toks[-1].isdigit():
            toks = toks[:-1]
        rel = other = ""
        if len(toks) >= 2 and toks[-1] in _DIRS and toks[-2] in _DIRS:
            rel, other = toks[-2], toks[-1]
            toks = toks[:-2]
        tag = ".".join(toks) if toks else stem
        return {"arc_type": arc_type, "rel_dir": rel, "other_dir": other,
                "cluster_tag": tag}

    return {"arc_type": arc_type, "rel_dir": "", "other_dir": "", "cluster_tag": stem}
