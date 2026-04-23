"""chartcl.py - Faithful port of MCQC 1-general/chartcl_helper/parser.py.

MCQC parity principles:
  - values stored as strings (no numeric conversion)
  - no TCL preprocessing (no $var expansion, no comment stripping)
  - last-match-wins for per-cell conditions
  - regex patterns copied verbatim from MCQC
"""

import os
import re


class ChartclParser:
    """Port of MCQC ChartclParser.

    variant='general' -> iterate content_lines in reverse, early-exit
    variant='mpw'     -> iterate forward, stop at 'cell setting depend on'
    """

    def __init__(self, filepath, variant='general'):
        self.filepath = filepath
        self.variant = variant
        self.vars = {}
        self.conditions = {}
        self.amd_glitch = {}
        self.set_cells = []
        self.content_lines = None
        self.content_raw = None
        self.load()

    def load(self):
        with open(self.filepath, 'r') as f:
            self.content_lines = f.readlines()
        with open(self.filepath, 'r') as f:
            self.content_raw = f.read()

    def parse_set_var(self):
        """Extract constraint_glitch_peak, constraint_delay_degrade,
        constraint_output_load (and mpw_input_threshold for mpw variant)
        via substring matching.

        MCQC parity: all values stored as strings.
        """
        if self.variant == 'general':
            self._parse_set_var_general()
        elif self.variant == 'mpw':
            self._parse_set_var_mpw()
        else:
            raise ValueError(f"unknown variant: {self.variant}")

    def _parse_set_var_general(self):
        """1-general: iterate backward, early-exit once all 3 found."""
        targets = {'constraint_glitch_peak',
                   'constraint_delay_degrade',
                   'constraint_output_load'}
        for line in reversed(self.content_lines):
            if targets.issubset(self.vars.keys()):
                break

            splited = line.split()
            if not splited:
                continue

            if 'set_var -stage variation constraint_delay_degrade ' in line:
                # set_var -stage variation constraint_delay_degrade 0.4
                # var_name = splited[-2], var_value = splited[-1]
                self.vars[splited[-2]] = splited[-1]
            elif 'set_var constraint_glitch_peak ' in line:
                self.vars[splited[1]] = splited[2]
            elif 'set_var constraint_delay_degrade ' in line:
                self.vars[splited[1]] = splited[2]
            elif 'set_var constraint_output_load ' in line:
                self.vars[splited[1]] = splited[2].replace('index_', '')

    def _parse_set_var_mpw(self):
        """0-mpw: iterate forward, stop at sentinel, also recognize
        mpw_input_threshold."""
        for line in self.content_lines:
            if 'cell setting depend on' in line:
                break

            splited = line.split()
            if not splited:
                continue

            if 'set_var -stage variation constraint_delay_degrade ' in line:
                self.vars[splited[-2]] = splited[-1]
            elif 'set_var constraint_glitch_peak ' in line:
                self.vars[splited[1]] = splited[2]
            elif 'set_var constraint_delay_degrade ' in line:
                self.vars[splited[1]] = splited[2]
            elif 'set_var constraint_output_load ' in line:
                self.vars[splited[1]] = splited[2].replace('index_', '')
            elif line.startswith('set_var mpw_input_threshold'):
                self.vars[splited[-2]] = splited[-1]

    _COND_LOAD_RE = re.compile(
        r'if.{0,50}\{.{0,10}string compare.{0,10}"(\w{0,50})".{0,50}'
        r'constraint_output_load.{0,10}index_(\w{0,2})',
        flags=re.DOTALL)

    def parse_condition_load(self):
        """Per-cell constraint_output_load overrides.

        MCQC parity: last-match wins; values stored as strings.
        Regex copied verbatim from MCQC 1-general/chartcl_helper/parser.py.
        """
        for cell, index in self._COND_LOAD_RE.findall(self.content_raw):
            self.conditions.setdefault(cell, {})['OUTPUT_LOAD'] = index

    _COND_GLITCH_RE = re.compile(
        r'if.{0,50}\{.{0,10}string compare.{0,10}"(\w{0,50})".{0,50}'
        r'constraint_glitch_peak ([0-9\.\-\+e]{0,4})',
        flags=re.DOTALL)

    _COND_PUSHOUT_RE = re.compile(
        r'if.{0,50}\{.{0,10}string compare.{0,10}"(\w{0,50})".{0,50}'
        r'constraint_delay_degrade ([0-9\.\-\+e]{0,4})',
        flags=re.DOTALL)

    def parse_condition_glitch(self):
        """Per-cell constraint_glitch_peak overrides.

        MCQC parity: last-match wins; values stored as strings.
        """
        for cell, value in self._COND_GLITCH_RE.findall(self.content_raw):
            self.conditions.setdefault(cell, {})['GLITCH'] = value

    def parse_condition_delay_degrade(self):
        """Per-cell constraint_delay_degrade overrides.

        MCQC parity: key stored as 'PUSHOUT_PER' (not 'DELAY_DEGRADE');
        last-match wins; values stored as strings.
        """
        for cell, value in self._COND_PUSHOUT_RE.findall(self.content_raw):
            self.conditions.setdefault(cell, {})['PUSHOUT_PER'] = value

    def parse_amd_smc_degrade(self):
        """AMD SMC degrade override, alternative to constraint_delay_degrade."""
        for line in self.content_lines:
            if 'set_config_opt -type lvf smc_degrade' in line:
                self.vars['smc_degrade'] = line.split()[-1].strip()

    _AMD_GLITCH_RE = re.compile(
        r'set_config_opt -type \{\*hold\*\}(.*\n){1,2}.*'
        r'glitch_high_threshold([ \w\.]+\n)+\}',
        flags=re.DOTALL)

    def parse_amd_glitch_high_threshold(self):
        """Parse AMD-specific glitch thresholds.

        MCQC parity: builds self.vars['amd_glitch'] composite dict with
        keys {default_glitch, hold_glitch, cell_glitch, cells}.
        """
        self.vars.setdefault('amd_glitch', {}).setdefault('cells', [])

        # Forward scan for 'set glitch_low_threshold' lines -> default_glitch
        for line in self.content_lines:
            if line.strip().startswith('set glitch_low_threshold'):
                self.vars['amd_glitch']['default_glitch'] = line.split()[-1].strip()

        # Scan for set_config_opt -type {*hold*} blocks
        for match in self._AMD_GLITCH_RE.finditer(self.content_raw):
            self.process_amd_raw_glitch(match.group(0))

    def process_amd_raw_glitch(self, glitch):
        """Parse one set_config_opt block line-by-line."""
        lines = [line.strip() for line in glitch.split('\n')]
        is_cell_glitch = False
        for line in lines:
            if '-cell' in line:
                self.vars['amd_glitch']['cells'] = self.process_amd_glitch_cell(line)
                is_cell_glitch = True
            elif 'glitch_low_threshold' in line and is_cell_glitch:
                self.vars['amd_glitch']['cell_glitch'] = line.split()[-1]
            elif 'glitch_low_threshold' in line and not is_cell_glitch:
                self.vars['amd_glitch']['hold_glitch'] = line.split()[-1]

    def process_amd_glitch_cell(self, line):
        """Extract cell list from '-cell {cell1 cell2 cell3}'."""
        left = line.index('{')
        right = line.index('}')
        return line[left + 1:right].strip().split()


