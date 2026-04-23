"""
template_map.py - Node-aware template selection following MCQC 2-flow/funcs.py logic.

Ports the `getHspiceTemplateName` / `getThanosTemplateName` if-chain from the
MCQC 2-flow/funcs.py.  Returns a template path relative to the node templates
directory (e.g. "hold/template__sync2__q1__rise__fall__1.sp").

Returns None for:
  - mpw arcs (handled by the YAML registry in N2P_v1.0/mpw/)
  - arcs not yet ported (caller falls back to YAML registry)

Usage:
    from core.template_map import map_to_template

    rel = map_to_template(
        cell_name='SYNC2DFF',
        arc_type='hold',
        rel_pin='CP',
        rel_dir='rise',
        constr_dir='fall',
        probe_list=[],
        node='N2P_v1.0',
        templates_dir='/path/to/deckgen/templates',
    )
    # -> /path/to/deckgen/templates/N2P_v1.0/hold/template__sync2__q1__rise__fall__1.sp
"""

import fnmatch
import os

# Arc types that fall under "general" flow (delay / hold / setup / removal / recovery)
DELAY_ARC_TYPES = frozenset({
    'combinational', 'combinational_fall', 'combinational_rise',
    'falling_edge', 'rising_edge',
    'three_state_disable', 'three_state_enable',
    'clear', 'preset',
})

CONSTRAINT_ARC_TYPES = frozenset({
    'hold', 'setup', 'removal', 'recovery', 'non_seq_hold', 'non_seq_setup',
})

MPW_ARC_TYPES = frozenset({'min_pulse_width', 'mpw'})


def map_to_template(cell_name, arc_type, rel_pin, rel_dir, constr_dir,
                    probe_list=None, node='N2P_v1.0', templates_dir=None):
    """Return an absolute template path for the given arc, or None if not found.

    Args:
        cell_name:    Cell name string (e.g. 'SYNC2DFFBWP140HVT')
        arc_type:     Liberty arc type string
        rel_pin:      Related (clock) pin name
        rel_dir:      Related pin direction ('rise' | 'fall')
        constr_dir:   Constrained pin direction ('rise' | 'fall' | None)
        probe_list:   List of probe pin names (used by SYNC2/3 Q1 probe rules)
        node:         Process node identifier (e.g. 'N2', 'N2P_v1.0', 'A14')
        templates_dir: Base templates directory (e.g. '/path/to/deckgen/templates')

    Returns:
        str: Absolute path to template file, or None if not resolved here.
    """
    probe_list = probe_list or []

    # MPW arcs are handled by the YAML registry (templates/N2P_v1.0/mpw/)
    if arc_type in MPW_ARC_TYPES:
        return None

    rel = _get_template_rel(cell_name, arc_type, rel_pin, rel_dir, constr_dir, probe_list)
    if rel is None:
        return None

    if templates_dir is None:
        return None

    abs_path = os.path.join(templates_dir, node, rel)
    if os.path.exists(abs_path):
        return abs_path

    # Fall back to N2P_v1.0 base node if node-specific file missing
    if node != 'N2P_v1.0':
        base_path = os.path.join(templates_dir, 'N2P_v1.0', rel)
        if os.path.exists(base_path):
            return base_path

    return None


# ---------------------------------------------------------------------------
# Internal if-chain -- ported from 2-flow/funcs.py getHspiceTemplateName
#
# Rules follow the same priority order as the original: more-specific patterns
# (SYNC2/3/4, etc.) before generic fallbacks.
#
# TODO: port remaining ~850 rules from 2-flow/funcs.py.  Each rule block maps
# to one return statement below.  Run the MCQC validation test suite against
# DeckGen-generated decks to confirm parity.
# ---------------------------------------------------------------------------

def _get_template_rel(cell_name, arc_type, rel_pin, rel_dir, constr_dir, probe_list):
    """Return arc_type-relative template path, or None.

    Mirror of getHspiceTemplateName() from 2-flow/funcs.py.
    Template paths are relative to the node directory
    (e.g. "hold/template__sync2__q1__rise__fall__1.sp").
    """

    # --- Ignored arcs (return None explicitly) ---
    for sync_pat in ('*SYNC2*Q*', '*SYNC3*Q*', '*SYNC4*Q*'):
        if arc_type == 'removal' and fnmatch.fnmatch(cell_name, sync_pat):
            return None

    # --- SYNC2 hold arcs ---
    if (arc_type == 'hold' and fnmatch.fnmatch(cell_name, '*SYNC2*Q*') and
            rel_pin == 'CP' and rel_dir == 'rise' and constr_dir == 'fall' and
            'Q1' in probe_list):
        return 'hold/template__sync2__q1__rise__fall__1.sp'

    if (arc_type == 'hold' and fnmatch.fnmatch(cell_name, '*SYNC2*Q*') and
            rel_pin == 'CP' and rel_dir == 'rise' and constr_dir == 'rise' and
            'Q1' in probe_list):
        return 'hold/template__sync2__q1__rise__rise__1.sp'

    # --- SYNC3 hold arcs ---
    if (arc_type == 'hold' and fnmatch.fnmatch(cell_name, '*SYNC3*Q*') and
            rel_pin == 'CP' and rel_dir == 'rise' and constr_dir == 'fall' and
            'Q1' in probe_list):
        return 'hold/template__sync3__q1__rise__fall__1.sp'

    if (arc_type == 'hold' and fnmatch.fnmatch(cell_name, '*SYNC3*Q*') and
            rel_pin == 'CP' and rel_dir == 'rise' and constr_dir == 'rise' and
            'Q1' in probe_list):
        return 'hold/template__sync3__q1__rise__rise__1.sp'

    # --- Generic DFF / flop hold: CP rise, constr fall ---
    if (arc_type == 'hold' and rel_pin == 'CP' and rel_dir == 'rise' and
            constr_dir == 'fall'):
        return 'hold/template__CP__rise__fall__1.sp'

    # --- Generic DFF / flop hold: CP fall, constr rise ---
    if (arc_type == 'hold' and rel_pin == 'CP' and rel_dir == 'fall' and
            constr_dir == 'rise'):
        return 'hold/template__CP__fall__rise__1.sp'

    # --- Generic DFF / flop hold: CP rise, constr rise ---
    if (arc_type == 'hold' and rel_pin == 'CP' and rel_dir == 'rise' and
            constr_dir == 'rise'):
        return 'hold/template__CP__rise__rise__1.sp'

    # --- Generic DFF / flop hold: CP fall, constr fall ---
    if (arc_type == 'hold' and rel_pin == 'CP' and rel_dir == 'fall' and
            constr_dir == 'fall'):
        return 'hold/template__CP__fall__fall__1.sp'

    # --- Delay / combinational: rel_dir fall -> probe fall ---
    if arc_type in DELAY_ARC_TYPES and rel_dir == 'fall':
        return 'delay/template__fall__1.sp'

    # --- Delay / combinational: rel_dir rise -> probe rise ---
    if arc_type in DELAY_ARC_TYPES and rel_dir == 'rise':
        return 'delay/template__rise__1.sp'

    # TODO: port remaining rules from 2-flow/funcs.py lines 100-18624
    # (setup, removal, recovery, three_state, CKL, MB, LHAO, SDF variants, etc.)

    return None
