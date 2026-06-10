"""verify_sidecar.py -- v1 -> v2-engine adapter for the --verify audit layer.

Stage-A mounting (spec docs/superpowers/specs/2026-06-09-v2-audit-sidecar-design.md):
v1 stays the production path; for every arc it resolves, this module additionally
runs engine.pipeline.run_pipeline_src and writes a verdict sidecar JSON next to
the generated deck. v1 deck bytes are NEVER touched; an engine failure always
degrades to a status=ERROR sidecar, never to a broken run.

Imported LAZILY by deckgen.py / core/batch.py (only under --verify), so the
flag-off production path executes none of this module -- including the engine
imports below.
"""

import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone

from engine.pipeline import run_pipeline_src
from engine.stages.stage5_verify import MeasContext, p3_property


class VerifyInputError(Exception):
    """A v1-side input needed by the engine is missing (e.g. netlist text)."""


# ---------------------------------------------------------------------------
# record mapping (spec section 3.1)
# ---------------------------------------------------------------------------

def to_lit_when(when):
    """Literal '!SE&SI' -> engine-encoded 'notSE_SI'; NO_CONDITION/empty -> ''."""
    if not when or when.strip() in ('', 'NO_CONDITION'):
        return ''
    toks = []
    for t in when.split('&'):
        t = t.strip()
        if not t:
            continue
        toks.append('not' + t[1:] if t.startswith('!') else t)
    return '_'.join(toks)


def build_record(arc_info, job=None):
    """Map v1's resolved arc_info (+ optional batch job dict) to the engine
    record consumed by Arc.from_record. when/vector are optional oracles; the
    engine derives independently when they are absent."""
    job = job or {}
    lit = (arc_info.get('LIT_WHEN') or '').strip()
    if lit and lit != 'NO_CONDITION':
        when = lit
    else:
        when = to_lit_when(arc_info.get('WHEN') or job.get('when') or '')
    # belt: to_lit_when already returns '' for NO_CONDITION; this guards against future drift
    if when == 'NO_CONDITION':
        when = ''

    probe_list = []
    i = 1
    while True:
        p = arc_info.get('PROBE_PIN_%d' % i)
        if not p:
            break
        probe_list.append(p)
        i += 1
    if not probe_list and job.get('probe_pin'):
        probe_list = [job['probe_pin']]

    return {
        'cell': arc_info['CELL_NAME'],
        'arc_type': arc_info['ARC_TYPE'],
        'rel_pin': arc_info['REL_PIN'],
        'rel_dir': arc_info['REL_PIN_DIR'],
        'constr_pin': arc_info['CONSTR_PIN'],
        'constr_dir': arc_info.get('CONSTR_PIN_DIR') or '',
        'when': when,
        'lit_when': lit,
        'when_literal': arc_info.get('WHEN') or job.get('when', '') or '',
        'vector': arc_info.get('VECTOR', '') or '',
        'probe_list': probe_list,
        'measurement': '',          # filled by write_sidecar after extraction
        'arc_id': job.get('arc_id', '') or '',
        'corner': job.get('corner', '') or '',
    }


# ---------------------------------------------------------------------------
# meas extraction (spec section 3.3) -- from v1's substituted deck lines
# ---------------------------------------------------------------------------

MEAS_MARKER = '* Measurements'


def extract_meas_block(deck_lines):
    """Return (meas_text, note). note is None on success; on failure it is a
    human-readable reason that MUST surface in the sidecar (never silent)."""
    lines = [l if isinstance(l, str) else str(l) for l in deck_lines]
    start = None
    for i, l in enumerate(lines):
        if MEAS_MARKER in l:
            start = i
            break
    if start is not None:
        block = []
        for l in lines[start:]:
            if l.lstrip().lower().startswith('.tran'):
                break
            block.append(l)
        text = ''.join(block).strip('\n')
        if '.meas' in text:
            return text, None
    meas_only = [l for l in lines if l.lstrip().startswith('.meas')]
    if meas_only:
        return ''.join(meas_only).strip('\n'), None
    return '', ("meas extraction failed: marker '* Measurements' absent "
                "and no .meas lines")


