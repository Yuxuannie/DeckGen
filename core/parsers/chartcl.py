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
