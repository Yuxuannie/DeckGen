"""
batch.py - Batch deck generation for N arcs x M corners.

Two-phase design:
  1. plan_jobs()   - resolve all arc x corner combos into job dicts (no I/O)
  2. execute_jobs() - build and write decks using ThreadPoolExecutor
  3. run_batch()   - convenience wrapper: plan + execute
"""

import os
import concurrent.futures

from core.parsers.arc import parse_arc_identifier
from core.parsers.corner import parse_corner_name
from core.parsers.template_tcl import parse_template_tcl, lookup_slew_load
from core.resolver import resolve_all, ResolutionError, TemplateResolver, NetlistResolver
from core.deck_builder import build_deck, build_mc_deck
from core.writer import write_deck, get_deck_dirname


# Arc types where index_1 = constrained-pin slew, index_2 = related-pin slew
CONSTRAINT_ARC_TYPES = frozenset({
    'hold', 'setup', 'removal', 'recovery', 'non_seq_hold', 'non_seq_setup'
})

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REGISTRY_PATH = os.path.normpath(
    os.path.join(_SCRIPT_DIR, '..', 'config', 'template_registry.yaml'))
_TEMPLATES_DIR = os.path.normpath(
    os.path.join(_SCRIPT_DIR, '..', 'templates'))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_jobs(arc_ids, corner_names, files, overrides=None,
              node=None, lib_type=None, collateral_root='collateral'):
    """Resolve all arc x corner combinations into a job list without writing files.

    Args:
        arc_ids:      list of cell_arc_pt identifier strings
        corner_names: list of corner name strings
        files:        dict with keys: netlist_dir, model, waveform, template_tcl_dir
        overrides:    dict with optional: vdd, temperature, slew, load, max_slew,
                      constr_pin, constr_dir

    Returns:
        (jobs, errors)
        jobs: list of job dicts, each with keys:
            id, arc_id, cell, arc_type, probe_pin, probe_dir, rel_pin, rel_dir,
            when, i1, i2, constr_pin, constr_dir, corner, vdd, temperature,
            template, constr_slew, rel_slew, output_load, max_slew,
            netlist, netlist_pins, warnings, error
        errors: list of fatal error strings (bad arc/corner syntax etc.)
    """
    overrides = overrides or {}
    if node and lib_type:
        return _plan_jobs_from_collateral(
            arc_ids, corner_names, node, lib_type,
            collateral_root, overrides)
    files = files or {}

    try:
        tpl_resolver = TemplateResolver(_REGISTRY_PATH, _TEMPLATES_DIR)
    except Exception as e:
        return [], [f"Failed to load template registry: {e}"]

    tcl_cache = {}   # path -> parsed tcl data
    jobs = []
    errors = []
    job_id = 0

    for arc_id in arc_ids:
        arc_id = arc_id.strip()
        if not arc_id:
            continue

        arc = parse_arc_identifier(arc_id)
        if arc is None:
            errors.append(f"Cannot parse arc identifier: {arc_id!r}")
            continue

        for corner_name in corner_names:
            corner_name = corner_name.strip()
            if not corner_name:
                continue

            corner = parse_corner_name(corner_name)
            if corner is None:
                errors.append(f"Cannot parse corner name: {corner_name!r}")
                continue

            job_id += 1
            is_constraint = arc['arc_type'] in CONSTRAINT_ARC_TYPES

            job = {
                'id': job_id,
                'arc_id': arc_id,
                'cell': arc['cell_name'],
                'arc_type': arc['arc_type'],
                'probe_pin': arc['probe_pin'],
                'probe_dir': arc['probe_dir'],
                'rel_pin': arc['rel_pin'],
                'rel_dir': arc['rel_dir'],
                # For constraint arcs constr_dir is opposite of rel_dir by convention
                'constr_pin': overrides.get('constr_pin', arc['rel_pin']),
                'constr_dir': overrides.get('constr_dir',
                                            _opposite_dir(arc['rel_dir'])
                                            if is_constraint else arc['rel_dir']),
                'when': arc['when'],
                'i1': arc['i1'],
                'i2': arc['i2'],
                'corner': corner_name,
                'vdd': overrides.get('vdd') or corner['vdd'],
                'temperature': overrides.get('temperature') or corner['temperature'],
                'template': None,
                'constr_slew': None,
                'rel_slew': None,
                'output_load': None,
                'max_slew': None,
                'netlist': None,
                'netlist_pins': None,
                'warnings': [],
                'error': None,
            }

            # --- Template resolution ---
            try:
                abs_tpl = tpl_resolver.resolve(
                    arc['cell_name'], arc['arc_type'],
                    arc['rel_pin'], arc['rel_dir'],
                    job['constr_dir']
                )
                job['template'] = os.path.relpath(abs_tpl, _TEMPLATES_DIR)
            except ResolutionError as e:
                job['error'] = str(e)
                jobs.append(job)
                continue

            # --- Slew / load from template.tcl ---
            tcl_dir = files.get('template_tcl_dir', '')
            if tcl_dir:
                tcl_path = _find_tcl(tcl_dir, corner_name)
                if tcl_path:
                    if tcl_path not in tcl_cache:
                        try:
                            tcl_cache[tcl_path] = parse_template_tcl(tcl_path)
                        except Exception as ex:
                            job['warnings'].append(
                                f"Could not parse {tcl_path}: {ex}")
                    if tcl_path in tcl_cache:
                        sl = lookup_slew_load(
                            tcl_cache[tcl_path], arc['i1'], arc['i2'],
                            arc_type=arc['arc_type'])
                        job['constr_slew'] = sl.get('constr_pin_slew')
                        job['rel_slew'] = sl.get('rel_pin_slew')
                        job['output_load'] = sl.get('output_load')
                        job['max_slew'] = sl.get('max_slew')
                else:
                    job['warnings'].append(
                        f"No template.tcl found for corner {corner_name!r} "
                        f"in {tcl_dir}")

            # Manual overrides win over auto-filled values
            if overrides.get('slew'):
                job['constr_slew'] = overrides['slew']
                job['rel_slew'] = overrides['slew']
            if overrides.get('load'):
                job['output_load'] = overrides['load']
            if overrides.get('max_slew'):
                job['max_slew'] = overrides['max_slew']

            # --- Netlist resolution ---
            netlist_file = files.get('netlist', '')
            netlist_dir = files.get('netlist_dir', '')
            if netlist_file:
                job['netlist'] = netlist_file
                try:
                    nr = NetlistResolver(os.path.dirname(netlist_file))
                    cell_stem = os.path.splitext(os.path.basename(netlist_file))[0]
                    _, pins = nr.resolve(cell_stem)
                    job['netlist_pins'] = pins
                except ResolutionError:
                    pass
            elif netlist_dir:
                try:
                    nr = NetlistResolver(netlist_dir)
                    path, pins = nr.resolve(arc['cell_name'])
                    job['netlist'] = path
                    job['netlist_pins'] = pins
                except ResolutionError as e:
                    job['warnings'].append(str(e))

            jobs.append(job)

    return jobs, errors


