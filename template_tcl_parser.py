"""
template_tcl_parser.py - Extracts slew/load index values from Liberty template.tcl.

Parses lines like:
    index_1 ("0.05 0.1 0.2 0.5 1.0")
    index_2 ("0.0005 0.001 0.005 0.01 0.05")
    index_3 ("0.01 0.02 0.05 0.1 0.2")

Returns per-template index lists. Given table point indices (i1, i2), callers
can look up the actual slew and load values.
"""

import re


def parse_template_tcl(path):
    """Parse a template.tcl file and return index data per template.

    Returns:
        dict: {
            'templates': {
                '<template_name>': {
                    'index_1': [float, float, ...],
                    'index_2': [float, float, ...],
                    'index_3': [float, float, ...],
                },
                ...
            },
            'global': {  # First/default template, used if no match
                'index_1': [...],
                'index_2': [...],
                'index_3': [...],
            }
        }
    """
    with open(path, 'r') as f:
        content = f.read()

    result = {'templates': {}, 'global': {}}

    # Pattern for template blocks: lu_table_template "name" { ... } or similar
    # We'll just scan for all index_N occurrences with their nearest template name.
    lines = content.split('\n')

    current_template = None
    brace_depth = 0

    for line in lines:
        stripped = line.strip()

        # Match template declarations
        m = re.match(
            r'lu_table_template\s+"([^"]+)"|lu_table_template\s+(\S+)|'
            r'(?:define_cell|template)\s+"([^"]+)"|'
            r'(?:define_cell|template)\s+(\S+)',
            stripped
        )
        if m:
            name = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            if name:
                current_template = name
                if current_template not in result['templates']:
                    result['templates'][current_template] = {}

        # Match index_N lines
        idx_match = re.search(r'index_(\d+)\s*\(\s*"([^"]*)"\s*\)', stripped)
        if idx_match:
            idx_num = int(idx_match.group(1))
            values_str = idx_match.group(2)
            values = _parse_number_list(values_str)
            if values:
                key = f'index_{idx_num}'
                if current_template and current_template in result['templates']:
                    if key not in result['templates'][current_template]:
                        result['templates'][current_template][key] = values
                # Always store in global as fallback
                if key not in result['global']:
                    result['global'][key] = values

    return result


def _parse_number_list(s):
    """Parse a space/comma separated list of numbers."""
    values = []
    for tok in re.split(r'[,\s]+', s.strip()):
        tok = tok.strip()
        if not tok:
            continue
        try:
            values.append(float(tok))
        except ValueError:
            pass
    return values


def lookup_slew_load(parsed, i1, i2, template_name=None, arc_type='delay'):
    """Look up slew/load values given table point indices.

    Args:
        parsed: output of parse_template_tcl()
        i1, i2: 1-based table point indices (from cell_arc_pt identifier)
        template_name: optional template name to use (falls back to global)
        arc_type: 'delay'/'slew' or 'hold'/'setup'/etc.

    Returns:
        dict with:
            'constr_pin_slew' (str with units, e.g. "2.5n")
            'rel_pin_slew'    (str with units)
            'output_load'     (str with units)
            'max_slew'        (str with units - the maximum slew value in the table)
        Returns None values for any missing data.
    """
    # Choose index source: specific template if available, else global
    indices = None
    if template_name and template_name in parsed['templates']:
        indices = parsed['templates'][template_name]
    if not indices or not indices.get('index_1'):
        indices = parsed['global']

    idx1 = indices.get('index_1', [])
    idx2 = indices.get('index_2', [])
    idx3 = indices.get('index_3', [])

    # Convert 1-based to 0-based
    try:
        i1_idx = int(i1) - 1 if i1 is not None else None
        i2_idx = int(i2) - 1 if i2 is not None else None
    except (ValueError, TypeError):
        i1_idx = i2_idx = None

    result = {
        'constr_pin_slew': None,
        'rel_pin_slew': None,
        'output_load': None,
        'max_slew': None,
    }

    # For constraints (hold/setup), index_1=constr slew, index_2=rel slew, index_3=load
    # For delay, index_1 = input slew (rel pin), index_2 = output load
    is_constraint = arc_type in ('hold', 'setup', 'removal', 'recovery',
                                  'non_seq_hold', 'non_seq_setup')

    if is_constraint:
        if i1_idx is not None and 0 <= i1_idx < len(idx1):
            result['constr_pin_slew'] = _format_slew(idx1[i1_idx])
        if i2_idx is not None and 0 <= i2_idx < len(idx2):
            result['rel_pin_slew'] = _format_slew(idx2[i2_idx])
        if idx3:
            # Output load: if only one entry in idx3 use it, else use last (largest)
            result['output_load'] = _format_load(idx3[0])
    else:
        # Delay: index_1 = input slew, index_2 = output load
        if i1_idx is not None and 0 <= i1_idx < len(idx1):
            slew_val = _format_slew(idx1[i1_idx])
            result['rel_pin_slew'] = slew_val
            result['constr_pin_slew'] = slew_val
        if i2_idx is not None and 0 <= i2_idx < len(idx2):
            result['output_load'] = _format_load(idx2[i2_idx])

    # Max slew = max of index_1
    if idx1:
        result['max_slew'] = _format_slew(max(idx1))

    return result


def _format_slew(value):
    """Format slew value with appropriate unit suffix."""
    if value == 0:
        return '0'
    # Liberty index values are typically in ns
    # Values between 1e-3 and 1 -> use ns ('n')
    # Values between 1 and 1000 -> likely already scaled, append 'n'
    if value < 1e-3:
        return f'{value*1e6:g}p'
    if value < 1:
        return f'{value:g}n'
    return f'{value:g}n'


def _format_load(value):
    """Format load value with appropriate unit suffix."""
    if value == 0:
        return '0'
    # Liberty cap values are typically in pF
    # Very small -> use fF
    if value < 1e-3:
        return f'{value*1e6:g}a'
    if value < 1:
        return f'{value*1e3:g}f'
    if value < 1e3:
        return f'{value:g}p'
    return f'{value:g}p'
