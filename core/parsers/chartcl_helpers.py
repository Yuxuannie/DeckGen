"""chartcl_helpers.py - companion utilities for char*.tcl parsing.

Ports of MCQC 1-general/hybrid_char_helper.py functions that live outside
the ChartclParser class.
"""

import re


def read_chartcl(filepath):
    """Return file content as a single string.

    Mirrors MCQC qaTemplateMaker/chartcl_condition.py::read_chartcl.
    """
    with open(filepath, 'r') as f:
        return f.read()


def parse_chartcl_for_cells(filepath):
    """Extract cell names from 'set cells {CELL1 CELL2 ...}' line.

    Mirrors MCQC hybrid_char_helper.parse_chartcl_for_cells.
    """
    cells = []
    with open(filepath, 'r') as f:
        for line in f:
            if 'set cells' not in line:
                continue
            tokens = line.split()
            for tok in tokens[2:]:
                if tok in ('{', '}', '[', ']'):
                    continue
                if 'packet_slave_cells' in tok:
                    continue
                cells.append(tok.replace('{', '').replace('}', ''))
    return cells


# extsim_model_include "/path/to/base.inc"
# extsim_model_include -type hold "/path/to/hold.inc"
_INC_TYPED_RE = re.compile(
    r'extsim_model_include\s+-type\s+(\w+)\s+"([^"]+)"')
_INC_PLAIN_RE = re.compile(
    r'extsim_model_include\s+"([^"]+)"')


def parse_chartcl_for_inc(filepath):
    """Extract {arc_type -> model .inc path} dict.

    Entry without -type is recorded under key 'traditional'.
    Mirrors MCQC hybrid_char_helper.parse_chartcl_for_inc.
    """
    result = {}
    content = read_chartcl(filepath)

    for arc_type, path in _INC_TYPED_RE.findall(content):
        result[arc_type] = path

    # Plain (untyped) entries -- match lines that don't have -type between
    # extsim_model_include and the path. We scan line-by-line to avoid double
    # matching typed lines.
    for line in content.splitlines():
        if 'extsim_model_include' not in line:
            continue
        if '-type' in line:
            continue
        m = _INC_PLAIN_RE.search(line)
        if m:
            result['traditional'] = m.group(1)

    return result