def execute_jobs(jobs, output_dir, nominal_only=False, num_samples=5000, files=None):
    """Build and write decks for a list of planned jobs.

    Args:
        jobs:         list of job dicts from plan_jobs()
        output_dir:   base output directory
        nominal_only: skip MC deck generation
        num_samples:  Monte Carlo sample count
        files:        dict with model/waveform paths

    Returns:
        list of result dicts (sorted by id):
          {id, success, nominal, mc, error}
    """
    files = files or {}

    def _run_one(job):
        if job.get('error'):
            return {'id': job['id'], 'success': False,
                    'nominal': None, 'mc': None, 'error': job['error']}
        try:
            # Collateral-backed jobs already carry a fully-resolved arc_info;
            # legacy jobs have only field-level data, so reconstruct there.
            if job.get('arc_info'):
                arc_info = job['arc_info']
                slew = (arc_info.get('INDEX_1_VALUE') or '0',
                        arc_info.get('INDEX_1_VALUE') or '0')
                load = arc_info.get('OUTPUT_LOAD') or '0'
                max_slew = arc_info.get('MAX_SLEW') or '0'
                when = arc_info.get('WHEN', 'NO_CONDITION')
            else:
                arc_info = _job_to_arc_info(job, files)
                slew = (job.get('constr_slew') or '0',
                        job.get('rel_slew') or '0')
                load = job.get('output_load') or '0'
                max_slew = job.get('max_slew')
                when = job.get('when', 'NO_CONDITION')

            nominal_lines = build_deck(arc_info, slew=slew, load=load,
                                       when=when, max_slew=max_slew)

            deck_suffix = job.get('_deck_suffix', '') or arc_info.get('_deck_suffix', '')
            # MCQC-matching layout: {lib_type}/{corner}/{arc_type}/{arc_id}[suffix]/
            # When no lib_type is available (legacy path), fall back to previous behavior.
            lib_type = job.get('lib_type') or ''
            corner   = job.get('corner', '')
            arc_type = arc_info.get('ARC_TYPE', 'unknown')
            arc_id   = job.get('arc_id') or get_deck_dirname(arc_info, when)
            # Sanitize: replace ! with not in directory names (MCQC convention)
            arc_id = arc_id.replace('!', 'not')
            if lib_type and corner:
                deck_dir = os.path.join(output_dir, lib_type, corner,
                                        arc_type, arc_id + deck_suffix)
            else:
                # Legacy path
                corner_suffix = '_' + corner if corner else ''
                deck_dir = os.path.join(output_dir,
                                        get_deck_dirname(arc_info, when)
                                        + corner_suffix + deck_suffix)
            os.makedirs(deck_dir, exist_ok=True)

            nominal_path = os.path.join(deck_dir, 'nominal_sim.sp')
            write_deck(nominal_lines, nominal_path)

            mc_path = None
            if not nominal_only:
                mc_lines = build_mc_deck(nominal_lines, num_samples=num_samples)
                mc_path = os.path.join(deck_dir, 'mc_sim.sp')
                write_deck(mc_lines, mc_path)

            return {'id': job['id'], 'success': True,
                    'nominal': nominal_path, 'mc': mc_path, 'error': None}
        except Exception as e:
            return {'id': job['id'], 'success': False,
                    'nominal': None, 'mc': None, 'error': str(e)}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_run_one, job): job for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda r: r['id'])
    return results


