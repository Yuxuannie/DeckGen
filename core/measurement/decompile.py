"""decompile.py -- G1 of the Phase G spec: decompile mined grammar recipes
into a typed IR of semantic primitives, each line owned by a NAMED RULE with
extracted params and a human-readable why. The IR stores every raw line
verbatim, so re-emission is byte-exact by construction; the semantic value is
the classification (what is this line, why is it here), quantified by the
residue report (lines no rule owns degrade to 'verbatim' -- listed, never
dropped). CLI: `python -m core.measurement.decompile report [grammar.json]`.
stdlib, ASCII."""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache

# ---------------------------------------------------------------------------
# rule battery -- ordered, first full-match wins. Patterns are written against
# the 55-entry local corpus census (2026-07-03); novel airgap lines fall to
# 'verbatim' and surface in the residue report rather than being guessed at.
# ---------------------------------------------------------------------------

_R = re.compile


def _param_extract(rx_names):
    def ex(m):
        return {k: m.group(k) for k in rx_names if m.group(k) is not None}
    return ex


_RULES = [
    # -- banner / provenance ------------------------------------------------
    ("banner", _R(r"\*{2,3} SPICE Deck created by .*\*{3}$"), None,
     "deck title banner; SPICE reads line 1 as the simulation title"),
    ("dont_touch", _R(r"\* DONT_TOUCH_PINS(?: (?P<pins>\S+))?$"),
     _param_extract(["pins"]),
     "marker consumed by the char driver: the named pins (or the bias "
     "section's pins when unnamed) must not be re-tied"),
    ("header_info", _R(r"(?:\* )?\$HEADER_INFO$"), None,
     "provenance comment placeholder; filled with cell/arc identity"),
    # -- simulator options ---------------------------------------------------
    ("sim_options", _R(r"\.options .+$"), None,
     "HSPICE accuracy/convergence knobs (three-party methodology constants)"),
    ("sim_options", _R(r"\.option sampling_method=\S+$"), None,
     "Monte Carlo sampling policy (LHS)"),
    ("sim_options", _R(r"\.save level=none$"), None,
     "suppress operating-point save (output size policy)"),
    # -- constraint-search block (hold/mpw) ----------------------------------
    ("opt_search", _R(r"\* THANOS Headers$"), None,
     "header of the constraint-search directive block"),
    ("opt_search", _R(r"\* CONSTR_CRITERIA \| (?P<crit>.+)$"),
     _param_extract(["crit"]),
     "search criterion the driver optimizes against"),
    ("opt_search", _R(r"\* OPT_RESULTS \| (?P<meas>.+)$"),
     _param_extract(["meas"]),
     "measurements the search reads back per iteration"),
    ("opt_search", _R(r"\* MEAS_DEGRADE_PER (?P<meas>\S+) \| (?P<per>.+)$"),
     _param_extract(["meas", "per"]),
     "pass/fail degradation threshold for the search (pushout fraction)"),
    ("opt_search", _R(r"\* CONSTR_PIN_PARAM \| (?P<param>.+)$"),
     _param_extract(["param"]),
     "the swept parameter: offset of the constrained pin's edge"),
    ("opt_search", _R(r"\*\.param constr_pin_offset = OPT1\(.*$"), None,
     "HSPICE-native optimizer alternative (disabled; driver-side search)"),
    ("opt_search", _R(r"\* \[1ps tolerance\].*$"), None,
     "search tolerance derivation note"),
    ("opt_search", _R(r"\*\.MODEL optmod opt .+$"), None,
     "optimizer model for the HSPICE-native path (disabled)"),
    ("opt_search",
     _R(r"\.param (?P<name>opt_init|opt_ub|opt_lb) = (?P<value>.+)$"),
     _param_extract(["name", "value"]),
     "constraint-search window bound (init/upper/lower)"),
    ("opt_search",
     _R(r"\.param (?P<name>constr_pin_offset) = (?P<value>.+)$"),
     _param_extract(["name", "value"]),
     "the swept variable: constrained-pin edge offset under search"),
    # -- timing skeleton ------------------------------------------------------
    ("timing_param",
     _R(r"\.param (?P<name>(?:related|constrained)_pin_t(?P<phase>\d\d))"
        r" = (?P<value>.+)$"),
     _param_extract(["name", "phase", "value"]),
     "waveform timestamp: anchors stimulus phase t%(phase)s in the "
     "transient window"),
    ("window_param",
     _R(r"\.param (?P<name>max_slew|search_window) = (?P<value>.+)$"),
     _param_extract(["name", "value"]),
     "slew/search-window wiring (family-specific: delay uses max_slew "
     "directly; mpw fixes max_slew and sweeps search_window)"),
    ("param", _R(r"\.param (?P<name>\w+) = (?P<value>.+)$"),
     _param_extract(["name", "value"]),
     "recipe parameter"),
    # -- initialization -------------------------------------------------------
    ("nodeset_enable", _R(r"\.option ptran_nodeset=(?P<v>\d+)$"),
     _param_extract(["v"]),
     "enable pseudo-transient nodeset initialization"),
    ("nodeset",
     _R(r"\.nodeset v\((?P<node>[^)]+)\) = '(?P<rail>vdd_value|vss_value)'$"),
     _param_extract(["node", "rail"]),
     "initialize storage/output node pattern %(node)s to %(rail)s so cycle 1 "
     "starts from a known state (N2P naming convention)"),
    # -- stimulus -------------------------------------------------------------
    ("stimulus",
     _R(r"XV(?P<tag>\S+) (?P<pin>\S+) 0 (?P<model>stdvs_\S+) VDD='vdd_value'"
        r" slew='(?P<slew>[^']+)'(?P<anchors>( t\d\d='[^']+')+)$"),
     _param_extract(["tag", "pin", "model", "slew", "anchors"]),
     "toggling source: drives %(pin)s with waveform model %(model)s anchored "
     "at the t0x timestamps"),
    ("fixed_tie",
     _R(r"V(?P<tag>\w+) (?P<pin>\w+) 0 '(?P<rail>vdd_value|vss_value)'$"),
     _param_extract(["tag", "pin", "rail"]),
     "cluster methodology hard-ties %(pin)s to %(rail)s (mined as recipe: "
     "fixed for every cell of this structural family)"),
    # -- measurement ----------------------------------------------------------
    ("meas", _R(r"\.meas (?:tran )?(?P<name>\S+) .*$"),
     lambda m: {"name": m.group("name"),
                "crosses": re.findall(r"cross=(\d+)", m.group(0))},
     "measurement %(name)s; cross=N selects WHICH edge/cycle is measured"),
    # -- transient ------------------------------------------------------------
    ("tran", _R(r"\.tran (?P<step>\S+) (?P<stop>\S+)(?P<rest>.*)$"),
     _param_extract(["step", "stop", "rest"]),
     "transient command: window covers all stimulus phases; sweep monte "
     "hooks the MC deck"),
    ("end", _R(r"\.end$"), None, "deck terminator"),
    # -- section comments ------------------------------------------------------
    ("section",
     _R(r"\* (?P<name>SPICE options|Toggling pins|Measurements|"
        r"Transient Sim Command|Optimization settings|Waveform timestamps|"
        r"Pin definitions|Unspecified pins|Output Load)$"),
     _param_extract(["name"]),
     "section marker (also an injection anchor for the assembler)"),
]