# ---------------------------------------------------------------------------
# golden biases + three-state bias match (spec section 5)
# ---------------------------------------------------------------------------

def derive_golden_biases(arc_info):
    """The biases v1's deck drives, with the exact semantics of
    deck_builder._generate_when_condition_lines (skip rel/constr pins;
    '!X' -> 0 else 1). A non-empty SIDE_PIN_STATES wins (more explicit)."""
    out = {}
    for tok in (arc_info.get('SIDE_PIN_STATES') or '').split():
        pin, _, val = tok.partition('=')
        if pin and val in ('0', '1'):
            out[pin] = int(val)
    if out:
        return out
    when = arc_info.get('WHEN', '') or ''
    if not when or when == 'NO_CONDITION':
        return {}
    rel = arc_info.get('REL_PIN', '')
    constr = arc_info.get('CONSTR_PIN', '')
    for cond in when.split('&'):
        cond = cond.strip()
        if not cond:
            continue
        pin = cond.lstrip('!')
        if pin in (rel, constr):
            continue
        out[pin] = 0 if cond.startswith('!') else 1
    return out


def classify_bias_match(derived, set_pins, masked_pins, golden):
    """Three-state aggregate (spec section 5): MISMATCH only for set-pin
    (critical) disagreements; masked pins are non-critical by definition."""
    if not golden:
        return 'N/A (no golden biases in deck)'
    crit_mism, crit_cmp, noncrit_diff, noncrit_cmp = [], 0, [], 0
    for pin, gval in golden.items():
        if pin not in derived:
            continue
        dval = derived[pin]
        if pin in set_pins:
            crit_cmp += 1
            if dval != gval:
                crit_mism.append('%s(derived=%s golden=%s)' % (pin, dval, gval))
        elif pin in masked_pins:
            noncrit_cmp += 1
            if dval != gval:
                noncrit_diff.append('%s derived=%s golden=%s' % (pin, dval, gval))
    if crit_mism:
        return 'MISMATCH: ' + ', '.join(crit_mism)
    if crit_cmp:
        if noncrit_diff:
            return 'MATCH (non-critical: ' + ', '.join(noncrit_diff) + ')'
        return 'MATCH'
    if noncrit_cmp:
        return 'NON_CRITICAL'
    return 'N/A (no golden biases in deck)'


# ---------------------------------------------------------------------------
# meas context from substituted deck lines (spec section 4.1)
# ---------------------------------------------------------------------------