def run_batch(arc_ids, corner_names, files, overrides=None, output_dir='.',
              selected_ids=None, nominal_only=False, num_samples=5000,
              node=None, lib_type=None, collateral_root='collateral'):
    """High-level batch runner: plan then execute.

    Args:
        arc_ids:      list of cell_arc_pt identifier strings
        corner_names: list of corner name strings
        files:        dict with keys: netlist_dir, model, waveform, template_tcl_dir
        overrides:    dict with optional: vdd, temperature, slew, load, max_slew
        output_dir:   base directory for output files
        selected_ids: if given, only execute jobs whose id is in this set
        nominal_only: skip MC generation
        num_samples:  Monte Carlo sample count
        node:         process node string (enables collateral mode)
        lib_type:     library type subdir (required with node)
        collateral_root: root directory for collateral files

    Returns:
        (jobs, results, errors)
    """
    jobs, errors = plan_jobs(arc_ids, corner_names, files, overrides,
                              node=node, lib_type=lib_type,
                              collateral_root=collateral_root)

    if selected_ids is not None:
        id_set = set(selected_ids)
        jobs_to_run = [j for j in jobs if j['id'] in id_set]
    else:
        jobs_to_run = jobs

    results = execute_jobs(jobs_to_run, output_dir,
                           nominal_only=nominal_only,
                           num_samples=num_samples,
                           files=files)
    return jobs, results, errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _opposite_dir(direction):
    return 'fall' if direction == 'rise' else 'rise'


def _find_tcl(tcl_dir, corner_name):
    """Find {corner_name}.template.tcl or template.tcl in tcl_dir."""
    for name in (f'{corner_name}.template.tcl', 'template.tcl'):
        path = os.path.join(tcl_dir, name)
        if os.path.exists(path):
            return path
    return None


def _job_to_arc_info(job, files):
    """Convert a planned job dict to the arc_info dict expected by deck_builder."""
    tpl_abs = os.path.normpath(
        os.path.join(_TEMPLATES_DIR, job.get('template', '')))
    return {
        'CELL_NAME': job['cell'],
        'ARC_TYPE': job['arc_type'],
        'REL_PIN': job['rel_pin'],
        'REL_PIN_DIR': job['rel_dir'],
        'CONSTR_PIN': job.get('constr_pin', job['rel_pin']),
        'CONSTR_PIN_DIR': job.get('constr_dir', ''),
        'PROBE_PIN_1': job.get('probe_pin', ''),
        'TEMPLATE_DECK_PATH': tpl_abs,
        'NETLIST_PATH': job.get('netlist', ''),
        'NETLIST_PINS': job.get('netlist_pins', ''),
        'VDD_VALUE': job.get('vdd', ''),
        'TEMPERATURE': job.get('temperature', ''),
        'INCLUDE_FILE': files.get('model', ''),
        'WAVEFORM_FILE': files.get('waveform', ''),
        'PUSHOUT_PER': job.get('pushout_per', '0.4'),
        'NUM_SAMPLES': job.get('num_samples', 5000),
    }


