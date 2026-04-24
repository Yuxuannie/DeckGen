"""mpw_skip.py - Arc skip logic (MCQC 0-mpw/qaTemplateMaker port).

Subset: SYNC2/3/4 removal arcs with Q probe are skipped.
Additional rules (MB, CKLNQR/HQR, RSDF) may be added if validation exposes them.
"""

import fnmatch


def skip_this_arc(cell_name, arc_type, rel_pin, rel_pin_dir,
                  pin, pin_dir, when, probe_list):
    """Return True if this arc should be skipped (MCQC parity).

    Mirrors the if-chain in MCQC 0-mpw/qaTemplateMaker/funcs.py:168-223.
    """
    probe_list = probe_list or []

    # SYNC2 Q removal
    if arc_type == 'removal' and fnmatch.fnmatch(cell_name, '*SYNC2*'):
        if any(p == 'Q' or 'Q' in p for p in probe_list):
            return True

    # SYNC3 Q removal
    if arc_type == 'removal' and fnmatch.fnmatch(cell_name, '*SYNC3*'):
        if any(p == 'Q' or 'Q' in p for p in probe_list):
            return True

    # SYNC4 Q removal
    if arc_type == 'removal' and fnmatch.fnmatch(cell_name, '*SYNC4*'):
        if any(p == 'Q' or 'Q' in p for p in probe_list):
            return True

    # TODO port remaining rules from 0-mpw/qaTemplateMaker/funcs.py:
    #   - CKLNQR/CKLHQR: skip if 'OV' in when
    #   - MB cells with ICG: skip if unbalanced vector after CP
    #   - MB cells with clkb probe: skip
    #   - RSDF: skip some arcs

    return False
