"""core/lsf.py -- production-shaped mock LSF.

emit_arrays writes the REAL, submittable bsub job-array scripts the team would
run, plus an index->arc->deck manifest read via $LSB_JOBINDEX. bjobs_snapshot
renders the monitor loop honestly: PEND only, never inventing DONE/EXIT.
ASCII only. Simulator-free.
"""
from __future__ import annotations

import os


def emit_arrays(generated_rows, out_dir, slot_limit=50, runlimit="00:20"):
    """Group generated rows by corner; write lsf/deckgen_<corner>.bsub and
    lsf/index_<corner>.manifest per corner. Returns
    {corner: {'script','manifest','n_jobs'}}."""
    lsf_dir = os.path.join(out_dir, 'lsf')
    os.makedirs(os.path.join(lsf_dir, 'logs'), exist_ok=True)

    by_corner = {}
    for r in generated_rows:
        if r.get('state') != 'generated':
            continue
        by_corner.setdefault(r['corner'], []).append(r)

    result = {}
    for corner, rows in by_corner.items():
        n = len(rows)
        man_path = os.path.join(lsf_dir, 'index_%s.manifest' % corner)
        with open(man_path, 'w', encoding='ascii') as fh:
            for r in rows:
                fh.write('%s\t%s\n' % (r['arc_id'], r.get('deck_path', '')))
        script_path = os.path.join(lsf_dir, 'deckgen_%s.bsub' % corner)
        log_glob = os.path.join(lsf_dir, 'logs', '%s.%%I.out' % corner)
        lines = [
            '#!/bin/bash',
            '#BSUB -J "deckgen_%s[1-%d]%%%d"' % (corner, n, slot_limit),
            '#BSUB -W %s' % runlimit,
            '#BSUB -o %s' % log_glob,
            'DECK=$(sed -n "${LSB_JOBINDEX}p" %s | cut -f2)' % man_path,
            '# team runs HSPICE:',
            'hspice "$DECK"',
            '',
        ]
        with open(script_path, 'w', encoding='ascii') as fh:
            fh.write('\n'.join(lines))
        result[corner] = {'script': script_path, 'manifest': man_path,
                          'n_jobs': n}
    return result


def bjobs_snapshot(arrays):
    """Mock bjobs: every array element PEND, labeled honestly."""
    lines = []
    for corner, info in sorted(arrays.items()):
        lines.append('deckgen_%s[1-%d]   PEND   (awaiting farm -- team runs '
                     'HSPICE)' % (corner, info['n_jobs']))
    return lines