from core.parsers.chartcl_helpers import parse_chartcl_for_cells


def chartcl_parse_all(filepath, variant='general'):
    """Mirror runMonteCarlo.chartcl_parsing() sequence.

    Returns a fully-parsed ChartclParser instance.
    """
    p = ChartclParser(filepath, variant=variant)
    p.parse_set_var()
    p.parse_condition_glitch()
    p.parse_condition_load()
    p.parse_condition_delay_degrade()
    p.parse_amd_smc_degrade()
    p.parse_amd_glitch_high_threshold()
    p.set_cells = parse_chartcl_for_cells(filepath)
    return p


def resolve_chartcl_for_arc(parser, cell_name, arc_type):
    """Collapse vars + per-cell conditions into final values for one arc.

    Mirrors timingArcInfo.parseQACharacteristicsInfo() precedence.

    GLITCH precedence (cell condition overrides all):
      1. vars['constraint_glitch_peak']
         else vars['amd_glitch']:
           'hold' in arc_type + cell in amd['cells']     -> amd['cell_glitch']
           'hold' in arc_type + cell NOT in amd['cells'] -> amd['hold_glitch']
           else                                          -> amd['default_glitch']
      2. conditions[cell]['GLITCH']  (overrides 1 if present)

    PUSHOUT_PER precedence:
      1. vars['constraint_delay_degrade'] else vars['smc_degrade']
      2. conditions[cell]['PUSHOUT_PER']

    OUTPUT_LOAD_INDEX precedence:
      1. vars['constraint_output_load']
      2. conditions[cell]['OUTPUT_LOAD']
    """
    out = {'GLITCH': None, 'PUSHOUT_PER': None, 'OUTPUT_LOAD_INDEX': None}

    # --- GLITCH ---
    if 'constraint_glitch_peak' in parser.vars:
        out['GLITCH'] = parser.vars['constraint_glitch_peak']
    elif 'amd_glitch' in parser.vars and parser.vars['amd_glitch']:
        amd = parser.vars['amd_glitch']
        if 'hold' in arc_type:
            if cell_name in amd.get('cells', []):
                out['GLITCH'] = amd.get('cell_glitch')
            else:
                out['GLITCH'] = amd.get('hold_glitch')
        else:
            out['GLITCH'] = amd.get('default_glitch')
    if cell_name in parser.conditions and 'GLITCH' in parser.conditions[cell_name]:
        out['GLITCH'] = parser.conditions[cell_name]['GLITCH']

    # --- PUSHOUT_PER ---
    if 'constraint_delay_degrade' in parser.vars:
        out['PUSHOUT_PER'] = parser.vars['constraint_delay_degrade']
    elif 'smc_degrade' in parser.vars:
        out['PUSHOUT_PER'] = parser.vars['smc_degrade']
    if cell_name in parser.conditions and 'PUSHOUT_PER' in parser.conditions[cell_name]:
        out['PUSHOUT_PER'] = parser.conditions[cell_name]['PUSHOUT_PER']

    # --- OUTPUT_LOAD_INDEX ---
    if 'constraint_output_load' in parser.vars:
        out['OUTPUT_LOAD_INDEX'] = parser.vars['constraint_output_load']
    if cell_name in parser.conditions and 'OUTPUT_LOAD' in parser.conditions[cell_name]:
        out['OUTPUT_LOAD_INDEX'] = parser.conditions[cell_name]['OUTPUT_LOAD']

    return out