@lru_cache(maxsize=8192)
def explain_recipe_line(line):
    """(rule, params, why) for one recipe line; ('verbatim', {}, ...) when no
    rule owns it. Cached: the corpus repeats lines heavily across entries."""
    s = line.strip()
    if not s:
        return ("blank", (), "spacing")
    for rule, rx, extract, why in _RULES:
        m = rx.fullmatch(s)
        if m:
            params = extract(m) if extract else {}
            try:
                why_txt = why % params if "%(" in why else why
            except (KeyError, ValueError):
                why_txt = why
            return (rule, tuple(sorted(params.items())), why_txt)
    return ("verbatim", (),
            "no semantic rule owns this line yet (kept verbatim; extend the "
            "rule battery in core/measurement/decompile.py)")


def explain_frame_line(line):
    """Rule+why for ANY frame line: collateral/bias-section lines (which the
    recipe region excludes) route through regions.classify_line; recipe lines
    through the rule battery. Used by the G1 sidecar."""
    from core.measurement.regions import classify_line
    cls = classify_line(line)
    if cls == "collateral":
        return {"rule": "collateral",
                "why": "resolved from collateral (values + sources in the "
                       "sidecar 'collateral' block)"}
    if cls == "bias":
        return {"rule": "section",
                "why": "engine bias injection anchor"}
    if cls == "blank":
        return {"rule": "blank", "why": "spacing"}
    rule, params, why = explain_recipe_line(line)
    return {"rule": rule, "why": why}


def decompile_entry(entry):
    """Ordered IR nodes for one grammar entry: {'rule','params','line','why'}
    per recipe line. Re-emission = [n['line'] for n in nodes], byte-exact by
    construction (the raw line is stored verbatim)."""
    nodes = []
    for line in entry["recipe_lines"]:
        rule, params, why = explain_recipe_line(line)
        nodes.append({"rule": rule, "params": dict(params),
                      "line": line, "why": why})
    return nodes


def report(grammar):
    """Residue report over a grammar: per-rule line counts + every verbatim
    line named with its entry provenance. sum(by_rule) == total (conservation)."""
    by_rule = {}
    verbatim = []
    total = 0
    for e in grammar["entries"]:
        for n in decompile_entry(e):
            total += 1
            by_rule[n["rule"]] = by_rule.get(n["rule"], 0) + 1
            if n["rule"] == "verbatim":
                verbatim.append({"entry": e["provenance"][0],
                                 "line": n["line"]})
    covered = total - len(verbatim)
    return {"total": total, "by_rule": by_rule, "verbatim": verbatim,
            "coverage_pct": round(100.0 * covered / total, 1) if total else 0.0}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "report":
        print("usage: python -m core.measurement.decompile report "
              "[grammar.json]")
        return 2
    path = argv[1] if len(argv) > 1 else "config/measurement_grammar.json"
    rep = report(json.load(open(path, encoding="ascii")))
    print("semantic coverage: %.1f%% (%d/%d lines owned by a named rule)"
          % (rep["coverage_pct"], rep["total"] - len(rep["verbatim"]),
             rep["total"]))
    for rule, n in sorted(rep["by_rule"].items(), key=lambda kv: -kv[1]):
        print("  %5d  %s" % (n, rule))
    if rep["verbatim"]:
        print("VERBATIM RESIDUE (%d lines) -- extend the rule battery:"
              % len(rep["verbatim"]))
        for v in rep["verbatim"]:
            print("  [%s] %s" % (v["entry"], v["line"]))
    return 0 if not rep["verbatim"] else 1


if __name__ == "__main__":
    sys.exit(main())
