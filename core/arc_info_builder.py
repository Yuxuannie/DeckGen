"""arc_info_builder.py - Compose MCQC-parity arc_info dict for non-cons arcs.

Faithful port of the non-cons-arc subset of parseQACharacteristicsInfo from
1-general/timingArcInfo/funcs.py.

Deferred to Point 2b:
  - 3D constraint expansion (5x5x5 -> 3 decks)
  - define_index override matching
  - SIS template {PINTYPE}_GLITCH_HIGH/LOW_THRESHOLD fields
  - Per-arc metric/metric_thresh extraction
  - MPW-only fields (MPW_INPUT_THRESHOLD)
"""

import re as _re

from core.parsers.chartcl import resolve_chartcl_for_arc


# Arc-type classification (MCQC parity)
_CONSTRAINT_ARC_TYPES = frozenset({
    'hold', 'setup', 'removal', 'recovery',
    'non_seq_hold', 'non_seq_setup', 'si_immunity',
})


def format_index_value(numeric_value, unit_suffix):
    """Format an index numeric value with a unit suffix.

    MCQC parity: trailing '.0' stripped (1.0 -> '1n', 0.05 -> '0.05n').
    """
    # Prefer shortest representation
    if numeric_value == int(numeric_value):
        return f"{int(numeric_value)}{unit_suffix}"
    # Strip trailing zeros from decimal part
    s = f"{numeric_value:.10g}"
    return f"{s}{unit_suffix}"


def _pick_template_for_arc(cell_info, arc_type):
    """Select which lu_table_template backs this arc (MCQC parity)."""
    if arc_type in _CONSTRAINT_ARC_TYPES or arc_type.startswith('nochange'):
        return cell_info.get('constraint_template')
    if arc_type in ('mpw', 'min_pulse_width'):
        return cell_info.get('mpw_template')
    if arc_type == 'si_immunity':
        return cell_info.get('si_immunity_template')
    # else: delay / combinational / edge / three_state / clear / preset
    return cell_info.get('delay_template')


def _index_2_unit_suffix(arc_type):
    """MCQC parity: INDEX_2_VALUE uses 'p' for non-cons load, 'n' for
    constraint slew."""
    if arc_type in _CONSTRAINT_ARC_TYPES or arc_type.startswith('nochange'):
        return 'n'
    return 'p'


def _build_header_info(arc, cell_info, arc_type, index_1_list, index_2_list,
                       max_slew, output_load):
    """Generate MCQC-format pipe-delimited header string.

    Example: CELL DFFQ1 | REL_PIN CP | REL_PIN_DIR fall | CONSTR_PIN E |
             CONSTR_PIN_DIR fall | OUTPUT_PINS Q | PROBE_PIN_1 Q |
             OUTPUT_LOAD 0.000558 | ...
    """
    parts = [
        f"CELL {arc.get('cell', '')}",
        f"REL_PIN {arc.get('rel_pin', '')}",
        f"REL_PIN_DIR {arc.get('rel_pin_dir', '')}",
        f"CONSTR_PIN {arc.get('pin', '') or arc.get('rel_pin', '')}",
        f"CONSTR_PIN_DIR {arc.get('pin_dir', '') or arc.get('rel_pin_dir', '')}",
        f"OUTPUT_PINS {' '.join(cell_info.get('output_pins', []))}",
        f"PROBE_PIN_1 {(arc.get('probe_list') or [''])[0]}",
        f"WHEN {arc.get('when', '')}",
        f"OUTPUT_LOAD {output_load}",
    ]
    if index_1_list:
        parts.append(f"REL_PIN_SLEWS {' '.join(str(v) for v in index_1_list)}")
    if index_2_list:
        parts.append(f"CONSTR_PIN_SLEWS {' '.join(str(v) for v in index_2_list)}")
    parts.append(f"MAX_SLEW {max_slew}")
    parts.append(f"ARC_TYPE {arc_type}")
    parts.append(f"VECTOR {arc.get('vector', '')}")
    pinlist = cell_info.get('pinlist', '')
    if pinlist:
        parts.append(f"TEMPLATE_PINLIST {pinlist}")
    return ' | '.join(parts)