_UNIT_NS = {'f': 1e-6, 'p': 1e-3, 'n': 1.0, 'u': 1e3, 'm': 1e6}
_PARAM_RE = re.compile(r"^\s*\.param\s+(\w+)\s*=\s*'?([^'\n]*?)'?\s*$")
_STDVS_RE = re.compile(r"^\s*XV\w*\s+(\S+)\s+0\s+(stdvs\w+)\s+(.*)$")
_TPAR_RE = re.compile(r"\bt(\d\d)\s*=\s*'([^']+)'")
_NUM_RE = re.compile(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?([fpnum]?)$")


def _resolve_ns(expr, params, depth=0):
    """Resolve a v1 template time expression to ns. Handles exactly the forms
    the production templates use: NUM[unit] | NAME | K * NAME | A + B.
    Returns None when the form is anything else (caller notes UNRESOLVED)."""
    if depth > 10 or expr is None:
        return None
    expr = expr.strip().strip("'")
    if '+' in expr:
        total = 0.0
        for part in expr.split('+'):
            v = _resolve_ns(part, params, depth + 1)
            if v is None:
                return None
            total += v
        return total
    if '*' in expr:
        left, _, right = expr.partition('*')
        try:
            k = float(left.strip())
        except ValueError:
            return None
        v = _resolve_ns(right, params, depth + 1)
        return None if v is None else k * v
    m = _NUM_RE.match(expr)
    if m:
        unit = m.group(1)
        return float(expr[:-1] if unit else expr) * _UNIT_NS.get(unit, 1.0)
    if expr in params:
        return _resolve_ns(params[expr], params, depth + 1)
    return None


def build_meas_context(deck_lines, arc_info):
    """Lift MeasContext from v1's substituted deck lines (spec 4.1).
    Never raises for unexpected template shapes: returns a context with
    capture_t_ns=None and a note (P3 then reports STUB naming the gap)."""
    lines = [l if isinstance(l, str) else str(l) for l in deck_lines]
    rel_pin = arc_info.get('REL_PIN', '')
    notes = []
    try:
        vdd = float(arc_info.get('VDD_VALUE') or 0.0)
    except ValueError:
        vdd = 0.0
        notes.append("UNRESOLVED: VDD_VALUE %r" % arc_info.get('VDD_VALUE'))

    params = {}
    for l in lines:
        m = _PARAM_RE.match(l)
        if m:
            params[m.group(1)] = m.group(2)

    def _unresolved(reason):
        notes.append(reason)
        return MeasContext(rel_edges=[], trig_cross=0, trig_td_ns=0.0,
                           capture_t_ns=None, capture_dir='', vdd=vdd,
                           notes=notes)

    # toggling-pin line: edge directions from the stdvs model-name suffix,
    # edge times from its tNN= params
    stdvs = None
    for l in lines:
        m = _STDVS_RE.match(l)
        if m and m.group(1) == rel_pin:
            stdvs = m
            break
    if stdvs is None:
        return _unresolved("UNRESOLVED: no stdvs toggling line for rel_pin "
                           "%r" % rel_pin)
    dirs = [t for t in stdvs.group(2).split('_') if t in ('rise', 'fall')]
    tpars = sorted(_TPAR_RE.findall(stdvs.group(3)))
    edges = []
    for (idx, pname), d in zip(tpars, dirs):
        t = _resolve_ns(pname, params)
        if t is None:
            return _unresolved("UNRESOLVED: .param %s = %r" %
                               (pname, params.get(pname)))
        edges.append(('t' + idx, t, d))
    edges.sort(key=lambda e: e[1])
    if not edges:
        return _unresolved("UNRESOLVED: stdvs line has no tNN= edge params")

    # primary measurement: first .meas whose trig probes v(rel_pin).
    # Clause attribution (normative): split at the 'targ' keyword; only a
    # trig-clause td gates the capture count.
    trig_cross, trig_td = None, 0.0
    pat = re.compile(r"trig\s+v\(%s\)" % re.escape(rel_pin), re.IGNORECASE)
    for l in lines:
        if not l.lstrip().startswith('.meas') or not pat.search(l):
            continue
        trig_part = re.split(r"\btarg\b", l, maxsplit=1)[0]
        mc = re.search(r"cross\s*=\s*(\d+)", trig_part)
        if not mc:
            continue
        trig_cross = int(mc.group(1))
        mtd = re.search(r"td\s*=\s*'?([^'\s]+)'?", trig_part)
        if mtd:
            td = _resolve_ns(mtd.group(1), params)
            if td is None:
                return _unresolved("UNRESOLVED: trig td %r" % mtd.group(1))
            trig_td = td
        break
    if trig_cross is None:
        return _unresolved("UNRESOLVED: no .meas trig on v(%s) with cross="
                           % rel_pin)

    after = [e for e in edges if e[1] >= trig_td]
    if len(after) < trig_cross:
        notes.append("trig cross=%d after td=%gns: only %d edge(s) in the "
                     "schedule" % (trig_cross, trig_td, len(after)))
        return MeasContext(rel_edges=edges, trig_cross=trig_cross,
                           trig_td_ns=trig_td, capture_t_ns=None,
                           capture_dir='', vdd=vdd, notes=notes)
    _, cap_t, cap_d = after[trig_cross - 1]
    return MeasContext(rel_edges=edges, trig_cross=trig_cross,
                       trig_td_ns=trig_td, capture_t_ns=cap_t,
                       capture_dir=cap_d, vdd=vdd, notes=notes)


# ---------------------------------------------------------------------------
# sidecar writer (spec section 5)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
SIDECAR_NAME = 'verify.json'


def engine_version_info():
    import engine
    commit = None
    try:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(engine.__file__)))
        out = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                             cwd=repo, capture_output=True, text=True,
                             timeout=1)
        if out.returncode == 0:
            commit = out.stdout.strip()
    except Exception:
        pass        # air-gapped server may have no git; commit stays None
    return {'version': getattr(engine, '__version__', 'unknown'),
            'commit': commit}


