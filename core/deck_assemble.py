"""deck_assemble.py -- assemble a runnable SPICE deck for an arc from collateral
+ the measurement grammar + an engine-derived side-pin bias. No per-cell
template file at runtime: the grammar entry carries its family template's FULL
text verbatim as frame_text (mined by core/measurement/mine.py), and assembly
fills that frame exactly like the golden flow fills a template -- the same
deck_builder substitution map and the same injection points -- so a deck whose
engine-derived bias agrees with the kit -when is BYTE-IDENTICAL to the golden
template-substitution deck. stdlib only, ASCII only, simulator-free."""
from __future__ import annotations

import re

from engine.whencond import parse_when_conjunction

# Same token shape deck_builder._substitute_vars resolves; used only to NAME
# the placeholders a line consumed in the audit record.
_PLACEHOLDER_RE = re.compile(r"\$([A-Z_][A-Z_0-9]*)")


def _vline(pin, value):
    rail = "vdd_value" if value else "vss_value"
    return "V%s %s 0 '%s'" % (pin, pin, rail)


def _kit_pin_order(kit_when, side_bias):
    """Side pins named by the kit -when, in the WHEN's own token order -- that
    is the order build_deck injects them under '* Pin definitions', so the
    order must match for byte-parity. Pins the engine did not bias are
    skipped (nothing to tie)."""
    if not kit_when or kit_when in ("NO_CONDITION", "NONE"):
        return []
    out = []
    for tok in kit_when.split("&"):
        pin = tok.strip().lstrip("!")
        if pin and pin in side_bias and pin not in out:
            out.append(pin)
    return out


