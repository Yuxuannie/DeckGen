"""engine_present.py -- data layer that turns a (cell, arc, options) request into
display-ready data for the showcase GUI (spec 2026-06-10).

Calls the v2 engine and the verify sidecar; returns JSON-serializable dicts plus
ready-to-embed SVG. NEVER raises to the caller: any engine/topology failure is
returned as {"status": "ERROR", ...} so the GUI renders a card, not a 500.
"""

import csv as _csv
import io
import os
import traceback

from engine.pipeline import run_pipeline_src
from engine.draw import render_svg


def _stage_log(result):
    return list(getattr(result, "stage_log", []) or [])


def _ccc_summary(result):
    roles = {}
    for sn in result.ccc.state_nodes:
        roles.setdefault(sn.role, []).append(sn.net)
    return {"components": len(result.ccc.components), "roles": roles}


def _subckt_pins(src, cell):
    import re
    for line in src.splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt"):
            toks = s.split()
            # .subckt CELL p1 p2 ... ; drop rails
            rails = {"VDD", "VSS", "VPP", "VBB", "0"}
            return [t for t in toks[2:] if t.upper() not in rails]
    return []


def topology_view(netlist_path, cell, corner=None, arc_type="hold",
                  rel_pin="CP", rel_dir="rise", constr_pin="D",
                  constr_dir="fall", when=None, force_bias=None):
    """Run S0-S2 on a real LPE netlist and return topology SVG + P1 verdict.

    when/force_bias are optional. Returns a dict that always has 'status'.
    """
    try:
        with open(netlist_path, "r") as fh:
            src = fh.read()
    except OSError as e:
        return {"status": "ERROR", "error": "cannot read netlist: %s" % e}

    pins = _subckt_pins(src, cell)

    record = {
        "cell": cell, "arc_type": arc_type,
        "rel_pin": rel_pin, "rel_dir": rel_dir,
        "constr_pin": constr_pin, "constr_dir": constr_dir,
        "when": (when or ""), "measurement": "",
    }
    if force_bias:
        record["force_bias"] = {k: int(v) for k, v in force_bias.items()}

    try:
        result = run_pipeline_src(record, src, "", "", "gui-topology")
    except Exception as e:
        tb = traceback.format_exc().splitlines()[-3:]
        return {"status": "ERROR", "error": str(e), "traceback_tail": tb}

    sens = result.sens
    if not result.ccc.state_nodes:
        status, p1_status = "NA", "NA"
    else:
        status, p1_status = "OK", ("PASS" if sens.proven else "FAIL")

    try:
        svg = render_svg(result.graph, result.ccc, sens, result.arc)
    except Exception as e:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60">'
               '<text x="10" y="30">topology render error: %s</text></svg>'
               % str(e).replace("<", "").replace(">", ""))

    p1_detail = (
        ["obligation : %s" % sens.p1_obligation]
        + ["bias %s = %s <= %s" % (pin, d.value, d.reason)
           for pin, d in sens.side_biases.items()]
        + ["arc-check  : %s" % sens.arc_check]
    )
    return {
        "status": status,
        "svg": svg,
        "p1": {"status": p1_status, "detail": p1_detail},
        "obligation": sens.p1_obligation,
        "stage_log": _stage_log(result),
        "ccc": _ccc_summary(result),
        "biases": {pin: {"value": d.value, "reason": d.reason}
                   for pin, d in sens.side_biases.items()},
        "arc_check": sens.arc_check,
        "pins": pins,
    }


