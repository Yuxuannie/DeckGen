"""arc_detail.py -- assemble everything the audit detail view shows for ONE arc:
the region table (engine vs kit, per side-pin state), the truth table + recovered
boolean function, the PUN/PDN topology blocks + per-state conducting sets, and the
verdict. All derived from the .subckt (Red Line A); the kit -when set is the
audited object, not an input to derivation.

stdlib only, ASCII.
"""
from __future__ import annotations

from itertools import product
from typing import Dict, List, Optional

from core import topo_pundn as T
from engine import switchlevel
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine.types import Arc

RAILS = T.RAILS


def _inputs_outputs(graph):
    driven = {d.terminals["d"] for d in graph.devices}
    inputs = [p for p in graph.ports if p not in RAILS and p not in driven]
    outputs = [p for p in graph.ports if p in driven and p not in RAILS]
    return inputs, outputs


def truth_table(graph, inputs: List[str], output: str) -> List[dict]:
    rows = []
    for combo in product((0, 1), repeat=len(inputs)):
        a = dict(zip(inputs, combo))
        rows.append({"inputs": a, "out": switchlevel.evaluate(graph, a).get(output)})
    return rows


# ---- Quine-McCluskey reduced sum-of-products (small n; display only) ----------
def _combine(a: str, b: str) -> Optional[str]:
    diff, out = 0, []
    for x, y in zip(a, b):
        if x != y:
            diff += 1
            out.append("-")
        else:
            out.append(x)
    return "".join(out) if diff == 1 else None


def boolean_sop(rows: List[dict], inputs: List[str], output: str) -> str:
    minterms = []
    for r in rows:
        if r["out"] == 1:
            minterms.append("".join(str(r["inputs"][p]) for p in inputs))
    if not minterms:
        return "%s = 0" % output
    if len(minterms) == 2 ** len(inputs):
        return "%s = 1" % output
    # prime implicants
    terms = set(minterms)
    primes = set()
    while terms:
        nxt, used = set(), set()
        tl = sorted(terms)
        for i in range(len(tl)):
            for j in range(i + 1, len(tl)):
                c = _combine(tl[i], tl[j])
                if c:
                    nxt.add(c)
                    used.add(tl[i])
                    used.add(tl[j])
        primes |= (terms - used)
        terms = nxt
    # greedy cover of the original minterms
    def covers(p, m):
        return all(pc == "-" or pc == mc for pc, mc in zip(p, m))
    uncovered = set(minterms)
    chosen = []
    for p in sorted(primes, key=lambda p: p.count("-"), reverse=True):
        hit = {m for m in uncovered if covers(p, m)}
        if hit:
            chosen.append(p)
            uncovered -= hit
        if not uncovered:
            break
    parts = []
    for p in chosen:
        lits = [("" if bit == "1" else "!") + pin
                for pin, bit in zip(inputs, p) if bit != "-"]
        parts.append("*".join(lits) if lits else "1")
    return "%s = %s" % (output, " + ".join(parts))


# ---- region table (engine vs kit, per side-pin state) ------------------------
def _comb(graph, arc, ccc):
    res = stage2_sensitize.derive_combinational(graph, arc, ccc)
    when_args = [w for w in (arc.raw.get("when_strings") or [])
                 if w not in ("NO_CONDITION", "", "NONE")]
    verdict = stage2_sensitize.comb_verdict(res, when_args)
    return res, verdict


def region_table(res, verdict, rel_pin: str) -> List[dict]:
    side = res.side_pins
    sens = {cs.label: cs for cs in res.sensitizing}
    blocked = {cs.label for cs in res.blocked}
    cover = set(verdict.cover)
    missing, extra = set(verdict.missing), set(verdict.extra)
    rows = []
    for combo in product((0, 1), repeat=len(side)):
        a = dict(zip(side, combo))
        label = "&".join((p if a[p] else "!" + p) for p in side) or "(uncond)"
        is_sens = label in sens
        diff = "MISS" if label in missing else ("EXTRA" if label in extra else "")
        rows.append({
            "side": a, "label": label,
            "engine": "SENS" if is_sens else "BLOCKED",
            "out_dir": sens[label].out_dir if is_sens else None,
            "kit": "covered" if label in cover else "-",
            "diff": diff,
        })
    return rows