def fill_frame(frame_text, arc_info, side_bias, kit_when=None, audit=None):
    """Fill a grammar entry's frame (the family template's full text, verbatim)
    the way the golden flow fills a template: deck_builder's substitution map
    for $VARS, load caps injected after '* Output Load', and engine V-sources
    for side pins -- kit-named pins after '* Pin definitions' (golden's
    injection point, WHEN token order), remaining engine-derived pins after
    '* Unspecified pins' (sorted; appended right after the kit pins when the
    frame has no Unspecified section -- some mpw frames do not). Engine values
    are the source of truth even for kit-named pins. .inc lines de-duplicate
    exactly like build_deck. Unknown $PLACEHOLDERS survive (they trip the
    no-unresolved-$ check downstream, never silently vanish).

    audit (optional dict) is the G0 explain layer: filled with a per-line
    origin record for EVERY output line (key "lines", 1-based "n" matching the
    deck), plus "dropped_inc" for lines the .inc dedup removed. It is written
    by the SAME pass that writes the deck, so it cannot drift from the deck.
    Passing audit never changes deck bytes."""
    from core.deck_builder import _build_substitution_map, _substitute_vars

    sub = None      # built on first $-line; frames without $ need no arc keys
    kit_pins = _kit_pin_order(kit_when, side_bias)
    extras = sorted(p for p in side_bias if p not in set(kit_pins))
    has_unspec = "* Unspecified pins" in frame_text

    out, seen_inc = [], set()
    alines = [] if audit is not None else None

    def push(line, src="frame", **meta):
        s = line.strip()
        if s.startswith(".inc "):
            if s in seen_inc:
                if audit is not None:
                    audit.setdefault("dropped_inc", []).append(s)
                return
            seen_inc.add(s)
        out.append(line)
        if alines is not None:
            rec = {"n": len(out), "src": src}
            rec.update(meta)
            if src in ("frame", "subst") and "rule" not in rec:
                # G1: per-line semantic rule + why from the decompiler
                # (cached per unique line; collateral/bias lines route via
                # regions.classify_line).
                from core.measurement.decompile import explain_frame_line
                rec.update(explain_frame_line(line))
            alines.append(rec)

    def push_bias(pin, section):
        why = ("kit -when names %s; engine-proven value ties it" % pin
               if section == "kit" else
               "engine-derived: kit leaves %s unspecified; P1 state pins it"
               % pin)
        push(_vline(pin, side_bias[pin]), src="engine",
             pin=pin, value=side_bias[pin], why=why)

    for line in frame_text.split("\n"):
        if "* Pin definitions" in line:
            push(line)
            for p in kit_pins:
                push_bias(p, "kit")
            if not has_unspec:
                for p in extras:
                    push_bias(p, "extra")
            continue
        if "* Unspecified pins" in line:
            push(line)
            for p in extras:
                push_bias(p, "extra")
            continue
        if "* Output Load" in line:
            push(line)
            pins = (arc_info.get("OUTPUT_PINS") or
                    arc_info.get("PROBE_PIN_1", "")).split()
            for pin in pins:
                push("C%s %s 0 'cl'" % (pin, pin), src="load", pin=pin,
                     why="load cap on output %s; cl from collateral "
                         "(template.tcl index_2)" % pin)
            continue
        if "$" in line:
            if sub is None:
                sub = _build_substitution_map(arc_info, None, None, None)
            phs = [m for m in _PLACEHOLDER_RE.findall(line) if m in sub]
            # Classify by the FRAME line, not the substituted output:
            # substitution changes values, never the line's semantic shape
            # -- except $HEADER_INFO, which expands to arbitrary header
            # comments that only the frame line identifies.
            fmeta = {}
            if alines is not None:
                from core.measurement.decompile import explain_frame_line
                fmeta = explain_frame_line(line)
            # HEADER_INFO substitution embeds newlines; split so .inc dedup
            # and line accounting stay per-line.
            for piece in _substitute_vars(line, sub).split("\n"):
                push(piece, src="subst", placeholders=phs, **fmeta)
            continue
        push(line)
    if audit is not None:
        audit["lines"] = alines
    return "\n".join(out)


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
    _EXTEND = ("to support it, add that family's golden template to the "
               "corpus and re-mine: python -m core.measurement.mine mine "
               "<template_dir> -o config/measurement_grammar.json")
    if family == "hold":
        if depth == 1:
            tag = "CP.syncx.D"
        elif 2 <= depth <= 6:
            tag = "CP.sync%d.D" % depth
        else:
            raise SeqScope(
                "depth %d beyond mined hold corpus (syncx=1..sync6=6); "
                "nearest mined recipe is CP.sync6.D (depth 6) -- %s"
                % (depth, _EXTEND))
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
            raise SeqScope(
                "depth %d beyond mined mpw corpus (CPN=1, sync2..6); "
                "nearest mined recipe is sync6.CP (depth 6) -- %s"
                % (depth, _EXTEND))
        return tag, rel_dir, other
    raise SeqScope("unknown deck family %r (want hold|mpw); mined families "
                   "cover hold and mpw only -- %s" % (family, _EXTEND))


def _err(msg, **extra):
    r = {"status": "ERROR", "deck_text": None, "bias": {}, "chosen_when": "",
         "output": "", "out_dir": "", "kit_match": False, "error": msg}
    r.update(extra)
    return r


def _collateral_facts(arc_info):
    """The resolved collateral values the deck consumed, with their sources --
    the G0 'where did this number come from' block."""
    g = arc_info.get
    return {
        "netlist": {"value": g("NETLIST_PATH", ""),
                    "source": "manifest netlist dir"},
        "model_inc": {"value": g("INCLUDE_FILE", ""),
                      "source": "manifest Char *.inc"},
        "waveform_inc": {"value": g("WAVEFORM_FILE", ""),
                         "source": "manifest / std_wv convention"},
        "vdd": {"value": g("VDD_VALUE", ""), "source": "corner name voltage"},
        "temp": {"value": g("TEMPERATURE", ""),
                 "source": "corner name temperature"},
        "slew_index_1": {"value": g("INDEX_1_VALUE", ""),
                         "source": "template.tcl index_1[i1]"},
        "load_index_2": {"value": g("INDEX_2_VALUE", ""),
                         "source": "template.tcl index_2[i2]"},
        "output_load": {"value": g("OUTPUT_LOAD", ""),
                        "source": "template.tcl (constraint arcs)"},
        "max_slew": {"value": g("MAX_SLEW", ""),
                     "source": "template.tcl / config"},
    }


