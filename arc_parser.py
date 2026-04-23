"""
arc_parser.py - Parses cell_arc_pt identifier strings.

Format:
    {arc_type}_{cell}_{probe_pin}_{probe_dir}_{rel_pin}_{rel_dir}_{when}_{I1}_{I2}

Examples:
    combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4
    combinational_MUX4MDLIMZD0P7BWP130HPNPN3P48CPD_Z_rise_S1_rise_notI0_notI1_notI2_I3_S0_4_4
    hold_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2
"""

import re

# Known arc type prefixes
ARC_TYPES = [
    'combinational', 'combinational_rise', 'combinational_fall',
    'hold', 'setup', 'removal', 'recovery',
    'non_seq_hold', 'non_seq_setup',
    'min_pulse_width',
    'nochange_low_low', 'nochange_low_high',
    'nochange_high_low', 'nochange_high_high',
]

# Known pin names (short, typically 1-4 chars, uppercase)
PIN_PATTERN = re.compile(r'^[A-Z][A-Z0-9]*$')

# Known direction keywords
DIRECTIONS = {'rise', 'fall'}


def parse_arc_identifier(identifier):
    """Parse a cell_arc_pt identifier string.

    Args:
        identifier: str like
            "combinational_ND2..._ZN_rise_A1_fall_NO_CONDITION_4_4"

    Returns:
        dict with keys:
            arc_type, cell_name, probe_pin, probe_dir,
            rel_pin, rel_dir, when, i1, i2
        Returns None if parsing fails.
    """
    identifier = identifier.strip()
    if not identifier:
        return None

    parts = identifier.split('_')
    if len(parts) < 8:
        return None

    # 1) Extract arc_type from the front (may be multi-word like "non_seq_hold")
    arc_type = None
    arc_end = 0
    for at in sorted(ARC_TYPES, key=len, reverse=True):
        at_parts = at.split('_')
        prefix = '_'.join(parts[:len(at_parts)])
        if prefix == at:
            arc_type = at
            arc_end = len(at_parts)
            break

    if arc_type is None:
        # Try single-word arc type
        arc_type = parts[0]
        arc_end = 1

    # 2) Extract table points from the tail: last two fields should be integers
    i1 = None
    i2 = None
    remaining = parts[arc_end:]
    if len(remaining) >= 2:
        try:
            i2 = int(remaining[-1])
            i1 = int(remaining[-2])
            remaining = remaining[:-2]
        except ValueError:
            pass

    if len(remaining) < 4:
        return None

    # 3) Work backwards from the remaining tokens to find:
    #    ..._{rel_pin}_{rel_dir}_{when_tokens}...
    #    ..._{probe_pin}_{probe_dir}_{rel_pin}_{rel_dir}_{when}...
    #
    # Strategy: scan from right to find the rel_dir, then rel_pin before it.
    # Then between rel_pin and the cell_name, find probe_pin and probe_dir.
    # The when condition is everything between rel_dir and the table points.

    # Find rightmost direction keyword -- that's rel_dir.
    # But we need to be careful: when conditions can contain "not" prefixed tokens.
    # The pattern is: ...cell_parts..._probePin_probeDir_relPin_relDir_whenParts...

    # Let's try to find the structure by scanning for direction keywords.
    # The first two direction keywords (from left in remaining) give probe_dir and rel_dir.

    dir_positions = []
    for i, token in enumerate(remaining):
        if token in DIRECTIONS:
            dir_positions.append(i)

    if len(dir_positions) < 2:
        return None

    # First direction = probe_dir, second = rel_dir
    probe_dir_idx = dir_positions[0]
    rel_dir_idx = dir_positions[1]

    # Cell name = everything before probe_pin (one token before probe_dir)
    if probe_dir_idx < 1:
        return None

    probe_pin_idx = probe_dir_idx - 1
    cell_parts = remaining[:probe_pin_idx]
    if not cell_parts:
        return None

    cell_name = '_'.join(cell_parts)
    probe_pin = remaining[probe_pin_idx]
    probe_dir = remaining[probe_dir_idx]

    # rel_pin is one token before rel_dir
    rel_pin_idx = rel_dir_idx - 1
    if rel_pin_idx <= probe_dir_idx:
        return None

    rel_pin = remaining[rel_pin_idx]
    rel_dir = remaining[rel_dir_idx]

    # When condition = everything between rel_dir and the end (table points already stripped)
    when_start = rel_dir_idx + 1
    when_parts = remaining[when_start:]

    if when_parts:
        # Convert notXX back to !XX for the when condition
        when_tokens = []
        for wp in when_parts:
            if wp == 'NO' and len(when_parts) > 1:
                continue
            if wp == 'CONDITION':
                when_tokens = []
                break
            if wp.startswith('not'):
                when_tokens.append('!' + wp[3:])
            else:
                when_tokens.append(wp)
        when = '&'.join(when_tokens) if when_tokens else 'NO_CONDITION'
    else:
        when = 'NO_CONDITION'

    # Handle "NO_CONDITION" that may appear as two tokens
    if '_'.join(remaining[when_start:]) == 'NO_CONDITION':
        when = 'NO_CONDITION'

    return {
        'arc_type': arc_type,
        'cell_name': cell_name,
        'probe_pin': probe_pin,
        'probe_dir': probe_dir,
        'rel_pin': rel_pin,
        'rel_dir': rel_dir,
        'when': when,
        'i1': i1,
        'i2': i2,
        'raw': identifier,
    }


def parse_arc_list(text):
    """Parse multiple arc identifiers (one per line, or comma-separated).

    Returns:
        list of parsed dicts
    """
    lines = re.split(r'[\n,;]+', text.strip())
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parsed = parse_arc_identifier(line)
        if parsed:
            results.append(parsed)
    return results