def _prop_dict(p):
    return {'status': p.status.value, 'detail': list(p.detail)}


def write_sidecar(deck_dir, arc_info, job, deck_lines):
    """Run the engine on one v1-resolved arc and write {deck_dir}/verify.json.
    NEVER raises for engine-side problems: any failure becomes a status=ERROR
    sidecar. (A failure writing the file itself propagates; the batch caller
    catches it and warns -- spec section 5.)"""
    started = datetime.now(timezone.utc).isoformat()
    payload = {
        'schema_version': SCHEMA_VERSION,
        'engine': engine_version_info(),
        'deck': 'nominal_sim.sp',
    }
    notes = []
    try:
        record = build_record(arc_info, job)
        payload['arc'] = {
            'arc_id': record['arc_id'], 'cell': record['cell'],
            'arc_type': record['arc_type'], 'corner': record['corner'],
            'rel_pin': record['rel_pin'], 'rel_dir': record['rel_dir'],
            'constr_pin': record['constr_pin'],
            'constr_dir': record['constr_dir'],
            'when': record['when'], 'when_literal': record['when_literal'],
            'vector': record['vector'],
        }
        npath = arc_info.get('NETLIST_PATH') or ''
        if not npath or not os.path.isfile(npath):
            raise VerifyInputError(
                'no netlist text available (NETLIST_PATH=%r)' % npath)
        with open(npath, 'r') as fh:
            src = fh.read()

        meas, mnote = extract_meas_block(deck_lines)
        if mnote:
            notes.append(mnote)
        record['measurement'] = meas
        inc = arc_info.get('INCLUDE_FILE') or ''
        model = ".inc '%s'" % inc if inc else ''

        result = run_pipeline_src(record, src, meas, model, 'v1-audit')

        if mnote:
            ctx = MeasContext(rel_edges=[], trig_cross=0, trig_td_ns=0.0,
                              capture_t_ns=None, capture_dir='', vdd=0.0,
                              notes=['no measurement block found in v1 deck '
                                     "(marker '* Measurements' absent and no "
                                     '.meas lines)'])
        else:
            ctx = build_meas_context(deck_lines, arc_info)
        result.verdict.p3 = p3_property(ctx, result.init, result.arc,
                                        sim_data=None)

        golden = derive_golden_biases(arc_info)
        derived = {p: d.value for p, d in result.sens.side_biases.items()}
        v = result.verdict
        payload.update({
            'status': 'OK',
            'verdict': {'overall': v.overall.value,
                        'p1': _prop_dict(v.p1), 'p2': _prop_dict(v.p2),
                        'p3': _prop_dict(v.p3)},
            'biases': {
                'derived': {p: {'value': d.value, 'reason': d.reason}
                            for p, d in result.sens.side_biases.items()},
                'golden': golden,
                'match': classify_bias_match(derived, result.sens.set_pins,
                                             result.sens.masked_pins, golden),
            },
            'arc_check': result.sens.arc_check,
            'stage_log': list(result.stage_log),
        })
    except Exception as e:
        frames = traceback.extract_tb(sys.exc_info()[2])
        last = frames[-1] if frames else None
        summary = ('%s:%s in %s: %s' % (last.filename, last.lineno,
                                        last.name, e)
                   if last else str(e))
        payload.update({
            'status': 'ERROR',
            'error': {'type': type(e).__name__, 'summary': summary,
                      'traceback_tail':
                          traceback.format_exc().splitlines()[-5:]},
        })
    payload['notes'] = notes
    payload['timestamps'] = {'started': started,
                             'finished': datetime.now(timezone.utc).isoformat()}
    path = os.path.join(deck_dir, SIDECAR_NAME)
    with open(path, 'w') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write('\n')
    return path