def _engine_ctx(engine_cache, cell, netlist_src):
    """Parse + CCC-decompose the cell netlist, reusing a per-cell cached result
    when engine_cache (a dict the caller owns for one run) is provided. The
    engine treats graph/CCC read-only -- proven: classify+derive give identical
    results and leave both objects byte-unchanged across reuse -- so the many
    arcs of one cell share a single parse instead of re-parsing per arc. The
    cache is per-run because a cell name maps to one netlist within a run."""
    from engine.stages import stage0_parse, stage1_ccc
    if engine_cache is not None and cell in engine_cache:
        return engine_cache[cell]
    graph = stage0_parse.parse(netlist_src, cell)
    ccc = stage1_ccc.decompose(graph)
    # "sens" caches stage2 derivations per arc identity: a full-grid run
    # visits the SAME arc once per (i1, i2) table point, and the derivation
    # depends only on the topology + arc pins -- never on the point.
    ctx = {"graph": graph, "ccc": ccc, "seq": None, "sens": {}}
    if engine_cache is not None:
        engine_cache[cell] = ctx
    return ctx


def assemble_combinational(arc_info: dict, netlist_src: str, grammar: dict,
                           engine_cache=None) -> dict:
    """Assemble a combinational delay/slew deck. Never raises: a bad arc is a named
    ERROR row (feeds B4's coverage report). engine_cache (optional per-run dict)
    lets sibling arcs of the same cell reuse one parse -- see _engine_ctx."""
    from engine.stages import stage2_sensitize
    from engine.types import Arc
    from core.measurement.emit import select_entry, SelectionError

    cell = arc_info.get("CELL_NAME", "")
    rel = arc_info.get("REL_PIN", "")
    probe = arc_info.get("PROBE_PIN_1", "")
    try:
        ctx = _engine_ctx(engine_cache, cell, netlist_src)
        graph, ccc = ctx["graph"], ctx["ccc"]
    except Exception as e:
        return _err("netlist parse failed: %s" % e)

    try:
        arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel, rel_dir="rise",
                  constr_pin=probe, constr_dir="rise", when="NO_CONDITION",
                  measurement="", raw={"probe_pin": probe})

        if not stage2_sensitize.is_combinational_arc(graph, arc, ccc):
            return _err("arc CCC has a state node -- sequential, handled by B2/B3")

        skey = ("comb", rel, probe)
        res = ctx["sens"].get(skey)
        if res is None:
            res = stage2_sensitize.derive_combinational(graph, arc, ccc)
            ctx["sens"][skey] = res
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
        if "frame_text" not in entry:
            return _err("grammar entry for delay/%s/%s has no frame_text -- "
                        "re-mine the corpus (python -m core.measurement.mine "
                        "mine <dir>)" % (rel_dir, out_dir))

        audit = {}
        deck_text = fill_frame(entry["frame_text"], arc_info, cb["bias"],
                               arc_info.get("WHEN"), audit=audit)
        explain = {
            "selection": {
                "arc_class": "combinational",
                "grammar_key": dict(entry.get("key", {})),
                "provenance": list(entry.get("provenance", [])),
                "why": "engine derived %s->%s as a %s-input arc whose output "
                       "%ss; grammar entry keyed (delay, %s, %s)"
                       % (rel, res.output, rel_dir, out_dir, rel_dir, out_dir),
            },
            "engine": {
                "bias": dict(cb["bias"]),
                "chosen_state": cb["chosen_label"],
                "kit_when": arc_info.get("WHEN") or "NO_CONDITION",
                "kit_match": cb["kit_match"],
                "sensitizing_states": [s.label for s in res.sensitizing],
                "why": "side pins tied to the chosen P1 sensitizing state; "
                       "kit_match means the kit -when covers that state",
            },
            "collateral": _collateral_facts(arc_info),
            "audit": audit,
        }
        return {"status": "OK", "deck_text": deck_text,
                "bias": cb["bias"], "chosen_when": cb["chosen_label"],
                "output": res.output, "out_dir": out_dir,
                "kit_match": cb["kit_match"], "explain": explain,
                "error": None}
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