def _plan_jobs_from_collateral(arc_ids, corner_names, node, lib_type,
                                collateral_root, overrides):
    """Collateral-backed planning. Returns (jobs, errors).

    For each (arc_id, corner) pair, calls resolve_all_from_collateral and
    produces a job dict compatible with execute_jobs.
    """
    from core.parsers.arc import parse_arc_identifier
    from core.resolver import resolve_all_from_collateral, ResolutionError

    jobs = []
    errors = []
    job_id = 0

    for arc_id in arc_ids:
        arc_id = arc_id.strip()
        if not arc_id:
            continue
        arc = parse_arc_identifier(arc_id)
        if arc is None:
            errors.append(f"Cannot parse arc identifier: {arc_id!r}")
            continue

        # MPW skip check
        from core.mpw_skip import skip_this_arc
        if skip_this_arc(
                cell_name=arc['cell_name'],
                arc_type=arc['arc_type'],
                rel_pin=arc['rel_pin'],
                rel_pin_dir=arc['rel_dir'],
                pin=arc.get('probe_pin', ''),
                pin_dir=arc.get('probe_dir', ''),
                when=arc.get('when', ''),
                probe_list=[arc.get('probe_pin', '')]):
            continue

        for corner_name in corner_names:
            corner_name = corner_name.strip()
            if not corner_name:
                continue
            try:
                # MCQC convention: constr_dir is opposite of rel_dir for both
                # constraint arcs AND combinational arcs (where constr_dir maps
                # to output transition direction, which inverts the input).
                default_constr_dir = _opposite_dir(arc['rel_dir'])
                # Pass i1/i2 table point indices so build_arc_info can
                # look up the correct slew/load values from template.tcl
                arc_overrides = dict(overrides)
                import sys
                print(f"[batch] arc_id={arc_id[:50]} i1={arc.get('i1')} i2={arc.get('i2')} parsed_keys={list(arc.keys())}", file=sys.stderr)
                if arc.get('i1') is not None:
                    arc_overrides['index_1_index'] = arc['i1']
                if arc.get('i2') is not None:
                    arc_overrides['index_2_index'] = arc['i2']
                print(f"[batch] arc_overrides keys={list(arc_overrides.keys())}", file=sys.stderr)
                result = resolve_all_from_collateral(
                    cell_name=arc['cell_name'],
                    arc_type=arc['arc_type'],
                    rel_pin=arc['rel_pin'],
                    rel_dir=arc['rel_dir'],
                    constr_pin=overrides.get('constr_pin', arc['rel_pin']),
                    constr_dir=overrides.get('constr_dir', default_constr_dir),
                    probe_pin=arc['probe_pin'],
                    node=node, lib_type=lib_type, corner_name=corner_name,
                    collateral_root=collateral_root,
                    overrides=arc_overrides,
                )
                # Normalize to list (backward-compat: resolver returns dict for 1 result)
                arc_info_list = result if isinstance(result, list) else [result]
                for arc_info in arc_info_list:
                    job_id += 1
                    jobs.append({
                        'id': job_id,
                        'arc_id': arc_id,
                        'corner': corner_name,
                        'lib_type': lib_type,
                        'cell': arc['cell_name'],
                        'arc_type': arc['arc_type'],
                        'vdd': arc_info['VDD_VALUE'],
                        'temperature': arc_info['TEMPERATURE'],
                        'template': None,
                        'arc_info': arc_info,
                        '_deck_suffix': arc_info.get('_deck_suffix', ''),
                        'warnings': [],
                        'error': None,
                    })
            except ResolutionError as e:
                job_id += 1
                jobs.append({
                    'id': job_id,
                    'arc_id': arc_id,
                    'corner': corner_name,
                    'cell': arc['cell_name'],
                    'arc_type': arc['arc_type'],
                    'error': str(e),
                    'arc_info': None,
                    'warnings': [],
                })

    # Disambiguate jobs with identical (arc_id, corner) but different vectors.
    # Append vector suffix to arc_id only for duplicates.
    from collections import Counter
    key_counts = Counter(
        (j.get('arc_id', ''), j.get('corner', ''))
        for j in jobs if j.get('arc_info'))
    for j in jobs:
        ai = j.get('arc_info')
        if not ai:
            continue
        key = (j.get('arc_id', ''), j.get('corner', ''))
        if key_counts[key] > 1:
            vector = ai.get('VECTOR', '')
            if vector:
                j['arc_id'] = j['arc_id'] + '_' + vector.strip('{}')

    return jobs, errors