def combinational_sensitization_view(netlist_path, cell, rel_pin,
                                     output=None, when_strings=None):
    """Run S0-S1 + combinational sensitization on an LPE/synthetic netlist and
    return demo-ready JSON for the GUI: the SENSITIZING / BLOCKED regions, the
    per-state conduction signature SIG, and the region-equivalence verdict
    (MATCH / DIVERGENCE + differing states / UNSUPPORTED-WHEN) against the
    collateral -when set. NEVER raises: failures come back as {"status":"ERROR"}.

    when_strings: the kit's -when conjunctions for this (rel_pin -> output) arc
    group (e.g. ["A1&!A2", "!A1&A2", "!A1&!A2"]); [] / None -> unconditional arc.
    """
    from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
    from engine.types import Arc

    try:
        with open(netlist_path, "r") as fh:
            src = fh.read()
    except OSError as e:
        return {"status": "ERROR", "error": "cannot read netlist: %s" % e}

    try:
        graph = stage0_parse.parse(src, cell)
        ccc = stage1_ccc.decompose(graph)
        arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel_pin,
                  rel_dir="rise", constr_pin=(output or ""), constr_dir="rise",
                  when="NO_CONDITION", measurement="",
                  raw={"probe_pin": output} if output else {})
        if not stage2_sensitize.is_combinational_arc(graph, arc, ccc):
            return {"status": "NA",
                    "error": "arc CCC has a state node -- not combinational"}
        res = stage2_sensitize.derive_combinational(graph, arc, ccc)
        verdict = stage2_sensitize.comb_verdict(res, list(when_strings or []))
    except Exception as e:
        tb = traceback.format_exc().splitlines()[-3:]
        return {"status": "ERROR", "error": str(e), "traceback_tail": tb}

    def _state(cs):
        return {"label": cs.label, "assign": dict(cs.assign),
                "out_dir": cs.out_dir, "sig": sorted(cs.sig)}

    return {
        "status": "OK",
        "rel_pin": res.rel_pin,
        "output": res.output,
        "side_pins": list(res.side_pins),
        "sensitizing": [_state(cs) for cs in res.sensitizing],
        "blocked": [_state(cs) for cs in res.blocked],
        "needs_split": res.needs_split,
        "verdict": {
            "status": verdict.status.value,
            "cover": verdict.cover,
            "missing": verdict.missing,
            "extra": verdict.extra,
            "detail": verdict.detail,
        },
        "notes": list(res.notes),
    }


def arc_detail_view(collateral_root, node, lib_type, corner, cell, rel_pin,
                    output, max_states=24):
    """Full per-arc detail for the audit detail pane: region table, truth table,
    boolean function, kit raw -when/-vector, and the PUN/PDN topology with a
    rendered SVG per relevant side-pin state (diff states first). NEVER raises.

    Engine derivation reads the .subckt only (Red Line A); template.tcl is read
    only for the kit-raw panel and the region cross-check.
    """
    from core.collateral import CollateralStore
    from core.resolver import NetlistResolver
    from core.parsers.template_tcl import parse_template_tcl_full
    from core.library_audit import _output_from_vector
    from core.arc_detail import arc_detail
    from core import topo_pundn

    try:
        store = CollateralStore(collateral_root, node, lib_type)
        template = store.get_template_tcl(corner)
        netlist_dir = store.get_netlist_dir(corner)
        npath, _pins = NetlistResolver(netlist_dir).resolve(cell)
    except Exception as e:
        return {"status": "ERROR", "error": "resolve: %s" % e}

    # kit raw + when set for this (cell, rel_pin, output)
    parsed = parse_template_tcl_full(template)
    cinfo = parsed.get("cells", {}).get(cell, {})
    pinlist = (cinfo.get("pinlist") or "").split()
    outs = cinfo.get("output_pins") or []
    whens, kit_raw = [], []
    for a in parsed.get("arcs", []):
        if a.get("cell") != cell or a.get("arc_type") != "combinational":
            continue
        if a.get("rel_pin") != rel_pin:
            continue
        a_out = _output_from_vector(pinlist, a.get("vector", ""), outs) or (
            outs[0] if outs else None)
        if a_out != output:
            continue
        whens.append(a.get("when", "NO_CONDITION"))
        kit_raw.append('define_arc -related_pin %s -when "%s" -vector {%s}'
                       % (rel_pin, a.get("when", "NO_CONDITION"), a.get("vector", "")))

    detail = arc_detail(npath, cell, rel_pin, output,
                        when_strings=whens, kit_raw=kit_raw)
    if detail.get("status") != "OK":
        return detail

    # render an SVG per state, differing states first, capped
    states = detail["topology"]["states"]
    states_sorted = sorted(states, key=lambda s: (s["diff"] == "", s["label"]))
    blocks = detail["topology"]["blocks"]
    rendered = []
    for s in states_sorted[:max_states]:
        rendered.append({
            "label": s["label"], "diff": s["diff"], "engine": s["engine"],
            "on": s["on"],
            "svg": topo_pundn.render_svg(blocks, on=set(s["on"]),
                                         rel_pin=rel_pin, output=output),
        })
    detail["topology"]["rendered"] = rendered
    detail["topology"]["truncated"] = len(states) > max_states
    return detail


CSV_COLUMNS = ["cell", "arc", "corner", "P1", "P2", "P3",
               "bias_match", "arc_check", "notes"]


def _arc_check_class(line):
    s = (line or "").upper()
    if "DISAGREE" in s:
        return "DISAGREE"
    if "AGREE" in s:
        return "AGREE"
    return "INDEPENDENT"


