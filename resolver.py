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

    def __init__(self, registry_path, templates_dir):
        self.templates_dir = templates_dir
        self.registry = load_yaml(registry_path)
        self.entries = self.registry.get('templates', [])

    def resolve(self, cell_name, arc_type, rel_pin, rel_dir, constr_dir=None):
        """Find the best matching template for the given arc specification.

        Returns:
            str: Absolute path to the template .sp file.

        Raises:
            ResolutionError: With details on why no match was found + closest matches.
        """
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
            # Check if arc_type matched but cell didn't — partial match
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
            msg += f"  ✗ {err}\n"
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
