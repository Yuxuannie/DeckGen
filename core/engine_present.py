"""engine_present.py -- data layer that turns a (cell, arc, options) request into
display-ready data for the showcase GUI (spec 2026-06-10).

Calls the v2 engine and the verify sidecar; returns JSON-serializable dicts plus
ready-to-embed SVG. NEVER raises to the caller: any engine/topology failure is
returned as {"status": "ERROR", ...} so the GUI renders a card, not a 500.
"""

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
    }
