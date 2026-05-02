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


# ---------------------------------------------------------------------------
# ALAPI format helpers (Altos template.tcl with define_template/define_arc)
# ---------------------------------------------------------------------------

def _is_alapi_format(content):
    """Return True if template.tcl uses Altos ALAPI format."""
    return 'ALAPI_active_cell' in content or (
        'define_template' in content and 'define_arc' in content)


def _join_continuation_lines(content):
    """Join Tcl backslash-continuation lines into single logical lines."""
    lines = content.split('\n')
    result = []
    buf = ''
    for line in lines:
        rstripped = line.rstrip()
        if rstripped.endswith('\\'):
            buf += rstripped[:-1] + ' '
        else:
            buf += line
            result.append(buf)
            buf = ''
    if buf:
        result.append(buf)
    return result


def _tokenize_tcl(s):
    """Tokenize one Tcl logical line into (type, value) pairs.

    type is 'bare', 'brace', or 'quoted'.
    Outer braces/quotes are stripped from the value.
    """
    tokens = []
    i = 0
    s = s.strip()
    while i < len(s):
        c = s[i]
        if c in ' \t':
            i += 1
        elif c == '{':
            depth = 0
            j = i
            while j < len(s):
                if s[j] == '{':
                    depth += 1
                elif s[j] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            tokens.append(('brace', s[i + 1:j]))
            i = j + 1
        elif c == '"':
            try:
                j = s.index('"', i + 1)
            except ValueError:
                j = len(s)
            tokens.append(('quoted', s[i + 1:j]))
            i = j + 1
        else:
            j = i
            while j < len(s) and s[j] not in ' \t{}"':
                j += 1
            tokens.append(('bare', s[i:j]))
            i = j
    return tokens


def _parse_alapi_cmd(logical_line):
    """Parse an ALAPI command line into (cmd, flags, positional).

    flags:      {'-type': 'hold', '-pin': 'E', ...}
    positional: ['CELLNAME']   (args not preceded by a -flag)
    Boolean flags (no value token) map to True.
    """
    tokens = _tokenize_tcl(logical_line)
    if not tokens:
        return '', {}, []
    cmd = tokens[0][1]
    flags = {}
    positional = []
    i = 1
    while i < len(tokens):
        typ, val = tokens[i]
        if typ == 'bare' and val.startswith('-'):
            # Look ahead: next token is value if it exists and is not itself a flag
            if (i + 1 < len(tokens) and
                    not (tokens[i + 1][0] == 'bare' and
                         tokens[i + 1][1].startswith('-'))):
                flags[val] = tokens[i + 1][1]
                i += 2
            else:
                flags[val] = True    # boolean flag, e.g. -user_arcs_only
                i += 1
        else:
            positional.append(val)
            i += 1
    return cmd, flags, positional


def _vector_to_dirs(vector):
    """Map an ALAPI vector string to (pin_dir, rel_pin_dir).

    3-char  (Xxx): first char = probe direction, no rel direction.
    4-char (XXxx): first char = rel direction, second = probe direction.
    x / X means 'any' -> mapped to empty string.

    Examples: Rxx->'rise','',  FRxx->'rise','fall',  xFxx->'fall',''
    """
    v = (vector or '').strip().upper()
    _m = {'R': 'rise', 'F': 'fall'}
    if len(v) >= 4 and v[2:4] == 'XX':
        pin_dir = _m.get(v[1], '')
        rel_dir = _m.get(v[0], '')
        return pin_dir, rel_dir
    if len(v) >= 3 and v[1:3] == 'XX':
        pin_dir = _m.get(v[0], '')
        return pin_dir, ''
    return '', ''


