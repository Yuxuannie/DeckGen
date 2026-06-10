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
