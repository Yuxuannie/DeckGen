"""
template_rules.py - MCQC template selection rules loaded from JSON.

Loads the 854 extracted rules from config/template_rules.json (generated from
MCQC's 18K-line if-chain in 2-flow/funcs.py).  Only HSPICE rules are used;
THANOS rules are skipped.

Rules are evaluated in order (first match wins), matching MCQC behavior.

Usage:
    from core.template_rules import match_template

    path = match_template(
        cell_name='DFFQ1BWP130...',
        arc_type='hold',
        rel_pin='CP', rel_pin_dir='rise',
        constr_pin='D', constr_pin_dir='fall',
        probe_list=['Q'],
        when='',
    )
"""

import fnmatch
import json
import os

# ---------------------------------------------------------------------------
# Load rules once at module import
# ---------------------------------------------------------------------------

_RULES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'template_rules.json')

_HSPICE_RULES = []

if os.path.isfile(_RULES_PATH):
    with open(_RULES_PATH, 'r') as _f:
        _all_rules = json.load(_f)
    _HSPICE_RULES = [r for r in _all_rules if r.get('function') == 'getHspiceTemplateName']


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _match_cell_pattern(cell_name, patterns):
    """Check if cell_name matches any fnmatch pattern in the list."""
    if not patterns:
        return False
    for pat in patterns:
        if fnmatch.fnmatch(cell_name, pat):
            return True
    return False


def _match_constr_pin(rule_constr_pin, actual_constr_pin):
    """Match the constr_pin field from a rule against the actual value.

    Rule constr_pin can be:
      - str: exact match or fnmatch pattern (e.g. "D", "F*_CLKEN")
      - list of str: any pattern in the list matches (fnmatch)
      - empty list []: matches anything (wildcard / not checked)
    """
    if rule_constr_pin is None:
        return True

    if isinstance(rule_constr_pin, list):
        if len(rule_constr_pin) == 0:
            # Empty list = not constrained
            return True
        for pat in rule_constr_pin:
            if fnmatch.fnmatch(actual_constr_pin, pat):
                return True
        return False

    # String: could contain wildcards
    if '*' in rule_constr_pin or '?' in rule_constr_pin:
        return fnmatch.fnmatch(actual_constr_pin, rule_constr_pin)
    return rule_constr_pin == actual_constr_pin


def _match_rel_pin(rule_rel_pin, actual_rel_pin):
    """Match rel_pin. Rule can be str or list."""
    if rule_rel_pin is None:
        return True
    if isinstance(rule_rel_pin, list):
        if len(rule_rel_pin) == 0:
            return True
        return actual_rel_pin in rule_rel_pin
    return rule_rel_pin == actual_rel_pin


def _match_when(rule_when, actual_when):
    """Match when condition.

    rule_when can be:
      - None: no constraint
      - str containing ' in when': substring check (e.g. '"CLKEN" in when')
      - str: exact match against actual_when
    """
    if rule_when is None:
        return True

    actual_when = actual_when or ''

    if isinstance(rule_when, str) and 'in when' in rule_when:
        # Extract the substring to search for: "CLKEN" in when -> CLKEN
        # The format is: "SUBSTRING" in when
        stripped = rule_when.replace(' in when', '').strip().strip('"').strip("'")
        return stripped in actual_when

    # Exact match
    return rule_when == actual_when


def _match_probe(rule_probe, actual_probe_list):
    """Match probe conditions.

    rule_probe is a dict with:
      - 'contains': list of strings that must be in probe_list
      - 'len': int or None -- if set, probe_list must have this length
    """
    if rule_probe is None:
        return True

    probe_list = actual_probe_list or []

    contains = rule_probe.get('contains', [])
    expected_len = rule_probe.get('len')

    # Check length constraint
    if expected_len is not None and len(probe_list) != expected_len:
        return False

    # Check that all required items are in probe_list
    for item in contains:
        if item not in probe_list:
            return False

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_template(cell_name, arc_type, rel_pin, rel_pin_dir,
                   constr_pin, constr_pin_dir,
                   probe_list=None, when=None):
    """Match MCQC template selection rules. Returns template relative path or None.

    Rules are evaluated in order (first match wins), matching MCQC behavior.
    Only HSPICE rules (not THANOS) are used.

    Args:
        cell_name:      Cell name string
        arc_type:       Arc type string (hold, setup, combinational, etc.)
        rel_pin:        Related pin name
        rel_pin_dir:    Related pin direction (rise/fall)
        constr_pin:     Constrained pin name
        constr_pin_dir: Constrained pin direction (rise/fall)
        probe_list:     List of probe pin names (optional)
        when:           When-condition string (optional)

    Returns:
        str: Template relative path (e.g. "hold/template__CP__rise__fall__1.sp")
             or None if no rule matches.
    """
    if not _HSPICE_RULES:
        return None

    probe_list = probe_list or []
    when = when or ''
    constr_pin = constr_pin or ''
    constr_pin_dir = constr_pin_dir or ''
    rel_pin = rel_pin or ''
    rel_pin_dir = rel_pin_dir or ''

    for rule in _HSPICE_RULES:
        # arc_type must match; skip "unknown" rules (incomplete extractions)
        r_arc = rule.get('arc_type')
        if not r_arc or r_arc == 'unknown':
            continue
        if r_arc != arc_type:
            continue

        # cell_pattern: list of fnmatch patterns; empty list = incomplete rule, skip
        r_cell = rule.get('cell_pattern', [])
        if not r_cell:
            continue
        if not _match_cell_pattern(cell_name, r_cell):
            continue

        # rel_pin
        if not _match_rel_pin(rule.get('rel_pin'), rel_pin):
            continue

        # rel_pin_dir
        r_rel_dir = rule.get('rel_pin_dir')
        if r_rel_dir is not None and r_rel_dir != rel_pin_dir:
            continue

        # constr_pin
        if not _match_constr_pin(rule.get('constr_pin'), constr_pin):
            continue

        # constr_pin_dir
        r_constr_dir = rule.get('constr_pin_dir')
        if r_constr_dir is not None and r_constr_dir != constr_pin_dir:
            continue

        # when
        if not _match_when(rule.get('when'), when):
            continue

        # probe
        if not _match_probe(rule.get('probe'), probe_list):
            continue

        # All conditions matched -- first match wins
        return rule.get('template')

    return None
