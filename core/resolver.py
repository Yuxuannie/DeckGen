"""
resolver.py - Resolves template, netlist, and electrical parameters for deck generation.

Given a (cell, arc_type, PT) specification, resolves:
  - Which SPICE template to use
  - Netlist path for the cell
  - Electrical parameters (VDD, temp, slew, load)
  - Pin list from netlist

Reports EXACTLY what can't be resolved instead of silently dropping arcs.
"""

import os
import re
import sys
import fnmatch
import yaml

from core.template_map import map_to_template


class ResolutionError(Exception):
    """Raised when a required parameter cannot be resolved."""

    def __init__(self, message, suggestions=None):
        super().__init__(message)
        self.suggestions = suggestions or []


def load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)


class TemplateResolver:
    """Resolves cell+arc specification to a SPICE template file."""

    def __init__(self, registry_path, templates_dir, node='N2P_v1.0'):
        self.templates_dir = templates_dir
        self.node = node
        self.registry = load_yaml(registry_path)
        self.entries = self.registry.get('templates', [])

    def resolve(self, cell_name, arc_type, rel_pin, rel_dir, constr_dir=None,
                probe_list=None):
        """Find the best matching template for the given arc specification.

        Returns:
            str: Absolute path to the template .sp file.

        Raises:
            ResolutionError: With details on why no match was found + closest matches.
        """
        # Try node-aware Python if-chain first (MCQC 2-flow/funcs.py port)
        tmap_path = map_to_template(
            cell_name=cell_name,
            arc_type=arc_type,
            rel_pin=rel_pin,
            rel_dir=rel_dir,
            constr_dir=constr_dir,
            probe_list=probe_list or [],
            node=self.node,
            templates_dir=self.templates_dir,
        )
        if tmap_path is not None:
            return tmap_path

        matches = []
        partial_matches = []

        for entry in self.entries:
            score = self._match_score(entry, cell_name, arc_type, rel_pin, rel_dir, constr_dir)
            if score == 0:
                continue
            if score == -1:
                partial_matches.append(entry)
                continue
            matches.append((score, entry))

        if not matches:
            suggestions = self._format_suggestions(partial_matches, cell_name, arc_type)
            raise ResolutionError(
                f"No template match for ({cell_name}, {arc_type}, "
                f"{rel_pin}/{rel_dir}, constr_dir={constr_dir})",
                suggestions=suggestions
            )

        # Highest score wins (most specific match)
        matches.sort(key=lambda x: x[0], reverse=True)
        best = matches[0][1]
        template_path = os.path.join(self.templates_dir, best['template'])

        if not os.path.exists(template_path):
            raise ResolutionError(
                f"Template file not found: {template_path}\n"
                f"  Matched registry entry: pattern={best['pattern']}, "
                f"arc_type={best['arc_type']}"
            )

        return template_path

    def _match_score(self, entry, cell_name, arc_type, rel_pin, rel_dir, constr_dir):
        """Score a registry entry against the request.

        Returns:
            int: >0 = full match (higher = more specific), -1 = partial match, 0 = no match
        """
        # arc_type must match (or entry says "any")
        if entry['arc_type'] != 'any' and entry['arc_type'] != arc_type:
            return 0

        score = 0

        # Cell pattern match
        if not fnmatch.fnmatch(cell_name, entry['pattern']):
            # Check if arc_type matched but cell didn't -- partial match
            return -1
        # More specific patterns score higher
        if entry['pattern'] != '*':
            score += 10

        # rel_pin match
        entry_rel_pin = entry.get('rel_pin', 'any')
        if entry_rel_pin != 'any':
            if entry_rel_pin != rel_pin:
                return -1
            score += 5

        # rel_dir match
        entry_rel_dir = entry.get('rel_dir', 'any')
        if entry_rel_dir != 'any':
            if entry_rel_dir != rel_dir:
                return -1
            score += 3

        # constr_dir match
        entry_constr_dir = entry.get('constr_dir', 'any')
        if entry_constr_dir != 'any' and constr_dir is not None:
            if entry_constr_dir != constr_dir:
                return -1
            score += 2

        return max(score, 1)  # At least 1 for a full match

    def _format_suggestions(self, partial_matches, cell_name, arc_type):
        suggestions = []
        for entry in partial_matches[:5]:
            suggestions.append(
                f"  - pattern={entry['pattern']} arc_type={entry['arc_type']} "
                f"rel_pin={entry.get('rel_pin','any')}/{entry.get('rel_dir','any')} "
                f"constr_dir={entry.get('constr_dir','any')} "
                f"-> {entry['template']}"
            )
        if not suggestions:
            suggestions.append(
                f"  No entries for arc_type={arc_type} in the registry."
            )
            suggestions.append(
                f"  Use --template /path/to/your.sp to provide a template directly."
            )
        return suggestions

    def list_matches(self, cell_name, arc_type=None):
        """List all registry entries that match a cell name (for debugging)."""
        results = []
        for entry in self.entries:
            if arc_type and entry['arc_type'] != arc_type:
                continue
            if fnmatch.fnmatch(cell_name, entry['pattern']):
                results.append(entry)
        return results


