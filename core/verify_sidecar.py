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