def assemble_sequential(arc_info: dict, netlist_src: str, grammar: dict,
                        engine_cache=None) -> dict:
    """Assemble a runnable sequential deck (hold or mpw family). Never raises: a
    bad/unsupported arc is a named ERROR row. Family from ARC_TYPE
    (hold -> CP.sync{N}.D; mpw|min_pulse_width -> sync{N}.CP/CPN); depth from the
    B2 structural class. engine_cache (optional per-run dict) lets sibling arcs
    of the same cell reuse one parse + classify -- see _engine_ctx."""
    from engine.stages import stage2_sensitize
    from engine.stages.stage1b_classify import classify, depth_of
    from engine.types import Arc
    from core.measurement.emit import select_entry, SelectionError

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
        ctx = _engine_ctx(engine_cache, cell, netlist_src)
        graph, ccc = ctx["graph"], ctx["ccc"]
    except Exception as e:
        return _err("netlist parse failed: %s" % e)

    try:
        seq = ctx["seq"]
        if seq is None:
            seq = classify(graph, cell)
            ctx["seq"] = seq
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
        skey = ("seq", rel, rel_dir, constr, constr_dir, at, arc.when, probe)
        sens = ctx["sens"].get(skey)
        if sens is None:
            sens = stage2_sensitize.derive(graph, arc, ccc)
            ctx["sens"][skey] = sens
        # P1 not proven -> side biases are None placeholders. Emitting anyway would
        # silently hard-tie every undetermined side pin to 0 (fill_frame maps
        # None -> vss_value). The combinational sibling gates on res.sensitizing
        # and stage3 filters None; do the same here rather than ship a deck with
        # unproven biases masquerading as logic 0.
        if not sens.proven:
            return _err("P1 not proven for %s: side-pin biases undetermined "
                        "(%s) -- refusing to emit a deck that would silently tie "
                        "them to 0" % (cell, sens.p1_obligation or "no obligation"))
        bias = {p: d.value for p, d in sens.side_biases.items()}

        try:
            entry = select_entry(grammar, arc_type="mpw", rel_dir=sel_rel,
                                 other_dir=sel_other, cluster_tag=tag)
        except SelectionError as e:
            return _err("no grammar entry for %s: %s" % (tag, e))
        if "frame_text" not in entry:
            return _err("grammar entry for %s has no frame_text -- re-mine the "
                        "corpus (python -m core.measurement.mine mine <dir>)"
                        % tag)

        if not arc_info.get("NETLIST_PINS"):
            arc_info = dict(arc_info)
            arc_info["NETLIST_PINS"] = _subckt_ports(netlist_src, cell)
        audit = {}
        deck_text = fill_frame(entry["frame_text"], arc_info, bias,
                               arc_info.get("WHEN"), audit=audit)
        explain = {
            "selection": {
                "arc_class": "sequential",
                "family": family, "cluster_tag": tag, "depth": depth,
                "verdict": seq.verdict,
                "grammar_key": dict(entry.get("key", {})),
                "provenance": list(entry.get("provenance", [])),
                "why": "structural classify: verdict=%s depth=%d -> recipe "
                       "cluster %s (%s family)"
                       % (seq.verdict, depth, tag, family),
            },
            "engine": {
                "bias": dict(bias),
                "kit_when": arc_info.get("WHEN") or "NO_CONDITION",
                "p1_proven": True,
                "why": "side-pin values from the proven P1 sensitization "
                       "obligation; deck refused earlier if P1 unproven",
            },
            "collateral": _collateral_facts(arc_info),
            "audit": audit,
        }
        return {"status": "OK", "deck_text": deck_text,
                "bias": bias, "verdict": seq.verdict, "depth": depth,
                "cluster_tag": tag, "family": family, "explain": explain,
                "error": None}
    except Exception as e:
        return _err("internal error during assembly: %s" % e)