class NetlistResolver:
    """Resolves cell name to LPE netlist path and extracts pin list."""

    # Netlist filename priority (same as MCQC)
    NETLIST_SUFFIXES = ['_c_qa.spi', '_c.spi', '.spi', '.sp', '.spice']

    def __init__(self, netlist_dir):
        self.netlist_dir = netlist_dir

    def resolve(self, cell_name):
        """Find the netlist file for a cell and extract its pin list.

        Returns:
            tuple: (netlist_path, pin_list_str)

        Raises:
            ResolutionError: If netlist not found, listing what was tried.
        """
        tried = []
        for suffix in self.NETLIST_SUFFIXES:
            candidate = os.path.join(self.netlist_dir, cell_name + suffix)
            tried.append(candidate)
            if os.path.exists(candidate):
                pins = self._extract_pins(candidate, cell_name)
                return candidate, pins

        raise ResolutionError(
            f"No netlist found for cell '{cell_name}' in {self.netlist_dir}\n"
            f"  Tried: {', '.join(os.path.basename(t) for t in tried)}\n"
            f"  Use --netlist /path/to/cell.spice to provide it directly."
        )

    def _extract_pins(self, netlist_path, cell_name):
        """Extract pin list from .subckt line in netlist."""
        with open(netlist_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped.lower().startswith('.subckt'):
                    parts = stripped.split()
                    # .subckt CELL_NAME pin1 pin2 ...
                    if len(parts) >= 2:
                        # Return pins only (skip .subckt and cell name)
                        pins = ' '.join(parts[2:])
                        return pins
        raise ResolutionError(
            f"Could not find .subckt line in netlist: {netlist_path}\n"
            f"  Provide pin list manually with --pins 'VDD VSS A Y'"
        )


class CornerResolver:
    """Resolves PVT corner parameters from corner config or CLI overrides."""

    REQUIRED_FIELDS = ['vdd', 'temperature', 'model_file', 'waveform_file']

    def __init__(self, corner_config=None):
        self.config = {}
        if corner_config:
            self.config = load_yaml(corner_config)

    def resolve(self, cli_overrides=None):
        """Merge corner config with CLI overrides and validate.

        Args:
            cli_overrides: dict of field -> value from CLI args

        Returns:
            dict: Resolved corner parameters

        Raises:
            ResolutionError: Lists exactly which required fields are missing.
        """
        params = dict(self.config)
        if cli_overrides:
            for k, v in cli_overrides.items():
                if v is not None:
                    params[k] = v

        missing = [f for f in self.REQUIRED_FIELDS if not params.get(f)]
        if missing:
            raise ResolutionError(
                f"Missing required corner parameters: {', '.join(missing)}\n"
                f"  Provide via corner config (--corner_config file.yaml) or CLI:\n"
                + '\n'.join(f"    --{f} <value>" for f in missing)
            )

        return params


def resolve_all(cell_name, arc_type, rel_pin, rel_dir, constr_pin, constr_dir,
                probe_pin, registry_path, templates_dir, netlist_dir=None,
                corner_config=None, cli_overrides=None, template_override=None,
                netlist_override=None, pins_override=None):
    """Main resolution entry point. Resolves everything needed for deck generation.

    Returns:
        dict: All resolved parameters (arc_info-compatible dict)

    Raises:
        ResolutionError: With specific, actionable error message
    """
    errors = []

    # 1. Resolve template
    template_path = None
    if template_override:
        if not os.path.exists(template_override):
            errors.append(f"Template file not found: {template_override}")
        else:
            template_path = template_override
    else:
        try:
            resolver = TemplateResolver(registry_path, templates_dir)
            template_path = resolver.resolve(cell_name, arc_type, rel_pin, rel_dir, constr_dir)
        except ResolutionError as e:
            errors.append(str(e))
            if e.suggestions:
                errors.append("Closest matches:")
                errors.extend(e.suggestions)

    # 2. Resolve netlist
    netlist_path = None
    netlist_pins = None
    if netlist_override:
        netlist_path = netlist_override
        if pins_override:
            netlist_pins = pins_override
        elif os.path.exists(netlist_override):
            try:
                nr = NetlistResolver(os.path.dirname(netlist_override))
                _, netlist_pins = nr.resolve(
                    os.path.splitext(os.path.basename(netlist_override))[0]
                )
            except ResolutionError:
                netlist_pins = pins_override  # Will be caught below if None
    elif netlist_dir:
        try:
            nr = NetlistResolver(netlist_dir)
            netlist_path, netlist_pins = nr.resolve(cell_name)
        except ResolutionError as e:
            errors.append(str(e))
    else:
        errors.append(
            "No netlist source specified.\n"
            "  Use --netlist /path/to/cell.spice or --netlist_dir /path/to/netlists/"
        )

    if pins_override:
        netlist_pins = pins_override

    # 3. Resolve corner parameters
    try:
        cr = CornerResolver(corner_config)
        corner_params = cr.resolve(cli_overrides)
    except ResolutionError as e:
        errors.append(str(e))
        corner_params = {}

    # Report all errors at once
    if errors:
        msg = f"Cannot generate deck for {cell_name} / {arc_type} / {rel_pin}->{constr_pin}:\n"
        for err in errors:
            msg += f"  x {err}\n"
        raise ResolutionError(msg)

    # Build the resolved arc_info dict
    arc_info = {
        'CELL_NAME': cell_name,
        'ARC_TYPE': arc_type,
        'REL_PIN': rel_pin,
        'REL_PIN_DIR': rel_dir,
        'CONSTR_PIN': constr_pin,
        'CONSTR_PIN_DIR': constr_dir or '',
        'PROBE_PIN_1': probe_pin or '',
        'TEMPLATE_DECK_PATH': template_path,
        'NETLIST_PATH': netlist_path,
        'NETLIST_PINS': netlist_pins or '',
        'VDD_VALUE': str(corner_params.get('vdd', '')),
        'TEMPERATURE': str(corner_params.get('temperature', '')),
        'INCLUDE_FILE': corner_params.get('model_file', ''),
        'WAVEFORM_FILE': corner_params.get('waveform_file', ''),
        'PUSHOUT_PER': str(corner_params.get('pushout_per', '0.4')),
        'NUM_SAMPLES': corner_params.get('num_samples', 5000),
    }

    return arc_info


def resolve_all_from_collateral(
    cell_name, arc_type, rel_pin, rel_dir, constr_pin, constr_dir, probe_pin,
    node, lib_type, corner_name,
    collateral_root='collateral',
    overrides=None,
    template_override=None,
    netlist_override=None,
    pins_override=None,
    waveform_override=None,
):
    """Non-cons orchestrator: pull everything from the collateral manifest.

    This is the new MCQC-parity entry point. Existing resolve_all() stays
    unchanged for the legacy single-arc CLI path.
    """
    from core.collateral import CollateralStore, CollateralError
    from core.parsers.chartcl import chartcl_parse_all
    from core.parsers.template_tcl import parse_template_tcl_full
    from core.arc_info_builder import build_arc_infos

    overrides = overrides or {}

    # 1. Load store + corner
    store = CollateralStore(collateral_root, node, lib_type)
    corner = store.get_corner(corner_name)

    # 2. Parse template.tcl (full)
    tpl_tcl_path = corner['template_tcl']
    if not tpl_tcl_path or not os.path.isfile(tpl_tcl_path):
        raise CollateralError(
            f"No template.tcl for corner '{corner_name}'")
    template_info = parse_template_tcl_full(tpl_tcl_path)

    # 3. Parse char*.tcl for this arc_type
    char_path = store.pick_char_file(corner_name, arc_type)
    if char_path and os.path.isfile(char_path):
        variant = 'mpw' if arc_type in ('mpw', 'min_pulse_width') else 'general'
        chartcl = chartcl_parse_all(char_path, variant=variant)
    else:
        chartcl = None

    # 4. Resolve model file (.inc) via chartcl, with fallback to corner model dict
    include_file = store.pick_model_file(corner_name, arc_type) or ''
    if not include_file:
        # Fallback: try corner's model dict directly
        model = corner.get('model', {})
        from core.collateral import _normalize_arc_type
        norm = _normalize_arc_type(arc_type)
        include_file = model.get(norm, '') or model.get('traditional', '') or ''
    import sys
    print(f"[resolver] model .inc for {arc_type}/{corner_name}: {include_file!r}", file=sys.stderr)

    # 5. Find the matching arc entry in template_info
    arc = _find_matching_arc(template_info, cell_name, arc_type,
                             rel_pin, rel_dir)
    if arc is None:
        raise ResolutionError(
            f"No matching arc in template.tcl for cell={cell_name} "
            f"arc_type={arc_type} rel_pin={rel_pin}/{rel_dir}")

    cell_info = template_info['cells'].get(cell_name, {
        'pinlist': '', 'output_pins': [],
        'delay_template': None, 'constraint_template': None,
        'mpw_template': None, 'si_immunity_template': None,
    })

    # 6. Netlist
    if netlist_override:
        netlist_path = netlist_override
        netlist_pins = pins_override or _extract_pins_safe(netlist_override)
    else:
        netlist_dir = corner.get('netlist_dir')
        if netlist_dir:
            try:
                nr = NetlistResolver(netlist_dir)
                netlist_path, netlist_pins = nr.resolve(cell_name)
            except ResolutionError:
                netlist_path = ''
                netlist_pins = pins_override or ''
        else:
            netlist_path = ''
            netlist_pins = pins_override or ''

    # 7. Waveform
    # Waveform: from overrides, or corner's usage_l, or MCQC standard path
    waveform_file = waveform_override or overrides.get('waveform_file', '')
    if not waveform_file:
        waveform_file = '/CAD/stdcell/DesignKits/Sponsor/Script/MCQC_automation/Template/std_wv_c651.spi'

    # 7b. SPICE template (deck) -- try delay rules, then MCQC JSON rules, then registry
    template_deck_path = template_override or ''
    if not template_deck_path:
        # Probe pin is the output/constrained pin for delay arcs
        probe_pin = arc.get('pin', '') or (cell_info.get('output_pins', [''])[0] if cell_info.get('output_pins') else '')

        # Try delay-specific rules first (hack_template_v2)
        from config.delay_template_rules import get_delay_template
        tmpl_rel = get_delay_template(
            cell_name=cell_name, arc_type=arc_type,
            constr_pin=probe_pin, constr_pin_dir=constr_dir,
            rel_pin=rel_pin, rel_pin_dir=rel_dir,
            when=arc.get('when', ''))

        # Then try MCQC JSON rules (hold/setup/mpw/etc.)
        if not tmpl_rel:
            from core.template_rules import match_template
            probe_list_val = arc.get('probe_list', [])
            tmpl_rel = match_template(
                cell_name=cell_name, arc_type=arc_type,
                rel_pin=rel_pin, rel_pin_dir=rel_dir,
                constr_pin=constr_pin, constr_pin_dir=constr_dir,
                probe_list=probe_list_val, when=arc.get('when', ''))

        if tmpl_rel:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            templates_dir = os.path.normpath(
                os.path.join(script_dir, '..', 'templates'))
            for base in [
                os.path.join(templates_dir, node) if node else None,
                templates_dir,
            ]:
                if base is None:
                    continue
                candidate = os.path.join(base, tmpl_rel)
                if os.path.isfile(candidate):
                    template_deck_path = candidate
                    break
    # Fallback to old TemplateResolver (registry + map) if rules didn't match
    if not template_deck_path:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        registry_path = os.path.normpath(
            os.path.join(script_dir, '..', 'config', 'template_registry.yaml'))
        templates_dir = os.path.normpath(
            os.path.join(script_dir, '..', 'templates'))
        try:
            tpl = TemplateResolver(registry_path, templates_dir, node=node)
            template_deck_path = tpl.resolve(
                cell_name, arc_type, rel_pin, rel_dir, constr_dir)
        except ResolutionError:
            template_deck_path = ''

    # 8. Hand off to arc_info_builder (may return 1 or 3 dicts for 3D arcs)
    results = build_arc_infos(
        arc=arc, cell_info=cell_info,
        template_info=template_info, chartcl=chartcl,
        corner=corner,
        netlist_path=netlist_path, netlist_pins=netlist_pins,
        include_file=include_file, waveform_file=waveform_file,
        overrides=overrides)

    # Stamp TEMPLATE_DECK_PATH onto every result so deck_builder/writer can
    # load + substitute the SPICE template file.
    for r in results:
        r['TEMPLATE_DECK_PATH'] = template_deck_path
        r['TEMPLATE_DECK'] = template_deck_path
    # Backward-compat: return a single dict when only one result
    if len(results) == 1:
        return results[0]
    return results


def _find_matching_arc(template_info, cell_name, arc_type, rel_pin, rel_dir):
    """Scan template_info['arcs'] for a match on (cell, arc_type, rel_pin, rel_dir)."""
    for arc in template_info.get('arcs', []):
        if (arc.get('cell') == cell_name
                and arc.get('arc_type') == arc_type
                and arc.get('rel_pin') == rel_pin
                and arc.get('rel_pin_dir') == rel_dir):
            return arc
    return None


def _extract_pins_safe(netlist_path):
    try:
        nr = NetlistResolver(os.path.dirname(netlist_path))
        stem = os.path.splitext(os.path.basename(netlist_path))[0]
        for s in ('_c_qa', '_c'):
            if stem.endswith(s):
                stem = stem[:-len(s)]
                break
        _, pins = nr.resolve(stem)
        return pins
    except ResolutionError:
        return ''