def _parse_alapi_full(content):
    """Parse ALAPI-format template.tcl.

    Returns (templates_dict, cells_dict, arcs_list) matching the schema
    used by parse_template_tcl_full.
    """
    logical_lines = _join_continuation_lines(content)

    templates = {}
    cells = {}
    arcs = []
    current_cell = None

    def _floats(s):
        try:
            return [float(x) for x in (s or '').split() if x]
        except ValueError:
            return []

    for line in logical_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # Track current cell from ALAPI_active_cell "NAME"
        m = re.search(r'ALAPI_active_cell\s+"([^"]+)"', stripped)
        if m:
            current_cell = m.group(1)
            continue

        first_word = stripped.split()[0] if stripped.split() else ''

        if first_word == 'define_template':
            _, flags, positional = _parse_alapi_cmd(stripped)
            name = positional[-1] if positional else None
            if not name:
                continue
            templates[name] = {
                'index_1': _floats(flags.get('-index_1', '')),
                'index_2': _floats(flags.get('-index_2', '')),
                'index_3': _floats(flags.get('-index_3', '')),
            }

        elif first_word == 'define_cell':
            _, flags, positional = _parse_alapi_cmd(stripped)
            name = positional[-1] if positional else current_cell
            if not name:
                continue
            cells[name] = {
                'pinlist':              flags.get('-pinlist', ''),
                'output_pins':          flags.get('-output', '').split(),
                'delay_template':       flags.get('-delay') or None,
                'constraint_template':  flags.get('-constraint') or None,
                'mpw_template':         flags.get('-mpw') or None,
                'si_immunity_template': flags.get('-si') or None,
            }

        elif first_word == 'define_arc':
            _, flags, positional = _parse_alapi_cmd(stripped)
            cell_name = positional[-1] if positional else current_cell
            if not cell_name:
                continue
            # MCQC parity: define_arc without -type defaults to 'combinational'
            # (charTemplateParser/funcs.py:481). These are the delay arcs.
            arc_type = flags.get('-type', '') or 'combinational'
            pin = flags.get('-pin', '')
            rel_pin = flags.get('-related_pin', '')
            vector = flags.get('-vector', '')
            when_raw = flags.get('-when', '') or 'NO_CONDITION'
            probe_str = flags.get('-probe', '')

            if arc_type == 'hidden':
                # hidden = internal characterization arc, not exported to .lib.
                continue

            pin_dir, rel_pin_dir = _vector_to_dirs(vector)
            probe_list = probe_str.split() if probe_str else ([pin] if pin else [])
            arcs.append({
                'cell':          cell_name,
                'arc_type':      arc_type,
                'pin':           pin,
                'pin_dir':       pin_dir,
                'rel_pin':       rel_pin,
                'rel_pin_dir':   rel_pin_dir,
                'when':          when_raw,
                'lit_when':      when_raw,
                'probe_list':    probe_list,
                'vector':        vector,
                'metric':        '',
                'metric_thresh': '',
            })

    return templates, cells, arcs