def build_arc_info(arc, cell_info, template_info, chartcl, corner,
                   netlist_path, netlist_pins, include_file, waveform_file,
                   overrides=None):
    """Compose the complete arc_info dict for a non-cons arc."""
    overrides = overrides or {}
    cell_name = arc['cell']
    arc_type  = arc['arc_type']

    # --- Index lookup ----------------------------------------------------
    template_name = _pick_template_for_arc(cell_info, arc_type)
    tpl = template_info['templates'].get(template_name, {}) if template_name else {}
    index_1_list = tpl.get('index_1', []) or template_info['global'].get('index_1', [])
    index_2_list = tpl.get('index_2', []) or template_info['global'].get('index_2', [])

    # Honor define_index override if one matches this (cell, pin, rel_pin, when)
    from core.parsers.template_tcl import find_define_index_override
    _di_override = find_define_index_override(
        template_info.get('index_overrides', []),
        cell=cell_name,
        pin=arc.get('pin', ''),
        rel_pin=arc.get('rel_pin', ''),
        when=arc.get('when', ''),
    )
    if _di_override:
        if _di_override.get('index_1'):
            index_1_list = _di_override['index_1']
        if _di_override.get('index_2'):
            index_2_list = _di_override['index_2']

    idx1 = overrides.get('index_1_index')
    idx2 = overrides.get('index_2_index')

    def _val(lst, idx, unit):
        if idx is None or not lst or idx < 1 or idx > len(lst):
            return ''
        return format_index_value(lst[idx - 1], unit)

    index_1_value = _val(index_1_list, idx1, 'n')
    index_2_value = _val(index_2_list, idx2, _index_2_unit_suffix(arc_type))

    # max_slew: MCQC uses max(max(index_1), max(index_2)) for constraint arcs
    max_vals = []
    if index_1_list:
        max_vals.append(max(index_1_list))
    if index_2_list and (arc_type in _CONSTRAINT_ARC_TYPES or arc_type.startswith('nochange')):
        max_vals.append(max(index_2_list))
    max_slew = format_index_value(max(max_vals), 'n') if max_vals else ''

    # --- chartcl-derived fields -----------------------------------------
    chart = resolve_chartcl_for_arc(chartcl, cell_name, arc_type) if chartcl else {
        'GLITCH': '', 'PUSHOUT_PER': '', 'OUTPUT_LOAD_INDEX': None,
    }

    # --- output_load (MCQC: index_2[load_index] from DELAY template) ----
    # MCQC default: load_index=2 (3rd element, 0-based) of the DELAY
    # template's index_2 list. chartcl can override per cell.
    output_load = ''
    ol_idx = chart.get('OUTPUT_LOAD_INDEX')
    if ol_idx is None:
        # MCQC default: use delay template's index_2, entry at index 2 (3rd)
        delay_tmpl_name = cell_info.get('delay_template')
        delay_tmpl = template_info['templates'].get(delay_tmpl_name, {}) if delay_tmpl_name else {}
        delay_idx2 = delay_tmpl.get('index_2', []) or template_info['global'].get('index_2', [])
        if len(delay_idx2) > 2:
            output_load = format_index_value(delay_idx2[2], 'p')
        elif delay_idx2:
            output_load = format_index_value(delay_idx2[-1], 'p')
    else:
        try:
            ol_idx_int = int(ol_idx)
            if 1 <= ol_idx_int <= len(index_2_list):
                output_load = format_index_value(
                    index_2_list[ol_idx_int - 1],
                    _index_2_unit_suffix(arc_type))
        except (ValueError, TypeError):
            pass

    # --- environment (overrides win) ------------------------------------
    vdd  = overrides.get('vdd')         or corner.get('vdd', '')
    temp = overrides.get('temperature') or corner.get('temperature', '')

    # --- probe pins -----------------------------------------------------
    probe = arc.get('probe_list', [])
    probe_fields = {}
    for i, name in enumerate(probe, start=1):
        probe_fields[f'PROBE_PIN_{i}'] = name
    probe_fields.setdefault('PROBE_PIN_1', '')

    # --- compose --------------------------------------------------------
    info = {
        # Core arc
        'CELL_NAME':        cell_name,
        'ARC_TYPE':         arc_type,
        'REL_PIN':          arc.get('rel_pin', ''),
        'REL_PIN_DIR':      arc.get('rel_pin_dir', ''),
        # non-cons: CONSTR_PIN mirrors REL_PIN
        'CONSTR_PIN':       arc.get('rel_pin', ''),
        'CONSTR_PIN_DIR':   arc.get('rel_pin_dir', ''),
        'OUTPUT_PINS':      ' '.join(cell_info.get('output_pins', [])),
        'SIDE_PIN_STATES':  '',
        'DONT_TOUCH_PINS':  '',
        'WHEN':             arc.get('when', ''),
        'LIT_WHEN':         arc.get('lit_when', ''),
        'HEADER_INFO':      _build_header_info(arc, cell_info, arc_type, index_1_list, index_2_list, max_slew, output_load),
        'TEMPLATE_PINLIST': cell_info.get('pinlist', ''),
        'VECTOR':           arc.get('vector', ''),

        # Indices
        'INDEX_1_INDEX':    str(idx1) if idx1 is not None else '',
        'INDEX_1_VALUE':    index_1_value,
        'INDEX_2_INDEX':    str(idx2) if idx2 is not None else '',
        'INDEX_2_VALUE':    index_2_value,
        'INDEX_3_INDEX':    '',       # deferred to 2b
        'OUTPUT_LOAD':      output_load,
        'MAX_SLEW':         max_slew,

        # Environment
        'VDD_VALUE':        str(vdd),
        'TEMPERATURE':      str(temp),
        'INCLUDE_FILE':     include_file,
        'WAVEFORM_FILE':    waveform_file,
        'NETLIST_PATH':     netlist_path,
        'NETLIST_PINS':     netlist_pins,

        # Metrics
        'GLITCH':           chart.get('GLITCH')      or '',
        'PUSHOUT_PER':      chart.get('PUSHOUT_PER') or overrides.get('pushout_per', '0.4'),
        'PUSHOUT_DIR':      overrides.get('pushout_dir', ''),

        # Template refs (for debugging / deck_builder)
        'TEMPLATE_DECK':    overrides.get('template_deck', ''),
        'TEMPLATE_TCL':     overrides.get('template_tcl',  ''),

        # 2b hook (not consumed yet)
        '_constraint_is_3d': False,
    }

    # MCQC parity: per-arc metric_thresh overrides all (highest precedence)
    if arc.get('metric') == 'glitch' and arc.get('metric_thresh'):
        info['GLITCH'] = str(arc['metric_thresh']).strip('"')

    info.update(probe_fields)

    # Inject SIS pintype glitch thresholds if the template has a sidecar.
    # Rule (MCQC): for each pin in OUTPUT_PINS, classify as 'O'; for each
    # other pin in TEMPLATE_PINLIST, classify as 'I'. Thresholds from the
    # first matching pintype block go into {PINTYPE}_GLITCH_HIGH/LOW_THRESHOLD.
    sis = template_info.get('sis', {})
    if sis:
        output_pins_list = cell_info.get('output_pins', [])
        if output_pins_list and 'O' in sis:
            info['O_GLITCH_HIGH_THRESHOLD'] = str(sis['O'].get('glitch_high_threshold', ''))
            info['O_GLITCH_LOW_THRESHOLD']  = str(sis['O'].get('glitch_low_threshold',  ''))
        if 'I' in sis:
            info['I_GLITCH_HIGH_THRESHOLD'] = str(sis['I'].get('glitch_high_threshold', ''))
            info['I_GLITCH_LOW_THRESHOLD']  = str(sis['I'].get('glitch_low_threshold',  ''))

    return info