def audit_arcs(node, lib_type, corner, arc_ids, collateral_root="collateral"):
    """Resolve each arc through v1 and verify it (P1 real, P2 STUB, P3 static).
    Returns {"rows": [...], "summary": {...}}. Never raises per arc.
    """
    from core.parsers.arc import parse_arc_identifier
    from core.resolver import resolve_all_from_collateral
    from core.deck_builder import build_deck
    from core.verify_sidecar import (build_record, extract_meas_block,
                                     build_meas_context, derive_golden_biases,
                                     classify_bias_match)
    from engine.pipeline import run_pipeline_src
    from engine.stages.stage5_verify import p3_property

    rows = []
    for item in arc_ids:
        if isinstance(item, dict):
            parsed = {
                "cell_name": item.get("cell") or item.get("cell_name", ""),
                "arc_type": item.get("arc_type", ""),
                "rel_pin": item.get("rel_pin", ""),
                "rel_dir": item.get("rel_dir", "rise"),
                "probe_pin": item.get("probe_pin", ""),
                "when": item.get("when", "NO_CONDITION"),
            }
            arc_id = item.get("arc_id") or item.get("cell", "?")
        else:
            arc_id = item
            parsed = parse_arc_identifier(item)
            if parsed is None:
                rows.append({"cell": "?", "arc": arc_id, "corner": corner,
                             "P1": "ERROR", "P2": "ERROR", "P3": "ERROR",
                             "bias_match": "N/A", "arc_check": "INDEPENDENT",
                             "notes": "unparseable arc id"})
                continue
        try:
            info = resolve_all_from_collateral(
                cell_name=parsed["cell_name"], arc_type=parsed["arc_type"],
                rel_pin=parsed["rel_pin"], rel_dir=parsed["rel_dir"],
                constr_pin=parsed["rel_pin"], constr_dir=parsed["rel_dir"],
                probe_pin=parsed["probe_pin"], node=node, lib_type=lib_type,
                corner_name=corner, collateral_root=collateral_root)
            info = info[0] if isinstance(info, list) else info
            info.setdefault("CONSTR_PIN", info.get("REL_PIN", ""))
            lines = build_deck(info, slew=(info.get("INDEX_1_VALUE") or "0",
                                           info.get("INDEX_1_VALUE") or "0"),
                               load=info.get("OUTPUT_LOAD") or "0",
                               when=info.get("WHEN", "NO_CONDITION"),
                               max_slew=info.get("MAX_SLEW") or "0") \
                if info.get("TEMPLATE_DECK_PATH") else []
            record = build_record(info, {"arc_id": arc_id, "corner": corner})
            meas, _mnote = extract_meas_block(lines)
            record["measurement"] = meas
            res = run_pipeline_src(record, open(info["NETLIST_PATH"]).read()
                                   if info.get("NETLIST_PATH") else "",
                                   meas, "", "gui-audit")
            ctx = build_meas_context(lines, info) if lines else None
            res.verdict.p3 = p3_property(ctx, res.init, res.arc, sim_data=None)
            golden = derive_golden_biases(info)
            derived = {p: d.value for p, d in res.sens.side_biases.items()}
            rows.append({
                "cell": parsed["cell_name"], "arc": arc_id, "corner": corner,
                "P1": res.verdict.p1.status.value,
                "P2": res.verdict.p2.status.value,
                "P3": res.verdict.p3.status.value,
                "bias_match": classify_bias_match(
                    derived, res.sens.set_pins, res.sens.masked_pins, golden),
                "arc_check": _arc_check_class(res.sens.arc_check),
                "notes": "",
            })
        except Exception as e:
            rows.append({"cell": parsed.get("cell_name", "?"), "arc": arc_id,
                         "corner": corner, "P1": "ERROR", "P2": "ERROR",
                         "P3": "ERROR", "bias_match": "N/A",
                         "arc_check": "INDEPENDENT", "notes": str(e)[:120]})

    def _count(key):
        c = {}
        for r in rows:
            c[r[key]] = c.get(r[key], 0) + 1
        return c

    agree = sum(1 for r in rows if r["arc_check"] == "AGREE")
    summary = {
        "total": len(rows),
        "P1": _count("P1"), "P2": _count("P2"), "P3": _count("P3"),
        "bias_match": _count("bias_match"),
        "arc_check_agree_rate": round(100.0 * agree / len(rows), 1) if rows else 0.0,
    }
    return {"rows": rows, "summary": summary}


def audit_csv(rows):
    """Serialize rows to CSV with exactly CSV_COLUMNS in order."""
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in CSV_COLUMNS})
    return buf.getvalue()
