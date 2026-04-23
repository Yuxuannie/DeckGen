"""collateral.py - CollateralStore loads manifest.json and serves lookups.

Every lookup failure raises CollateralError with actionable suggestions.
"""

import json
import os

from core.resolver import ResolutionError
from core.parsers.chartcl_helpers import parse_chartcl_for_inc


class CollateralError(ResolutionError):
    """Lookup failure. Always carries suggestions."""
    pass


# Arc-type normalization table for model-file lookup (MCQC parity with
# hybrid_char_helper.parse_chartcl_for_inc consumers).
_ARC_TYPE_NORMALIZATION = {
    'min_pulse_width':      'mpw',
    'mpw':                  'mpw',
    'combinational':        'delay',
    'edge':                 'delay',
    'combinational_rise':   'delay',
    'combinational_fall':   'delay',
    'rising_edge':          'delay',
    'falling_edge':         'delay',
    'three_state_enable':   'delay',
    'three_state_disable':  'delay',
    'clear':                'delay',
    'preset':               'delay',
}

# Arc types considered "constraint" for char*.tcl picking
_CONSTRAINT_ARC_TYPES = frozenset({
    'hold', 'setup', 'removal', 'recovery',
    'non_seq_hold', 'non_seq_setup',
    'mpw', 'min_pulse_width', 'si_immunity',
    'nochange_low_low', 'nochange_low_high',
    'nochange_high_low', 'nochange_high_high',
})


def _normalize_arc_type(arc_type):
    if arc_type.startswith('nochange'):
        return 'nochange'
    return _ARC_TYPE_NORMALIZATION.get(arc_type, arc_type)


def _closest_matches(needle, haystack, n=10):
    """Naive substring-first, then prefix, then sorted list."""
    sub = [h for h in haystack if needle in h]
    pre = [h for h in haystack if h not in sub and h.startswith(needle[:5])]
    return (sub + pre + sorted(haystack))[:n]


class CollateralStore:
    """Load manifest.json for one (node, lib_type) leaf and serve lookups."""

    def __init__(self, collateral_root, node, lib_type):
        self.collateral_root = os.path.abspath(collateral_root)
        self.node = node
        self.lib_type = lib_type
        self.leaf = os.path.join(self.collateral_root, node, lib_type)
        self.manifest_path = os.path.join(self.leaf, 'manifest.json')
        self.manifest = self._load()

    def _load(self):
        if not os.path.isfile(self.manifest_path):
            # Try to generate it on the fly
            self._rescan()
            if not os.path.isfile(self.manifest_path):
                raise CollateralError(
                    f"manifest.json not found at {self.manifest_path}\n"
                    f"  x Run: python3 tools/scan_collateral.py "
                    f"--node {self.node} --lib_type {self.lib_type}")

        # Staleness check: if any subdir is newer, regenerate
        if self._is_stale():
            self._rescan()

        with open(self.manifest_path) as f:
            return json.load(f)

    def _is_stale(self):
        if not os.path.isfile(self.manifest_path):
            return True
        m_mtime = os.path.getmtime(self.manifest_path)
        for sub in ('Char', 'Template', 'Netlist'):
            d = os.path.join(self.leaf, sub)
            if os.path.isdir(d) and os.path.getmtime(d) > m_mtime:
                return True
        return False

    def _rescan(self):
        # Local import to avoid circular dependency
        from tools.scan_collateral import build_manifest
        build_manifest(self.collateral_root, self.node, self.lib_type)

    # -- listing ------------------------------------------------------------

    def list_corners(self):
        return sorted(self.manifest.get('corners', {}).keys())

    def list_cells(self):
        return sorted(self.manifest.get('cells', {}).keys())

    # -- corner lookup ------------------------------------------------------

    def _abs(self, rel):
        if rel is None:
            return None
        if os.path.isabs(rel):
            return rel
        return os.path.abspath(os.path.join(self.leaf, rel))

    def get_corner(self, corner_name):
        """Return manifest corner entry with paths resolved to absolute."""
        corners = self.manifest.get('corners', {})
        if corner_name not in corners:
            suggestions = _closest_matches(corner_name, list(corners.keys()))
            raise CollateralError(
                f"No corner '{corner_name}' in node '{self.node}' "
                f"/ lib_type '{self.lib_type}'\n"
                f"  x Closest matches:\n" +
                ''.join(f"  x   - {s}\n" for s in suggestions) +
                f"  x Manifest: {self.manifest_path}")

        entry = corners[corner_name]
        resolved = dict(entry)

        char = dict(entry['char'])
        for k in char:
            char[k] = self._abs(char[k])
        resolved['char'] = char

        model = dict(entry['model'])
        for k in model:
            model[k] = self._abs(model[k])
        resolved['model'] = model

        resolved['usage_l']      = self._abs(entry.get('usage_l'))
        resolved['template_tcl'] = self._abs(entry.get('template_tcl'))
        resolved['netlist_dir']  = self._abs(entry.get('netlist_dir'))

        return resolved

    # -- specialized pickers ------------------------------------------------

    def pick_char_file(self, corner_name, arc_type):
        """Pick the correct char*.tcl file for this (corner, arc_type).

        Precedence:
          1. combined (corner-specific)
          2. cons (constraint arc) / non_cons (non-cons arc)
          3. group_combined
          4. group_cons / group_non_cons
        """
        c = self.get_corner(corner_name)['char']
        if c.get('combined'):
            return c['combined']

        want_cons = arc_type in _CONSTRAINT_ARC_TYPES
        primary = c.get('cons') if want_cons else c.get('non_cons')
        if primary:
            return primary

        if c.get('group_combined'):
            return c['group_combined']

        group_primary = c.get('group_cons') if want_cons else c.get('group_non_cons')
        return group_primary  # may be None

    def pick_model_file(self, corner_name, arc_type):
        """Resolve INCLUDE_FILE via chartcl extsim_model_include (MCQC exact).

        Steps:
          1. Pick char*.tcl file for this (corner, arc_type)
          2. parse_chartcl_for_inc -> {'traditional': path, 'hold': path, ...}
          3. Normalize arc_type (mpw/min_pulse_width->'mpw', etc.)
          4. Return lookup[normalized]
          5. If missing AND lookup has exactly 1 entry -> lookup['traditional']
        """
        char_file = self.pick_char_file(corner_name, arc_type)
        if not char_file or not os.path.isfile(char_file):
            return None
        inc = parse_chartcl_for_inc(char_file)
        if not inc:
            return None

        key = _normalize_arc_type(arc_type)
        if key in inc:
            return inc[key]

        if len(inc) == 1 and 'traditional' in inc:
            return inc['traditional']

        return None

    def get_usage_l(self, corner_name):
        return self.get_corner(corner_name).get('usage_l')

    def get_template_tcl(self, corner_name):
        path = self.get_corner(corner_name).get('template_tcl')
        if path is None:
            raise CollateralError(
                f"No template.tcl for corner '{corner_name}' in "
                f"{self.node}/{self.lib_type}")
        return path

    def get_netlist_dir(self, corner_name):
        return self.get_corner(corner_name).get('netlist_dir')