def parse_template_tcl(path):
    """Parse a template.tcl file and return index data per template.

    Supports both Liberty lu_table_template format and Altos ALAPI
    define_template format (auto-detected).

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

    if _is_alapi_format(content):
        # ALAPI format: define_template -index_1 {...} ... NAME
        templates, _, _ = _parse_alapi_full(content)
        result['templates'] = {
            name: {k: v for k, v in t.items() if v}
            for name, t in templates.items()
        }
        # Global fallback: first template with index_1
        for t in result['templates'].values():
            if t.get('index_1'):
                result['global'] = t
                break
        return result

    # Liberty format: lu_table_template / index_N ("...") lines
    lines = content.split('\n')
    current_template = None

    for line in lines:
        stripped = line.strip()

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

        idx_match = re.search(r'index_(\d+)\s*\(\s*"([^"]*)"\s*\)', stripped)
        if idx_match:
            idx_num = int(idx_match.group(1))
            values = _parse_number_list(idx_match.group(2))
            if values:
                key = f'index_{idx_num}'
                if current_template and current_template in result['templates']:
                    if key not in result['templates'][current_template]:
                        result['templates'][current_template][key] = values
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


# ---------------------------------------------------------------------------
# Full parser -- extends parse_template_tcl with cells + arcs + templates.
# Used by core.arc_info_builder for MCQC-parity arc_info composition.
# ---------------------------------------------------------------------------

_DEFINE_CELL_RE = re.compile(
    r'define_cell\s+"([^"]+)"\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
    flags=re.DOTALL)
_DEFINE_ARC_RE = re.compile(
    r'define_arc\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
    flags=re.DOTALL)
_DEFINE_INDEX_RE = re.compile(
    r'define_index\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
    flags=re.DOTALL)
_INDEX_N_RE = re.compile(r'index_(\d)\s*\(\s*"([^"]*)"\s*\)\s*;?')
# Matches  key : "quoted";  or  key : {braced};  or  key : bare_token;
_FIELD_COLON_RE = re.compile(
    r'(\w+)\s*:\s*(?:"([^"]*)"|\{([^}]*)\}|([^;\s][^;]*?))\s*;')
# Matches  key { braced }  (no colon, no semicolon -- used by pinlist/output_pins)
_FIELD_BRACE_RE = re.compile(r'(\w+)\s*\{([^}]*)\}')


def find_define_index_override(overrides, cell, pin, rel_pin, when):
    """Return the first matching define_index entry, or None.

    Matching (MCQC parity): exact cell, exact pin, rel_pin match (or '*'),
    when fnmatch.
    """
    import fnmatch as _fn
    for o in overrides:
        if o.get('cell') != cell:
            continue
        if o.get('pin') != pin and o.get('pin') != '*':
            continue
        rp = o.get('rel_pin')
        if rp and rp != '*' and not _fn.fnmatch(rel_pin or '', rp):
            continue
        w = o.get('when')
        if w and not _fn.fnmatch(when or '', w):
            continue
        return o
    return None


def _parse_block_fields(block_body):
    """Parse key-value pairs from a define_cell or define_arc body.

    Handles:
      - key : "quoted";
      - key : { braced };
      - key : bare_token;
      - key { braced }   (no colon -- pinlist, output_pins style)
    """
    fields = {}
    # First pass: colon-style fields (these are authoritative)
    for m in _FIELD_COLON_RE.finditer(block_body):
        key = m.group(1)
        quoted, braced, bare = m.group(2), m.group(3), m.group(4)
        if quoted is not None:
            fields[key] = quoted
        elif braced is not None:
            fields[key] = braced.strip()
        else:
            fields[key] = (bare or '').strip()
    # Second pass: bare brace fields (only if key not already captured)
    for m in _FIELD_BRACE_RE.finditer(block_body):
        key = m.group(1)
        if key not in fields:
            fields[key] = m.group(2).strip()
    return fields


import os as _os

_DEFINE_PINTYPE_RE = re.compile(
    r'define_pintype\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
    flags=re.DOTALL)


def _parse_sis_sidecar(tcl_path):
    """If a <stem>.sis file exists alongside tcl_path in a Template_sis/
    directory, parse it and return {pintype: {key: value}}.
    """
    stem = _os.path.splitext(_os.path.basename(tcl_path))[0]
    dirname = _os.path.dirname(tcl_path)
    sis_path = _os.path.join(dirname, 'Template_sis', stem + '.sis')
    if not _os.path.isfile(sis_path):
        return {}
    with open(sis_path, 'r') as f:
        content = f.read()
    result = {}
    for m in _DEFINE_PINTYPE_RE.finditer(content):
        name = m.group(1)
        fields = _parse_block_fields(m.group(2))
        result[name] = fields
    return result


def parse_template_tcl_full(path):
    """Full MCQC-style template.tcl parse.

    Returns:
        {
          'templates': {...},                    # from parse_template_tcl
          'cells':     {name: {
              'pinlist':              str,
              'output_pins':          list[str],
              'delay_template':       str or None,
              'constraint_template':  str or None,
              'mpw_template':         str or None,
              'si_immunity_template': str or None,
          }},
          'arcs':      [{
              'cell':        str,
              'arc_type':    str,
              'pin':         str,
              'pin_dir':     str,
              'rel_pin':     str,
              'rel_pin_dir': str,
              'when':        str,
              'lit_when':    str,
              'probe_list':  list[str],
              'vector':      str,
              'metric':      str,     # default ''
              'metric_thresh': str,   # default ''
          }],
          'global':    {...}  # from parse_template_tcl
        }
    """
    with open(path, 'r') as f:
        content = f.read()

    sis = _parse_sis_sidecar(path)

    if _is_alapi_format(content):
        templates, cells, arcs = _parse_alapi_full(content)
        base = parse_template_tcl(path)
        return {
            'templates':       base['templates'],
            'cells':           cells,
            'arcs':            arcs,
            'global':          base['global'],
            'index_overrides': [],
            'sis':             sis,
        }

    # Liberty format path
    base = parse_template_tcl(path)

    cells = {}
    for m in _DEFINE_CELL_RE.finditer(content):
        name = m.group(1)
        body = m.group(2)
        f = _parse_block_fields(body)
        cells[name] = {
            'pinlist':              f.get('pinlist', ''),
            'output_pins':          f.get('output_pins', '').split(),
            'delay_template':       f.get('delay_template')       or None,
            'constraint_template':  f.get('constraint_template')  or None,
            'mpw_template':         f.get('mpw_template')         or None,
            'si_immunity_template': f.get('si_immunity_template') or None,
        }

    arcs = []
    for m in _DEFINE_ARC_RE.finditer(content):
        body = m.group(1)
        f = _parse_block_fields(body)
        arcs.append({
            'cell':         f.get('cell', ''),
            'arc_type':     f.get('arc_type', ''),
            'pin':          f.get('pin', ''),
            'pin_dir':      f.get('pin_dir', ''),
            'rel_pin':      f.get('rel_pin', ''),
            'rel_pin_dir':  f.get('rel_pin_dir', ''),
            'when':         f.get('when', ''),
            'lit_when':     f.get('lit_when', ''),
            'probe_list':   f.get('probe_list', '').split(),
            'vector':       f.get('vector', ''),
            'metric':       f.get('metric', ''),
            'metric_thresh': f.get('metric_thresh', ''),
        })

    def _floats(s):
        s = (s or '').replace('"', '').strip()
        try:
            return [float(x) for x in s.split()]
        except ValueError:
            return []

    index_overrides = []
    for m in _DEFINE_INDEX_RE.finditer(content):
        body = m.group(1)
        idx_fields = {}
        for im in _INDEX_N_RE.finditer(body):
            idx_fields['index_' + im.group(1)] = im.group(2)
        f = _parse_block_fields(body)
        index_overrides.append({
            'cell':    f.get('cell', ''),
            'pin':     f.get('pin', ''),
            'rel_pin': f.get('rel_pin', ''),
            'when':    f.get('when', ''),
            'index_1': _floats(idx_fields.get('index_1', '')),
            'index_2': _floats(idx_fields.get('index_2', '')),
            'index_3': _floats(idx_fields.get('index_3', '')),
        })

    return {
        'templates':      base['templates'],
        'cells':          cells,
        'arcs':           arcs,
        'global':         base['global'],
        'index_overrides': index_overrides,
        'sis':            sis,
    }
