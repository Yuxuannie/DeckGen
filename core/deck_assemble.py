"""deck_assemble.py -- assemble a runnable SPICE deck for a COMBINATIONAL delay/
slew arc from collateral + the Phase-A measurement recipe + an engine-derived
side-pin bias. No per-cell template. stdlib only, ASCII only, simulator-free.

Sequential arcs are out of scope here (B2/B3): they are detected and returned as a
named ERROR, never assembled."""
from __future__ import annotations

from engine.whencond import parse_when_conjunction


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


def choose_bias(sensitizing: list, kit_when):
    """Pick one sensitizing state's side-pin assignment. Prefer the state matching
    the kit -when conjunction; else the first by sorted label. Engine is source of
    truth -- a non-matching kit yields kit_match=False, not an override."""
    states = sorted(sensitizing, key=lambda s: s.label)
    want = None
    if kit_when and kit_when not in ("NO_CONDITION", "", "NONE"):
        want = parse_when_conjunction(kit_when)        # None if OR/contradiction
    if want is not None:
        for s in states:
            if all(s.assign.get(p) == v for p, v in want.items()) and \
                    len(s.assign) == len(want):
                return {"bias": dict(s.assign), "chosen_label": s.label,
                        "kit_match": True}
    first = states[0]
    return {"bias": dict(first.assign), "chosen_label": first.label,
            "kit_match": False}


_DIR = {"R": "rise", "F": "fall", "rise": "rise", "fall": "fall"}


def _err(msg, **extra):
    r = {"status": "ERROR", "deck_text": None, "bias": {}, "chosen_when": "",
         "output": "", "out_dir": "", "kit_match": False, "error": msg}
    r.update(extra)
    return r


def assemble_combinational(arc_info: dict, netlist_src: str, grammar: dict) -> dict:
    """Assemble a combinational delay/slew deck. Never raises: a bad arc is a named
    ERROR row (feeds B4's coverage report)."""
    from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
    from engine.types import Arc
    from core.measurement.emit import select_entry, emit
    from core.measurement.emit import SelectionError

    cell = arc_info.get("CELL_NAME", "")
    rel = arc_info.get("REL_PIN", "")
    probe = arc_info.get("PROBE_PIN_1", "")
    try:
        graph = stage0_parse.parse(netlist_src, cell)
        ccc = stage1_ccc.decompose(graph)
    except Exception as e:
        return _err("netlist parse failed: %s" % e)

    try:
        arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel, rel_dir="rise",
                  constr_pin=probe, constr_dir="rise", when="NO_CONDITION",
                  measurement="", raw={"probe_pin": probe})

        if not stage2_sensitize.is_combinational_arc(graph, arc, ccc):
            return _err("arc CCC has a state node -- sequential, handled by B2/B3")

        res = stage2_sensitize.derive_combinational(graph, arc, ccc)
        if not res.sensitizing:
            return _err("empty SENSITIZING: %s does not combinationally drive %s "
                        "(sequential/clock or wrong probe)" % (rel, res.output))

        cb = choose_bias(res.sensitizing, arc_info.get("WHEN"))

        rel_dir = _DIR.get(arc_info.get("REL_PIN_DIR", "rise"), "rise")
        # output edge for the chosen state -> grammar 'other_dir'
        chosen = next(s for s in res.sensitizing if s.label == cb["chosen_label"])
        out_dir = _DIR.get(chosen.out_dir or "rise", "rise")
        try:
            entry = select_entry(grammar, arc_type="delay", rel_dir=rel_dir,
                                 other_dir=out_dir)
        except SelectionError as e:
            return _err("no grammar entry: %s" % e)

        # $HEADER_INFO is a provenance comment placeholder emit has no value key for.
        # Resolve ONLY it (targeted, never a blanket strip) so any other unresolved
        # placeholder still survives and trips the no-unresolved-$ check.
        header = arc_info.get("HEADER_INFO") or "%s %s %s->%s" % (
            cell, arc_info.get("ARC_TYPE", "delay"), rel, probe)
        recipe = [l.replace("$HEADER_INFO", header)
                  for l in emit(entry, arc_info, fill_values=True)]

        pins = arc_info.get("NETLIST_PINS", "")
        deck_lines = (
            collateral_section(arc_info)
            + ["* ===== INSTANCE =====", "X1 %s %s" % (pins, cell)]
            + engine_bias_section(cb["bias"])
            + recipe
            + [".end"]
        )
        return {"status": "OK", "deck_text": "\n".join(deck_lines) + "\n",
                "bias": cb["bias"], "chosen_when": cb["chosen_label"],
                "output": res.output, "out_dir": out_dir,
                "kit_match": cb["kit_match"], "error": None}
    except Exception as e:
        return _err("internal error during assembly: %s" % e)