def _is_3d_template(template_name):
    """MCQC parity: template name matches regex '5x5x5'."""
    return bool(template_name and _re.search(r'5x5x5', template_name))


def build_arc_infos(arc, cell_info, template_info, chartcl, corner,
                    netlist_path, netlist_pins, include_file, waveform_file,
                    overrides=None):
    """Build one or more arc_info dicts. Returns a LIST.

    For 3D constraint arcs (template matches '5x5x5'), returns 3 entries
    (indices 1, 2, 3 of index_3 -- endpoints skipped per MCQC).
    For all other arcs, returns a single entry.
    """
    overrides = overrides or {}
    arc_type = arc.get('arc_type', '')

    # Determine if this is a 3D constraint arc
    tpl_name = _pick_template_for_arc(cell_info, arc_type)
    tpl = template_info['templates'].get(tpl_name, {}) if tpl_name else {}
    index_3_list = tpl.get('index_3', [])

    if _is_3d_template(tpl_name) and len(index_3_list) == 5:
        results = []
        for idx3 in (2, 3, 4):  # 1-based indices 2,3,4 => skip 1 and 5
            ov = dict(overrides)
            ov['index_3_index'] = idx3
            info = build_arc_info(
                arc=arc, cell_info=cell_info,
                template_info=template_info, chartcl=chartcl,
                corner=corner,
                netlist_path=netlist_path, netlist_pins=netlist_pins,
                include_file=include_file, waveform_file=waveform_file,
                overrides=ov)
            info['INDEX_3_INDEX'] = str(idx3 - 1)   # MCQC: index at 1,2,3
            info['_deck_suffix']  = f"-{idx3}"
            info['_constraint_is_3d'] = True
            # OUTPUT_LOAD comes from index_3[idx3-1] for 3D
            if 0 < (idx3 - 1) < len(index_3_list):
                info['OUTPUT_LOAD'] = format_index_value(
                    index_3_list[idx3 - 1], 'p')
            results.append(info)
        return results

    # Non-3D: single result
    info = build_arc_info(
        arc=arc, cell_info=cell_info,
        template_info=template_info, chartcl=chartcl,
        corner=corner,
        netlist_path=netlist_path, netlist_pins=netlist_pins,
        include_file=include_file, waveform_file=waveform_file,
        overrides=overrides)
    info['_deck_suffix'] = ''
    return [info]
