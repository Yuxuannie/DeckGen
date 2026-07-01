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
        # Subset match: a kit -when names only the gate-local partner(s), while an
        # engine sensitizing state pins EVERY side input. Require the kit-named pins
        # to agree; do not demand the kit enumerate all of them (that exactness made
        # kit_match always False for multi-input gates).
        for s in states:
            if all(s.assign.get(p) == v for p, v in want.items()):
                return {"bias": dict(s.assign), "chosen_label": s.label,
                        "kit_match": True}
    first = states[0]
    return {"bias": dict(first.assign), "chosen_label": first.label,
            "kit_match": False}


_DIR = {"R": "rise", "F": "fall", "rise": "rise", "fall": "fall"}


class SeqScope(Exception):
    """Raised when a sequential arc falls outside the mined recipe corpus
    (depth range or family). Caught by assemble_sequential -> named ERROR."""


def _seq_cluster_tag(family, depth, rel_dir):
    """Map a structural (family, depth) to the grammar cluster-tag and the
    rise/fall variant to select. hold -> CP.sync{N}.D (depth-1 = CP.syncx.D,
    fall->rise only); mpw -> CPN (depth 1) / sync{N}.CP (2..6), variant follows
    the arc's rel_dir. Corpus depth ceiling is 6. Never returns silently on a
    miss -- raises SeqScope with a reason."""
    if family == "hold":
        if depth == 1:
            tag = "CP.syncx.D"
        elif 2 <= depth <= 6:
            tag = "CP.sync%d.D" % depth
        else:
            raise SeqScope("depth %d beyond mined hold corpus (syncx=1..sync6=6)"
                           % depth)
        return tag, "fall", "rise"
    if family == "mpw":
        other = {"rise": "fall", "fall": "rise"}.get(rel_dir)
        if other is None:
            raise SeqScope("mpw needs rel_dir rise|fall, got %r" % rel_dir)
        if depth == 1:
            tag = "CPN"
        elif 2 <= depth <= 6:
            tag = "sync%d.CP" % depth
        else:
            raise SeqScope("depth %d beyond mined mpw corpus (CPN=1, sync2..6)"
                           % depth)
        return tag, rel_dir, other
    raise SeqScope("unknown deck family %r (want hold|mpw)" % family)


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
        # chosen.out_dir is the output edge WHEN THE REL PIN RISES. When the arc's rel
        # pin actually falls, the real output edge is the opposite, so flip it before
        # picking the grammar 'other_dir' variant -- otherwise fall-input arcs measure
        # the wrong output transition.
        chosen = next(s for s in res.sensitizing if s.label == cb["chosen_label"])
        out_dir_rise = _DIR.get(chosen.out_dir or "rise", "rise")
        out_dir = out_dir_rise if rel_dir == "rise" else \
            {"rise": "fall", "fall": "rise"}[out_dir_rise]
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
            + recipe   # emit()'s recipe already ends with .end -- do not re-append
        )
        return {"status": "OK", "deck_text": "\n".join(deck_lines) + "\n",
                "bias": cb["bias"], "chosen_when": cb["chosen_label"],
                "output": res.output, "out_dir": out_dir,
                "kit_match": cb["kit_match"], "error": None}
    except Exception as e:
        return _err("internal error during assembly: %s" % e)


def _subckt_ports(netlist_src, cell):
    """Port order from the `.subckt <cell> <p1> <p2> ...` header, for the X1
    instance line. Empty string if not found (assembly then reports it)."""
    for line in netlist_src.splitlines():
        toks = line.split()
        if len(toks) >= 2 and toks[0].lower() in (".subckt", ".subckt:") \
                and toks[1] == cell:
            return " ".join(toks[2:])
    return ""


def assemble_sequential(arc_info: dict, netlist_src: str, grammar: dict) -> dict:
    """Assemble a runnable sequential deck (hold or mpw family). Never raises: a
    bad/unsupported arc is a named ERROR row. Family from ARC_TYPE
    (hold -> CP.sync{N}.D; mpw|min_pulse_width -> sync{N}.CP/CPN); depth from the
    B2 structural class."""
    from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
    from engine.stages.stage1b_classify import classify, depth_of
    from engine.types import Arc
    from core.measurement.emit import select_entry, emit, SelectionError

    cell = arc_info.get("CELL_NAME", "")
    rel = arc_info.get("REL_PIN", "CP")
    constr = arc_info.get("CONSTR_PIN", "D")
    probe = arc_info.get("PROBE_PIN_1", "Q")
    rel_dir = _DIR.get(arc_info.get("REL_PIN_DIR", "fall"), "fall")
    constr_dir = _DIR.get(arc_info.get("CONSTR_PIN_DIR", "fall"), "fall")

    at = (arc_info.get("ARC_TYPE") or "").lower()
    if at in ("hold", "setup"):
        family = "hold"
    elif at in ("mpw", "min_pulse_width"):
        family = "mpw"
    else:
        return _err("unsupported ARC_TYPE %r for sequential emitter "
                    "(want hold|mpw)" % at)

    try:
        graph = stage0_parse.parse(netlist_src, cell)
        ccc = stage1_ccc.decompose(graph)
    except Exception as e:
        return _err("netlist parse failed: %s" % e)

    try:
        seq = classify(graph, cell)
        if seq.verdict in ("combinational", "recognized_unsupported"):
            return _err("not an assemblable sequential arc: verdict=%s (%s)"
                        % (seq.verdict, seq.reason or "no storage core"))
        if seq.verdict == "latch":
            return _err("latch not yet supported by the sequential emitter "
                        "(transparent; distinct methodology) -- %s"
                        % (seq.reason or "verdict=latch"))
        depth = depth_of(seq)
        try:
            tag, sel_rel, sel_other = _seq_cluster_tag(family, depth, rel_dir)
        except SeqScope as e:
            return _err("out of recipe corpus: %s" % e)

        arc = Arc(cell=cell, arc_type=at, rel_pin=rel, rel_dir=rel_dir,
                  constr_pin=constr, constr_dir=constr_dir,
                  when=arc_info.get("WHEN", "NO_CONDITION"),
                  measurement="", raw={"probe_pin": probe})
        sens = stage2_sensitize.derive(graph, arc, ccc)
        bias = {p: d.value for p, d in sens.side_biases.items()}

        try:
            entry = select_entry(grammar, arc_type="mpw", rel_dir=sel_rel,
                                 other_dir=sel_other, cluster_tag=tag)
        except SelectionError as e:
            return _err("no grammar entry for %s: %s" % (tag, e))

        header = arc_info.get("HEADER_INFO") or "%s %s %s->%s depth=%d" % (
            cell, at, rel, probe, depth)
        recipe = [l.replace("$HEADER_INFO", header)
                  for l in emit(entry, arc_info, fill_values=True)]

        pins = arc_info.get("NETLIST_PINS") or _subckt_ports(netlist_src, cell)
        deck_lines = (
            collateral_section(arc_info)
            + ["* ===== INSTANCE =====", "X1 %s %s" % (pins, cell)]
            + engine_bias_section(bias)
            + recipe
        )
        return {"status": "OK", "deck_text": "\n".join(deck_lines) + "\n",
                "bias": bias, "verdict": seq.verdict, "depth": depth,
                "cluster_tag": tag, "family": family, "error": None}
    except Exception as e:
        return _err("internal error during assembly: %s" % e)