def _state_why(rel: str, out: str, engine: str, out_dir: Optional[str],
               diff: str) -> str:
    """Plain-language reason for one side-pin state."""
    arrow = "" if not out_dir else (" (%s rises)" % out if out_dir == "R"
                                    else " (%s falls)" % out)
    if engine == "SENS":
        base = "toggling %s changes %s here%s" % (rel, out, arrow)
        if diff == "MISS":
            return base + " -- but the kit has no arc for this state (kit omits)."
        return base + "."
    base = "toggling %s cannot change %s here (no conducting path)" % (rel, out)
    if diff == "EXTRA":
        return base + " -- yet the kit marks a timing arc here (likely kit over-claim)."
    return base + "."


def _summary(rel: str, out: str, verdict, region: List[dict]) -> str:
    """One-line plain-language conclusion for the whole arc."""
    st = verdict.status.value
    n_sens = sum(1 for r in region if r["engine"] == "SENS")
    if st == "MATCH":
        return ("Engine and kit agree: %s sensitizes %s in exactly %d state(s)."
                % (rel, out, n_sens))
    if st == "UNSUPPORTED-WHEN":
        return ("Kit -when is not a pure conjunction (OR); engine cannot map it "
                "to states -- UNSUPPORTED, not judged.")
    parts = ["DIVERGENCE."]
    if verdict.extra:
        parts.append("Kit marks timing in {%s} where toggling %s cannot change %s "
                     "(likely kit over-claim)." % (", ".join(verdict.extra), rel, out))
    if verdict.missing:
        parts.append("Kit omits {%s} where the engine finds %s does change %s."
                     % (", ".join(verdict.missing), rel, out))
    return " ".join(parts)


def arc_detail(netlist_path: str, cell: str, rel_pin: str, output: str,
               when_strings: Optional[List[str]] = None,
               kit_raw: Optional[List[str]] = None) -> dict:
    """Full detail bundle for one (cell, rel_pin -> output) arc. Never raises."""
    import os
    try:
        with open(netlist_path, encoding="ascii", errors="replace") as fh:
            src = fh.read()
        graph = stage0_parse.parse(src, cell)
    except OSError as e:
        return {"status": "ERROR", "error": "cannot read netlist: %s" % e}
    inputs, outputs = _inputs_outputs(graph)
    out = output if output in outputs else (outputs[0] if outputs else output)
    ccc = stage1_ccc.decompose(graph)
    arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel_pin, rel_dir="rise",
              constr_pin=out, constr_dir="rise", when="NO_CONDITION",
              measurement="", raw={"probe_pin": out,
                                   "when_strings": list(when_strings or [])})
    if not stage2_sensitize.is_combinational_arc(graph, arc, ccc):
        return {"status": "NA", "error": "arc CCC has a state node (sequential)"}
    res, verdict = _comb(graph, arc, ccc)
    rows = truth_table(graph, inputs, out)
    region = region_table(res, verdict, rel_pin)
    for r in region:                                    # plain-language per state
        r["why"] = _state_why(rel_pin, out, r["engine"], r["out_dir"], r["diff"])

    # topology: SP blocks + per (relevant) side-state conducting sets (rel_pin=1)
    blocks = T.pull_networks(graph)
    side = res.side_pins
    states = []
    for r in region:
        assign = dict(r["side"])
        assign[rel_pin] = 1
        states.append({"label": r["label"], "assign": assign,
                       "on": sorted(T.conducting(graph, assign)),
                       "diff": r["diff"], "engine": r["engine"], "why": r["why"]})
    return {
        "status": "OK",
        "cell": cell, "rel_pin": rel_pin, "output": out,
        "inputs": inputs, "side_pins": side,
        "summary": _summary(rel_pin, out, verdict, region),
        "verdict": {"status": verdict.status.value, "missing": verdict.missing,
                    "extra": verdict.extra, "detail": verdict.detail},
        "boolean": boolean_sop(rows, inputs, out),
        "truth_table": rows,
        "region": region,
        "topology": {"blocks": [
            {"net": b["net"], "is_output": b["is_output"],
             "pun": b["pun"], "pdn": b["pdn"],
             "pun_text": T.sp_to_text(b["pun"]), "pdn_text": T.sp_to_text(b["pdn"])}
            for b in blocks], "states": states},
        "kit_raw": list(kit_raw or []),
    }
