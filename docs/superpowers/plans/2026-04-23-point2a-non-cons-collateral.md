# Point 2a: Non-Cons Collateral Dataset + Resolvers -- Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the MCQC-parity foundation for DeckGen: a manually-populated collateral dataset keyed by `(node, lib_type)`, a faithful ChartclParser port, an extended template.tcl parser, a full arc_info builder for non-cons arcs, and deck-builder substitutions -- enough to generate delay/slew decks that match MCQC bit-for-bit.

**Architecture:** User places SCLD collateral files under `collateral/{node}/{lib_type}/{Char,Template,Netlist}/` in SCLD-native form. `tools/scan_collateral.py` walks the tree and emits `manifest.json`. `core/collateral.CollateralStore` serves corner/cell lookups. `core/parsers/chartcl.py` ports MCQC's ChartclParser verbatim. `core/arc_info_builder.py` mirrors `parseQACharacteristicsInfo()` from `1-general/timingArcInfo/funcs.py`. `core/deck_builder.py` gains every MCQC-parity `$VAR` substitution. Scope excludes 3D constraint expansion, define_index overrides, SIS templates, and per-arc metric extraction (all deferred to Point 2b).

**Tech Stack:** Python 3.8+, pytest, pyyaml (existing), stdlib re / os / json only.

**Spec:** `docs/superpowers/specs/2026-04-23-point2a-non-cons-collateral-design.md`

---

## File Structure

**Created:**
- `collateral/README.md` -- how to populate + run scanner
- `collateral/.gitkeep` -- keeps the dir in git when all data is gitignored
- `core/parsers/chartcl.py` -- faithful ChartclParser port
- `core/parsers/chartcl_helpers.py` -- companion utilities (read_chartcl, parse_chartcl_for_cells, parse_chartcl_for_inc)
- `core/collateral.py` -- CollateralStore + CollateralError
- `core/arc_info_builder.py` -- port of parseQACharacteristicsInfo (non-cons subset)
- `tools/scan_collateral.py` -- manifest generator
- `tests/fixtures/chartcl/general_set_vars.tcl`
- `tests/fixtures/chartcl/mpw_set_vars.tcl`
- `tests/fixtures/chartcl/conditions_load.tcl`
- `tests/fixtures/chartcl/conditions_glitch.tcl`
- `tests/fixtures/chartcl/conditions_pushout.tcl`
- `tests/fixtures/chartcl/combined.tcl`
- `tests/fixtures/chartcl/last_match_wins.tcl`
- `tests/fixtures/chartcl/amd_glitch.tcl`
- `tests/fixtures/chartcl/smc_degrade.tcl`
- `tests/fixtures/chartcl/extsim_model_include.tcl`
- `tests/fixtures/chartcl/set_cells.tcl`
- `tests/fixtures/template_tcl/non_cons_full.tcl`
- `tests/fixtures/collateral/` -- tiny synthetic collateral tree
- `tests/test_chartcl_parser.py`
- `tests/test_chartcl_helpers.py`
- `tests/test_template_tcl_full.py`
- `tests/test_scan_collateral.py`
- `tests/test_collateral_store.py`
- `tests/test_arc_info_builder.py`
- `tests/test_resolve_from_collateral.py`

**Modified:**
- `.gitignore` -- add collateral gitignore rules
- `core/parsers/template_tcl.py` -- add `parse_template_tcl_full()`
- `core/resolver.py` -- add `resolve_all_from_collateral()`
- `core/deck_builder.py` -- expand `$VAR` substitution list
- `core/batch.py` -- add `node`/`lib_type` params
- `deckgen.py` -- new CLI flags `--node`, `--lib_type`, `--rescan`
- `docs/task.md` -- mark Point 2a done, list 2b open items

**Not touched:** 63 existing MPW templates at `templates/N2P_v1.0/mpw/`, `config/template_registry.yaml`, `core/writer.py`, existing 96 tests.

---

## Task 1: Collateral directory scaffold + gitignore

**Files:**
- Create: `collateral/README.md`
- Create: `collateral/.gitkeep`
- Modify: `.gitignore` (append)

- [ ] **Step 1: Create collateral/README.md**

```markdown
# Collateral Dataset

Manually-populated SCLD characterization collaterals, organized by `{node}/{lib_type}/`.

## Layout

```
collateral/
  {node}/                                    # e.g. N2P_v1.0, A14
    {lib_type}/                              # e.g. tcb02p_bwph130pnpnl3p48cpd_base_svt
      Char/                                  # char_*.tcl, *.inc, *.usage.l
      Template/                              # *.template.tcl
      Netlist/
        LPE_{rc}_{temp}/                     # netlists per RC type + temperature
          {CELL}_c.spi
      manifest.json                          # auto-generated, COMMITTED to git
```

## Populating

Drop SCLD files into `Char/`, `Template/`, `Netlist/` preserving SCLD-native filenames
(lib_type embedded). Do NOT rename files.

## Generating manifest.json

```bash
python3 tools/scan_collateral.py --node N2P_v1.0 --lib_type tcb02p_bwph130pnpnl3p48cpd_base_svt
python3 tools/scan_collateral.py --node N2P_v1.0 --all       # every lib_type under N2P_v1.0
python3 tools/scan_collateral.py --all                       # every (node, lib_type) leaf
```

The scanner also runs automatically whenever `CollateralStore` detects that
`Char/`, `Template/`, or `Netlist/` mtimes are newer than `manifest.json`.

## Git

`Char/`, `Template/`, `Netlist/` are gitignored. Only `manifest.json` and this README
are committed.
```

- [ ] **Step 2: Create collateral/.gitkeep**

```bash
touch collateral/.gitkeep
```

- [ ] **Step 3: Modify .gitignore**

Append to `.gitignore`:

```
# Collateral data (manifest.json and README are committed; raw data is gitignored)
collateral/*/*/Char/
collateral/*/*/Template/
collateral/*/*/Netlist/
```

- [ ] **Step 4: Non-ASCII check**

Run:
```bash
python3 -c "open('collateral/README.md','rb').read().decode('ascii'); print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add collateral/README.md collateral/.gitkeep .gitignore
git commit -m "feat(collateral): add dataset scaffold and gitignore rules"
```

---


## Task 2: char*.tcl test fixtures

**Files:**
- Create: `tests/fixtures/chartcl/general_set_vars.tcl`
- Create: `tests/fixtures/chartcl/mpw_set_vars.tcl`
- Create: `tests/fixtures/chartcl/conditions_load.tcl`
- Create: `tests/fixtures/chartcl/conditions_glitch.tcl`
- Create: `tests/fixtures/chartcl/conditions_pushout.tcl`
- Create: `tests/fixtures/chartcl/combined.tcl`
- Create: `tests/fixtures/chartcl/last_match_wins.tcl`
- Create: `tests/fixtures/chartcl/amd_glitch.tcl`
- Create: `tests/fixtures/chartcl/smc_degrade.tcl`
- Create: `tests/fixtures/chartcl/extsim_model_include.tcl`
- Create: `tests/fixtures/chartcl/set_cells.tcl`

- [ ] **Step 1: general_set_vars.tcl** -- exercises backward-iteration parser with all 3 constraint vars + -stage variation form.

```tcl
# General variant fixture
set_var constraint_glitch_peak 0.1
set_var constraint_output_load index_2
set_var -stage variation constraint_delay_degrade 0.4
# extra noise lines below must not break early-exit
set_var some_unrelated_var 99
```

- [ ] **Step 2: mpw_set_vars.tcl** -- MPW variant with sentinel + mpw_input_threshold.

```tcl
# MPW variant fixture: parser iterates forward, stops at sentinel
set_var constraint_glitch_peak 0.05
set_var constraint_delay_degrade 0.3
set_var constraint_output_load index_1
set_var mpw_input_threshold 0.5
# sentinel halts parsing
# cell setting depend on something below
set_var this_must_be_ignored 123
```

- [ ] **Step 3: conditions_load.tcl** -- multiple cells via string compare.

```tcl
if {[string compare "DFFQ1"] constraint_output_load index_2} {
    set foo 1
}
if {[string compare "SYNC2DFF"] constraint_output_load index_3} {
    set foo 2
}
if {[string compare "LAT1"] constraint_output_load index_1} {
    set foo 3
}
```

- [ ] **Step 4: conditions_glitch.tcl** -- numeric values with scientific notation.

```tcl
if {[string compare "CELLA"] constraint_glitch_peak 0.05} {
    set foo 1
}
if {[string compare "CELLB"] constraint_glitch_peak 0.1} {
    set foo 2
}
if {[string compare "CELLC"] constraint_glitch_peak 1e-3} {
    set foo 3
}
```

- [ ] **Step 5: conditions_pushout.tcl**

```tcl
if {[string compare "DFFQ1"] constraint_delay_degrade 0.25} {
    set foo 1
}
if {[string compare "SYNC2DFF"] constraint_delay_degrade 0.5} {
    set foo 2
}
```

- [ ] **Step 6: combined.tcl** -- cons + non_cons merged (vars + conditions in one file).

```tcl
set_var constraint_glitch_peak 0.1
set_var constraint_delay_degrade 0.4
set_var constraint_output_load index_2

if {[string compare "DFFQ1"] constraint_output_load index_3} {
    set foo 1
}
if {[string compare "DFFQ1"] constraint_glitch_peak 0.15} {
    set foo 2
}
```

- [ ] **Step 7: last_match_wins.tcl** -- verify overwrite semantics.

```tcl
if {[string compare "DFFQ1"] constraint_glitch_peak 0.05} {
    set first 1
}
if {[string compare "DFFQ1"] constraint_glitch_peak 0.2} {
    set second 1
}
```

- [ ] **Step 8: amd_glitch.tcl** -- set_config_opt block with -cell list.

```tcl
set glitch_low_threshold 0.05
set_config_opt -type {*hold*} {
    -cell {AND2X1 AND2X2 OR2X1}
    glitch_high_threshold 0.3 0.3 0.3
}
```

- [ ] **Step 9: smc_degrade.tcl**

```tcl
set_config_opt -type lvf smc_degrade 0.25
```

- [ ] **Step 10: extsim_model_include.tcl** -- for parse_chartcl_for_inc.

```tcl
set_var extsim_model_include "/server/path/base_model.inc"
set_var extsim_model_include -type hold "/server/path/hold_model.inc"
set_var extsim_model_include -type mpw "/server/path/mpw_model.inc"
set_var extsim_model_include -type delay "/server/path/delay_model.inc"
```

- [ ] **Step 11: set_cells.tcl** -- for parse_chartcl_for_cells.

```tcl
set cells {AND2X1 AND2X2 OR2X1 OR2X2 DFFQ1}
```

- [ ] **Step 12: Non-ASCII check**

Run:
```bash
python3 -c "
import os
for f in sorted(os.listdir('tests/fixtures/chartcl')):
    open(f'tests/fixtures/chartcl/{f}','rb').read().decode('ascii')
print('OK')
"
```
Expected: `OK`

- [ ] **Step 13: Commit**

```bash
git add tests/fixtures/chartcl/
git commit -m "test(chartcl): add fixture files for parser tests"
```

---


## Task 3: ChartclParser -- parse_set_var (general variant)

**Files:**
- Create: `core/parsers/chartcl.py`
- Create: `tests/test_chartcl_parser.py`

- [ ] **Step 1: Write failing tests for parse_set_var (general variant)**

Create `tests/test_chartcl_parser.py`:

```python
"""Tests for core.parsers.chartcl -- faithful MCQC ChartclParser port."""
import os
import pytest
from core.parsers.chartcl import ChartclParser

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'chartcl')


class TestParseSetVarGeneral:
    """MCQC parity: values stored as strings, NOT numeric."""

    def test_all_three_vars_found(self):
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        assert p.vars['constraint_glitch_peak'] == '0.1'
        assert p.vars['constraint_delay_degrade'] == '0.4'
        assert p.vars['constraint_output_load'] == '2'  # 'index_' prefix stripped

    def test_index_prefix_stripped(self):
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        assert not p.vars['constraint_output_load'].startswith('index_')

    def test_values_are_strings(self):
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        for key in ('constraint_glitch_peak', 'constraint_delay_degrade',
                    'constraint_output_load'):
            assert isinstance(p.vars[key], str)

    def test_stage_variation_form(self):
        """-stage variation constraint_delay_degrade recognized."""
        p = ChartclParser(os.path.join(FIX, 'general_set_vars.tcl'))
        p.parse_set_var()
        assert p.vars['constraint_delay_degrade'] == '0.4'
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_chartcl_parser.py::TestParseSetVarGeneral -v`
Expected: FAIL with "No module named 'core.parsers.chartcl'"

- [ ] **Step 3: Implement ChartclParser (general variant parse_set_var only)**

Create `core/parsers/chartcl.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chartcl_parser.py::TestParseSetVarGeneral -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/parsers/chartcl.py tests/test_chartcl_parser.py
git commit -m "feat(chartcl): add ChartclParser.parse_set_var (general variant)"
```

---


## Task 4: ChartclParser -- parse_set_var (mpw variant)

**Files:**
- Modify: `tests/test_chartcl_parser.py` (append class)

- [ ] **Step 1: Write failing tests for mpw variant**

Append to `tests/test_chartcl_parser.py`:

```python
class TestParseSetVarMpw:
    def test_mpw_input_threshold_found(self):
        p = ChartclParser(os.path.join(FIX, 'mpw_set_vars.tcl'), variant='mpw')
        p.parse_set_var()
        assert p.vars['mpw_input_threshold'] == '0.5'

    def test_sentinel_stops_parsing(self):
        p = ChartclParser(os.path.join(FIX, 'mpw_set_vars.tcl'), variant='mpw')
        p.parse_set_var()
        assert 'this_must_be_ignored' not in p.vars

    def test_mpw_vars_found(self):
        p = ChartclParser(os.path.join(FIX, 'mpw_set_vars.tcl'), variant='mpw')
        p.parse_set_var()
        assert p.vars['constraint_glitch_peak'] == '0.05'
        assert p.vars['constraint_delay_degrade'] == '0.3'
        assert p.vars['constraint_output_load'] == '1'
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_chartcl_parser.py::TestParseSetVarMpw -v`
Expected: all 3 PASS (mpw variant was already implemented in Task 3)

- [ ] **Step 3: Commit**

```bash
git add tests/test_chartcl_parser.py
git commit -m "test(chartcl): cover mpw variant parse_set_var"
```

---

## Task 5: ChartclParser -- parse_condition_load

**Files:**
- Modify: `core/parsers/chartcl.py` (append method)
- Modify: `tests/test_chartcl_parser.py` (append class)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_chartcl_parser.py`:

```python
class TestParseConditionLoad:
    def test_three_cells_found(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_load.tcl'))
        p.parse_condition_load()
        assert set(p.conditions.keys()) == {'DFFQ1', 'SYNC2DFF', 'LAT1'}

    def test_output_load_indices(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_load.tcl'))
        p.parse_condition_load()
        assert p.conditions['DFFQ1']['OUTPUT_LOAD'] == '2'
        assert p.conditions['SYNC2DFF']['OUTPUT_LOAD'] == '3'
        assert p.conditions['LAT1']['OUTPUT_LOAD'] == '1'

    def test_values_are_strings(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_load.tcl'))
        p.parse_condition_load()
        for cell in p.conditions:
            assert isinstance(p.conditions[cell]['OUTPUT_LOAD'], str)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_chartcl_parser.py::TestParseConditionLoad -v`
Expected: FAIL with "AttributeError: ... has no attribute 'parse_condition_load'"

- [ ] **Step 3: Implement parse_condition_load**

Append to `core/parsers/chartcl.py` (inside class ChartclParser):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chartcl_parser.py::TestParseConditionLoad -v`
Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add core/parsers/chartcl.py tests/test_chartcl_parser.py
git commit -m "feat(chartcl): add parse_condition_load"
```

---

## Task 6: ChartclParser -- parse_condition_glitch + parse_condition_delay_degrade

**Files:**
- Modify: `core/parsers/chartcl.py` (append methods)
- Modify: `tests/test_chartcl_parser.py` (append class)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_chartcl_parser.py`:

```python
class TestParseConditionGlitch:
    def test_glitch_values(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_glitch.tcl'))
        p.parse_condition_glitch()
        assert p.conditions['CELLA']['GLITCH'] == '0.05'
        assert p.conditions['CELLB']['GLITCH'] == '0.1'
        assert p.conditions['CELLC']['GLITCH'] == '1e-3'


class TestParseConditionPushout:
    def test_pushout_values(self):
        p = ChartclParser(os.path.join(FIX, 'conditions_pushout.tcl'))
        p.parse_condition_delay_degrade()
        assert p.conditions['DFFQ1']['PUSHOUT_PER'] == '0.25'
        assert p.conditions['SYNC2DFF']['PUSHOUT_PER'] == '0.5'


class TestLastMatchWins:
    def test_later_value_overwrites(self):
        p = ChartclParser(os.path.join(FIX, 'last_match_wins.tcl'))
        p.parse_condition_glitch()
        # MCQC parity: last regex match wins
        assert p.conditions['DFFQ1']['GLITCH'] == '0.2'
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_chartcl_parser.py::TestParseConditionGlitch tests/test_chartcl_parser.py::TestParseConditionPushout tests/test_chartcl_parser.py::TestLastMatchWins -v`
Expected: FAIL with AttributeError

- [ ] **Step 3: Implement methods**

Append to `core/parsers/chartcl.py` (inside class ChartclParser):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chartcl_parser.py::TestParseConditionGlitch tests/test_chartcl_parser.py::TestParseConditionPushout tests/test_chartcl_parser.py::TestLastMatchWins -v`
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
git add core/parsers/chartcl.py tests/test_chartcl_parser.py
git commit -m "feat(chartcl): add parse_condition_glitch and parse_condition_delay_degrade"
```

---


## Task 7: ChartclParser -- parse_amd_smc_degrade

**Files:**
- Modify: `core/parsers/chartcl.py`
- Modify: `tests/test_chartcl_parser.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_chartcl_parser.py`:

```python
class TestAmdSmcDegrade:
    def test_smc_degrade_extracted(self):
        p = ChartclParser(os.path.join(FIX, 'smc_degrade.tcl'))
        p.parse_amd_smc_degrade()
        assert p.vars['smc_degrade'] == '0.25'
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_chartcl_parser.py::TestAmdSmcDegrade -v`
Expected: FAIL with AttributeError

- [ ] **Step 3: Implement method**

Append to `core/parsers/chartcl.py` (inside class):

```python
    def parse_amd_smc_degrade(self):
        """AMD SMC degrade override, alternative to constraint_delay_degrade."""
        for line in self.content_lines:
            if 'set_config_opt -type lvf smc_degrade' in line:
                self.vars['smc_degrade'] = line.split()[-1].strip()
```

- [ ] **Step 4: Run test to verify pass**

Run: `python -m pytest tests/test_chartcl_parser.py::TestAmdSmcDegrade -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/parsers/chartcl.py tests/test_chartcl_parser.py
git commit -m "feat(chartcl): add parse_amd_smc_degrade"
```

---

## Task 8: ChartclParser -- parse_amd_glitch_high_threshold

**Files:**
- Modify: `core/parsers/chartcl.py`
- Modify: `tests/test_chartcl_parser.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_chartcl_parser.py`:

```python
class TestAmdGlitch:
    def test_amd_glitch_cells_extracted(self):
        p = ChartclParser(os.path.join(FIX, 'amd_glitch.tcl'))
        p.parse_amd_glitch_high_threshold()
        assert 'amd_glitch' in p.vars
        assert set(p.vars['amd_glitch']['cells']) == {'AND2X1', 'AND2X2', 'OR2X1'}

    def test_amd_glitch_default_glitch(self):
        p = ChartclParser(os.path.join(FIX, 'amd_glitch.tcl'))
        p.parse_amd_glitch_high_threshold()
        # 'set glitch_low_threshold 0.05' -> default_glitch
        assert p.vars['amd_glitch']['default_glitch'] == '0.05'
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_chartcl_parser.py::TestAmdGlitch -v`
Expected: FAIL with AttributeError

- [ ] **Step 3: Implement methods**

Append to `core/parsers/chartcl.py` (inside class):

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_chartcl_parser.py::TestAmdGlitch -v`
Expected: both PASS

- [ ] **Step 5: Full parser suite check**

Run: `python -m pytest tests/test_chartcl_parser.py -v`
Expected: all chartcl tests PASS, existing 96 tests unaffected.

Run: `python -m pytest tests/ -q`
Expected: all pass, no regression.

- [ ] **Step 6: Commit**

```bash
git add core/parsers/chartcl.py tests/test_chartcl_parser.py
git commit -m "feat(chartcl): add parse_amd_glitch_high_threshold and helpers"
```

---


## Task 9: chartcl helpers (read_chartcl, parse_chartcl_for_cells, parse_chartcl_for_inc)

**Files:**
- Create: `core/parsers/chartcl_helpers.py`
- Create: `tests/test_chartcl_helpers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_chartcl_helpers.py`:

```python
"""Tests for core.parsers.chartcl_helpers."""
import os
import pytest
from core.parsers.chartcl_helpers import (
    read_chartcl,
    parse_chartcl_for_cells,
    parse_chartcl_for_inc,
)

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'chartcl')


def test_read_chartcl_returns_raw_string():
    content = read_chartcl(os.path.join(FIX, 'general_set_vars.tcl'))
    assert isinstance(content, str)
    assert 'constraint_glitch_peak' in content


def test_parse_chartcl_for_cells_extracts_list():
    cells = parse_chartcl_for_cells(os.path.join(FIX, 'set_cells.tcl'))
    assert cells == ['AND2X1', 'AND2X2', 'OR2X1', 'OR2X2', 'DFFQ1']


def test_parse_chartcl_for_cells_empty_when_absent():
    cells = parse_chartcl_for_cells(os.path.join(FIX, 'general_set_vars.tcl'))
    assert cells == []


def test_parse_chartcl_for_inc_traditional_entry():
    inc = parse_chartcl_for_inc(os.path.join(FIX, 'extsim_model_include.tcl'))
    # MCQC parity: entry without -type goes under 'traditional'
    assert inc['traditional'] == '/server/path/base_model.inc'


def test_parse_chartcl_for_inc_per_arc_entries():
    inc = parse_chartcl_for_inc(os.path.join(FIX, 'extsim_model_include.tcl'))
    assert inc['hold']  == '/server/path/hold_model.inc'
    assert inc['mpw']   == '/server/path/mpw_model.inc'
    assert inc['delay'] == '/server/path/delay_model.inc'
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_chartcl_helpers.py -v`
Expected: FAIL with "No module named 'core.parsers.chartcl_helpers'"

- [ ] **Step 3: Implement helpers**

Create `core/parsers/chartcl_helpers.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_chartcl_helpers.py -v`
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
git add core/parsers/chartcl_helpers.py tests/test_chartcl_helpers.py
git commit -m "feat(chartcl): add helper functions (read, cells, inc)"
```

---

## Task 10: chartcl_parse_all wrapper + resolve_chartcl_for_arc

**Files:**
- Modify: `core/parsers/chartcl.py` (append module-level functions)
- Modify: `tests/test_chartcl_parser.py` (append classes)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_chartcl_parser.py`:

```python
from core.parsers.chartcl import chartcl_parse_all, resolve_chartcl_for_arc


class TestChartclParseAll:
    def test_wrapper_runs_all_methods(self):
        p = chartcl_parse_all(os.path.join(FIX, 'combined.tcl'))
        assert p.vars['constraint_glitch_peak'] == '0.1'
        assert p.conditions['DFFQ1']['OUTPUT_LOAD'] == '3'
        assert p.conditions['DFFQ1']['GLITCH'] == '0.15'


class TestResolveChartclForArc:
    def _fresh(self):
        return chartcl_parse_all(os.path.join(FIX, 'combined.tcl'))

    def test_global_glitch_used_when_no_cell_condition(self):
        p = self._fresh()
        # 'UNKNOWN' cell has no condition -> falls back to constraint_glitch_peak
        v = resolve_chartcl_for_arc(p, 'UNKNOWN', 'hold')
        assert v['GLITCH'] == '0.1'

    def test_cell_glitch_overrides_global(self):
        p = self._fresh()
        # DFFQ1 has per-cell GLITCH=0.15 in combined.tcl
        v = resolve_chartcl_for_arc(p, 'DFFQ1', 'hold')
        assert v['GLITCH'] == '0.15'

    def test_global_pushout_used(self):
        p = self._fresh()
        v = resolve_chartcl_for_arc(p, 'UNKNOWN', 'hold')
        assert v['PUSHOUT_PER'] == '0.4'

    def test_global_output_load_index(self):
        p = self._fresh()
        v = resolve_chartcl_for_arc(p, 'UNKNOWN', 'hold')
        assert v['OUTPUT_LOAD_INDEX'] == '2'

    def test_cell_output_load_overrides_global(self):
        p = self._fresh()
        v = resolve_chartcl_for_arc(p, 'DFFQ1', 'hold')
        assert v['OUTPUT_LOAD_INDEX'] == '3'
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_chartcl_parser.py::TestChartclParseAll tests/test_chartcl_parser.py::TestResolveChartclForArc -v`
Expected: FAIL with ImportError on `chartcl_parse_all`

- [ ] **Step 3: Implement wrapper + resolver**

Append to `core/parsers/chartcl.py` (at module level, below the class):

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_chartcl_parser.py -v`
Expected: all chartcl tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/parsers/chartcl.py tests/test_chartcl_parser.py
git commit -m "feat(chartcl): add chartcl_parse_all and resolve_chartcl_for_arc"
```

---


## Task 11: parse_template_tcl_full -- fixture + tests

**Files:**
- Create: `tests/fixtures/template_tcl/non_cons_full.tcl`
- Create: `tests/test_template_tcl_full.py`

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/template_tcl/non_cons_full.tcl`:

```tcl
lu_table_template "delay_template_5x5" {
  variable_1 : input_net_transition;
  variable_2 : total_output_net_capacitance;
  index_1 ("0.05 0.1 0.2 0.5 1.0");
  index_2 ("0.0005 0.001 0.005 0.01 0.05");
}

lu_table_template "hold_template_5x5" {
  variable_1 : constrained_pin_transition;
  variable_2 : related_pin_transition;
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
}

define_cell "DFFQ1" {
  pinlist { VDD VSS CP D Q SE SI }
  output_pins { Q }
  delay_template       : delay_template_5x5;
  constraint_template  : hold_template_5x5;
  mpw_template         : delay_template_5x5;
}

define_arc {
  cell         : DFFQ1;
  arc_type     : combinational;
  pin          : Q;
  pin_dir      : rise;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "!SE&SI";
  lit_when     : "notSE_SI";
  probe_list   : { Q };
  vector       : "RxxRxx";
}

define_arc {
  cell         : DFFQ1;
  arc_type     : hold;
  pin          : D;
  pin_dir      : fall;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "NO_CONDITION";
  lit_when     : "NO_CONDITION";
  probe_list   : { Q };
  vector       : "xxRxFxx";
}
```

- [ ] **Step 2: Non-ASCII check on fixture**

Run: `python3 -c "open('tests/fixtures/template_tcl/non_cons_full.tcl','rb').read().decode('ascii'); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Write failing tests**

Create `tests/test_template_tcl_full.py`:

```python
"""Tests for parse_template_tcl_full (extension of template_tcl parser)."""
import os
import pytest
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


@pytest.fixture
def info():
    return parse_template_tcl_full(os.path.join(FIX, 'non_cons_full.tcl'))


class TestTemplatesSection:
    def test_delay_template_found(self, info):
        assert 'delay_template_5x5' in info['templates']
        t = info['templates']['delay_template_5x5']
        assert t['index_1'] == [0.05, 0.1, 0.2, 0.5, 1.0]

    def test_hold_template_found(self, info):
        assert 'hold_template_5x5' in info['templates']


class TestCellsSection:
    def test_cell_pinlist(self, info):
        cell = info['cells']['DFFQ1']
        assert cell['pinlist'] == 'VDD VSS CP D Q SE SI'

    def test_cell_output_pins(self, info):
        assert info['cells']['DFFQ1']['output_pins'] == ['Q']

    def test_cell_template_references(self, info):
        cell = info['cells']['DFFQ1']
        assert cell['delay_template']      == 'delay_template_5x5'
        assert cell['constraint_template'] == 'hold_template_5x5'
        assert cell['mpw_template']        == 'delay_template_5x5'


class TestArcsSection:
    def test_two_arcs_found(self, info):
        assert len(info['arcs']) == 2

    def test_combinational_arc_fields(self, info):
        arc = [a for a in info['arcs'] if a['arc_type'] == 'combinational'][0]
        assert arc['cell']        == 'DFFQ1'
        assert arc['pin']         == 'Q'
        assert arc['pin_dir']     == 'rise'
        assert arc['rel_pin']     == 'CP'
        assert arc['rel_pin_dir'] == 'rise'
        assert arc['when']        == '!SE&SI'
        assert arc['lit_when']    == 'notSE_SI'
        assert arc['probe_list']  == ['Q']
        assert arc['vector']      == 'RxxRxx'

    def test_hold_arc_no_condition(self, info):
        arc = [a for a in info['arcs'] if a['arc_type'] == 'hold'][0]
        assert arc['when'] == 'NO_CONDITION'


class TestLegacyCompatibility:
    def test_old_parse_template_tcl_still_works(self):
        from core.parsers.template_tcl import parse_template_tcl
        old = parse_template_tcl(os.path.join(FIX, 'non_cons_full.tcl'))
        # existing key 'templates' preserved
        assert 'delay_template_5x5' in old['templates']
```

- [ ] **Step 4: Run tests to verify failure**

Run: `python -m pytest tests/test_template_tcl_full.py -v`
Expected: FAIL with ImportError on parse_template_tcl_full

- [ ] **Step 5: Implement parse_template_tcl_full**

Append to `core/parsers/template_tcl.py` at module level:

```python
# ---------------------------------------------------------------------------
# Full parser -- extends parse_template_tcl with cells + arcs + templates.
# Used by core.arc_info_builder for MCQC-parity arc_info composition.
# ---------------------------------------------------------------------------

_DEFINE_CELL_RE = re.compile(
    r'define_cell\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
    flags=re.DOTALL)
_DEFINE_ARC_RE = re.compile(
    r'define_arc\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
    flags=re.DOTALL)
_FIELD_RE = re.compile(
    r'(\w+)\s*:\s*(?:"([^"]*)"|\{([^}]*)\}|([^;\s][^;]*?))\s*;')


def _parse_block_fields(block_body):
    """Parse `key : value;` pairs from a define_cell or define_arc body.

    Values can be:
      - quoted strings: when : "!SE&SI";
      - brace lists:    pinlist { VDD VSS CP };
      - bare tokens:    arc_type : combinational;
    """
    fields = {}
    for m in _FIELD_RE.finditer(block_body):
        key = m.group(1)
        quoted, braced, bare = m.group(2), m.group(3), m.group(4)
        if quoted is not None:
            fields[key] = quoted
        elif braced is not None:
            # Brace list -> space-joined string (callers can .split() if needed)
            fields[key] = braced.strip()
        else:
            fields[key] = (bare or '').strip()
    return fields


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
    base = parse_template_tcl(path)

    with open(path, 'r') as f:
        content = f.read()

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

    return {
        'templates': base['templates'],
        'cells':     cells,
        'arcs':      arcs,
        'global':    base['global'],
    }
```

- [ ] **Step 6: Run tests to verify pass**

Run: `python -m pytest tests/test_template_tcl_full.py -v`
Expected: all PASS, including legacy compatibility test

Run: `python -m pytest tests/ -q`
Expected: no regression.

- [ ] **Step 7: Commit**

```bash
git add core/parsers/template_tcl.py tests/test_template_tcl_full.py tests/fixtures/template_tcl/
git commit -m "feat(template_tcl): add parse_template_tcl_full (cells + arcs)"
```

---


## Task 12: Collateral fixture for scanner + store tests

**Files:**
- Create: `tests/fixtures/collateral/N2P_v1.0/test_lib/Char/*.inc`, `*.tcl`, `*.usage.l`
- Create: `tests/fixtures/collateral/N2P_v1.0/test_lib/Template/*.template.tcl`
- Create: `tests/fixtures/collateral/N2P_v1.0/test_lib/Netlist/LPE_cworst_CCworst_T_m40c/DFFQ1_c.spi`

The fixture represents: 1 node, 1 lib_type, 1 corner `ssgnp_0p450v_m40c_cworst_CCworst_T`, 1 cell `DFFQ1`.

- [ ] **Step 1: Create Char/ files**

Prefix = `test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T`  (no embedded lib_type in these test names; the filename matching relies only on the corner portion).

Files (one-line each, content only needs to be realistic enough to parse):

**tests/fixtures/collateral/N2P_v1.0/test_lib/Char/char_test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.cons.tcl:**
```tcl
set_var constraint_glitch_peak 0.1
set_var constraint_delay_degrade 0.4
set_var constraint_output_load index_2
```

**tests/fixtures/collateral/N2P_v1.0/test_lib/Char/char_test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.non_cons.tcl:**
```tcl
set_var constraint_glitch_peak 0.05
set_var constraint_delay_degrade 0.25
set_var constraint_output_load index_1
set_var extsim_model_include "/server/test_lib/ssgnp_0p450v_m40c_cworst_CCworst_T.inc"
set_var extsim_model_include -type delay "/server/test_lib/ssgnp_0p450v_m40c_cworst_CCworst_T.delay.inc"
```

**tests/fixtures/collateral/N2P_v1.0/test_lib/Char/test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.inc:**
```spice
* base model include
.lib test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.usage.l PROCESS
```

**tests/fixtures/collateral/N2P_v1.0/test_lib/Char/test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.delay.inc:**
```spice
* delay model include
.lib test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.usage.l DELAY
```

**tests/fixtures/collateral/N2P_v1.0/test_lib/Char/test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.hold.inc:**
```spice
* hold model include
.lib test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.usage.l HOLD
```

**tests/fixtures/collateral/N2P_v1.0/test_lib/Char/test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.usage.l:**
```spice
* usage library (referenced by .inc via .lib directive)
.lib PROCESS
.endl
.lib DELAY
.endl
.lib HOLD
.endl
```

- [ ] **Step 2: Create Template/ file**

**tests/fixtures/collateral/N2P_v1.0/test_lib/Template/test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.template.tcl:**

Copy the full content from `tests/fixtures/template_tcl/non_cons_full.tcl` (same cells/arcs/templates).

```bash
cp tests/fixtures/template_tcl/non_cons_full.tcl \
   tests/fixtures/collateral/N2P_v1.0/test_lib/Template/test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.template.tcl
```

- [ ] **Step 3: Create Netlist/LPE_cworst_CCworst_T_m40c/DFFQ1_c.spi**

```spice
* Synthetic DFFQ1 netlist for testing
.subckt DFFQ1 VDD VSS CP D Q SE SI
* body omitted
.ends DFFQ1
```

- [ ] **Step 4: Non-ASCII check**

Run:
```bash
python3 -c "
import os
for root, dirs, files in os.walk('tests/fixtures/collateral'):
    for f in files:
        open(os.path.join(root,f),'rb').read().decode('ascii')
print('OK')
"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/collateral/
git commit -m "test(collateral): add synthetic collateral fixture (1 corner, 1 cell)"
```

---

## Task 13: tools/scan_collateral.py -- manifest generator

**Files:**
- Create: `tools/scan_collateral.py`
- Create: `tests/test_scan_collateral.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scan_collateral.py`:

```python
"""Tests for tools.scan_collateral -- manifest generator."""
import json
import os
import pytest
from tools.scan_collateral import scan_one, build_manifest

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'


def test_scan_one_returns_manifest_dict():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    assert manifest['schema_version'] == 1
    assert manifest['node'] == NODE
    assert manifest['lib_type'] == LIB


def test_scan_one_finds_corner():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    assert 'ssgnp_0p450v_m40c_cworst_CCworst_T' in manifest['corners']


def test_scan_one_corner_fields():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['process']     == 'ssgnp'
    assert c['vdd']         == '0.450'
    assert c['temperature'] == '-40'
    assert c['rc_type']     == 'cworst_CCworst_T'


def test_scan_one_char_cons_and_non_cons_found():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['char']['cons'].endswith('.cons.tcl')
    assert c['char']['non_cons'].endswith('.non_cons.tcl')
    assert c['char']['combined'] is None


def test_scan_one_model_files():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    m = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']['model']
    assert m['base'].endswith('.inc')
    assert m['delay'].endswith('.delay.inc')
    assert m['hold'].endswith('.hold.inc')


def test_scan_one_template_tcl():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['template_tcl'].endswith('.template.tcl')


def test_scan_one_netlist_dir():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    c = manifest['corners']['ssgnp_0p450v_m40c_cworst_CCworst_T']
    assert c['netlist_dir'] == 'Netlist/LPE_cworst_CCworst_T_m40c'


def test_scan_one_finds_cell():
    manifest = scan_one(FIXTURE_ROOT, NODE, LIB)
    assert 'DFFQ1' in manifest['cells']
    assert 'LPE_cworst_CCworst_T_m40c' in manifest['cells']['DFFQ1']


def test_build_manifest_writes_file(tmp_path):
    # Copy fixture into tmp so we don't write into the real fixture dir
    import shutil
    dest = tmp_path / 'collateral' / NODE / LIB
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB), str(dest))
    path = build_manifest(str(tmp_path / 'collateral'), NODE, LIB)
    assert os.path.isfile(path)
    with open(path) as f:
        data = json.load(f)
    assert data['node'] == NODE
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_scan_collateral.py -v`
Expected: FAIL with "No module named 'tools.scan_collateral'"

- [ ] **Step 3: Implement scanner**

Create `tools/scan_collateral.py`:

```python
#!/usr/bin/env python3
"""scan_collateral.py - Scan collateral/{node}/{lib_type}/ and emit manifest.json.

Does NOT copy files. Walks Char/, Template/, Netlist/ and records paths
grouped by corner. Writes manifest.json in the leaf directory.

Usage:
    python3 tools/scan_collateral.py --node N2P_v1.0 --lib_type <lib>
    python3 tools/scan_collateral.py --node N2P_v1.0 --all
    python3 tools/scan_collateral.py --all
"""

import argparse
import datetime
import json
import os
import re
import sys


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DECKGEN_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '..'))

# Corner regex: captures {process}_{voltage}v_{temp}c_{rc_type} with rc ending in _T
# Example match: ssgnp_0p450v_m40c_cworst_CCworst_T
_CORNER_RE = re.compile(
    r'(?P<process>\w+?)_(?P<vdd>\d+p\d+)v_(?P<temp>m?\d+)c_(?P<rc>\w+?_T)(?=[._]|$)'
)


def _parse_corner(name):
    """Extract (process, vdd, temp, rc_type) from a corner token.

    Returns (process, vdd_dotted, temp_signed, rc) or None.
    """
    m = _CORNER_RE.search(name)
    if not m:
        return None
    vdd_raw = m.group('vdd')              # '0p450'
    vdd = vdd_raw.replace('p', '.')       # '0.450'
    temp_raw = m.group('temp')            # 'm40' or '25'
    temp = ('-' + temp_raw[1:]) if temp_raw.startswith('m') else temp_raw
    return m.group('process'), vdd, temp, m.group('rc')


def _find_char_files(char_dir):
    """Scan Char/ and bucket files by corner + kind.

    Returns {corner_name: {
        'char_cons': path_or_None, 'char_non_cons': path_or_None,
        'char_combined': path_or_None,
        'inc_base': path, 'inc_delay': path, 'inc_hold': path,
        'inc_setup': path, 'inc_mpw': path,
        'usage_l': path,
    }}
    """
    result = {}
    warnings = []
    if not os.path.isdir(char_dir):
        return result, warnings

    # Priority-ordered suffixes (longest first)
    SUFFIXES = [
        ('char_cons',     '.cons.tcl'),
        ('char_non_cons', '.non_cons.tcl'),
        ('inc_delay',     '.delay.inc'),
        ('inc_hold',      '.hold.inc'),
        ('inc_setup',     '.setup.inc'),
        ('inc_mpw',       '.mpw.inc'),
        ('inc_base',      '.inc'),
        ('usage_l',       '.usage.l'),
    ]

    for fname in sorted(os.listdir(char_dir)):
        full = os.path.join(char_dir, fname)
        if not os.path.isfile(full):
            continue

        matched = False
        for kind, suffix in SUFFIXES:
            if not fname.endswith(suffix):
                continue
            stem = fname[:-len(suffix)]
            corner_parse = _parse_corner(stem)
            if corner_parse is None:
                warnings.append(f"Char/{fname}: no corner pattern matched")
                matched = True
                break
            process, vdd, temp, rc = corner_parse
            # Reconstruct corner key from the matched portion
            m = _CORNER_RE.search(stem)
            corner_key = m.group(0)
            entry = result.setdefault(corner_key, {})
            # First match wins (files sorted, so deterministic)
            entry.setdefault(kind, os.path.relpath(full, os.path.dirname(char_dir)))
            matched = True
            break

        if not matched:
            warnings.append(f"Char/{fname}: unknown suffix")

    return result, warnings


def _find_template_files(template_dir):
    """Scan Template/ for *.template.tcl per corner."""
    result = {}
    warnings = []
    if not os.path.isdir(template_dir):
        return result, warnings

    for fname in sorted(os.listdir(template_dir)):
        if not fname.endswith('.template.tcl'):
            warnings.append(f"Template/{fname}: not a .template.tcl file")
            continue
        full = os.path.join(template_dir, fname)
        stem = fname[:-len('.template.tcl')]
        m = _CORNER_RE.search(stem)
        if not m:
            warnings.append(f"Template/{fname}: no corner pattern matched")
            continue
        corner_key = m.group(0)
        result[corner_key] = os.path.relpath(full, os.path.dirname(template_dir))

    return result, warnings


def _find_netlist_dirs(netlist_dir):
    """Scan Netlist/ for LPE_{rc}_{temp} subdirs.

    Returns {'LPE_cworst_CCworst_T_m40c': 'Netlist/LPE_cworst_CCworst_T_m40c', ...},
    and {cell_name: [list of LPE dirs]}.
    """
    lpe_dirs = {}
    cells = {}
    if not os.path.isdir(netlist_dir):
        return lpe_dirs, cells

    for sub in sorted(os.listdir(netlist_dir)):
        subpath = os.path.join(netlist_dir, sub)
        if not os.path.isdir(subpath):
            continue
        rel = os.path.relpath(subpath, os.path.dirname(netlist_dir))
        lpe_dirs[sub] = rel
        for f in os.listdir(subpath):
            if not f.endswith(('.spi', '.sp', '.spice')):
                continue
            # Strip _c_qa, _c suffixes to get cell name
            stem = f
            for s in ('_c_qa.spi', '_c.spi', '.spi', '.sp', '.spice'):
                if stem.endswith(s):
                    stem = stem[:-len(s)]
                    break
            cells.setdefault(stem, []).append(sub)

    return lpe_dirs, cells


def _lpe_suffix_for_corner(rc, temp):
    """Build 'LPE_{rc}_{temp}c' suffix matching netlist subdir naming.

    temp here is the signed temp ('-40' or '25'); convert back to MCQC form ('m40' / '25').
    """
    t = 'm' + temp[1:] if temp.startswith('-') else temp
    return f"LPE_{rc}_{t}c"


def scan_one(collateral_root, node, lib_type):
    """Scan one {node}/{lib_type}/ leaf and return a manifest dict.

    Paths in the manifest are relative to the leaf dir (collateral_root/node/lib_type).
    """
    leaf = os.path.join(collateral_root, node, lib_type)
    char_dir     = os.path.join(leaf, 'Char')
    template_dir = os.path.join(leaf, 'Template')
    netlist_dir  = os.path.join(leaf, 'Netlist')

    warnings = []

    char_map,     w = _find_char_files(char_dir);     warnings.extend(w)
    template_map, w = _find_template_files(template_dir); warnings.extend(w)
    lpe_dirs, cells  = _find_netlist_dirs(netlist_dir)

    corners = {}
    for corner_key, char in char_map.items():
        parse = _parse_corner(corner_key)
        if parse is None:
            warnings.append(f"corner '{corner_key}' failed to parse")
            continue
        process, vdd, temp, rc = parse
        lpe_subdir = _lpe_suffix_for_corner(rc, temp)

        corners[corner_key] = {
            'process':     process,
            'vdd':         vdd,
            'temperature': temp,
            'rc_type':     rc,
            'char': {
                'combined':       char.get('char_combined'),
                'cons':           char.get('char_cons'),
                'non_cons':       char.get('char_non_cons'),
                'group_combined': None,
                'group_cons':     None,
                'group_non_cons': None,
            },
            'model': {
                'base':  char.get('inc_base'),
                'delay': char.get('inc_delay'),
                'hold':  char.get('inc_hold'),
                'setup': char.get('inc_setup'),
                'mpw':   char.get('inc_mpw'),
            },
            'usage_l':      char.get('usage_l'),
            'template_tcl': template_map.get(corner_key),
            'netlist_dir':  lpe_dirs.get(lpe_subdir),
        }

        if corners[corner_key]['netlist_dir'] is None:
            warnings.append(
                f"corner '{corner_key}': expected Netlist/{lpe_subdir} not found")
        if corners[corner_key]['template_tcl'] is None:
            warnings.append(
                f"corner '{corner_key}': no matching template.tcl")

    return {
        'schema_version':  1,
        'node':            node,
        'lib_type':        lib_type,
        'collateral_root': os.path.relpath(leaf, _DECKGEN_ROOT),
        'generated_at':    datetime.datetime.utcnow().isoformat() + 'Z',
        'corners':         corners,
        'cells':           cells,
        'warnings':        warnings,
    }


def build_manifest(collateral_root, node, lib_type):
    """Scan one leaf and write its manifest.json. Returns the manifest path."""
    manifest = scan_one(collateral_root, node, lib_type)
    leaf = os.path.join(collateral_root, node, lib_type)
    os.makedirs(leaf, exist_ok=True)
    path = os.path.join(leaf, 'manifest.json')
    with open(path, 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--node', default=None)
    p.add_argument('--lib_type', default=None)
    p.add_argument('--all', action='store_true',
                   help='scan every (node, lib_type) leaf under collateral/')
    p.add_argument('--collateral_root', default='collateral')
    args = p.parse_args()

    root = os.path.abspath(os.path.join(_DECKGEN_ROOT, args.collateral_root)) \
        if not os.path.isabs(args.collateral_root) else args.collateral_root

    if not os.path.isdir(root):
        print(f"ERROR: collateral root not found: {root}", file=sys.stderr)
        sys.exit(1)

    jobs = []
    if args.all and not args.node:
        for node in sorted(os.listdir(root)):
            node_dir = os.path.join(root, node)
            if not os.path.isdir(node_dir):
                continue
            for lib in sorted(os.listdir(node_dir)):
                if os.path.isdir(os.path.join(node_dir, lib)):
                    jobs.append((node, lib))
    elif args.node and args.all:
        node_dir = os.path.join(root, args.node)
        for lib in sorted(os.listdir(node_dir)):
            if os.path.isdir(os.path.join(node_dir, lib)):
                jobs.append((args.node, lib))
    elif args.node and args.lib_type:
        jobs.append((args.node, args.lib_type))
    else:
        p.error("provide --node + --lib_type, --node + --all, or --all")

    total_warnings = 0
    for node, lib in jobs:
        path = build_manifest(root, node, lib)
        # Read back to report warnings
        with open(path) as f:
            data = json.load(f)
        n_warn = len(data.get('warnings', []))
        total_warnings += n_warn
        print(f"  {node}/{lib}: {len(data['corners'])} corners, {n_warn} warnings"
              f"  -> {os.path.relpath(path, _DECKGEN_ROOT)}")
        for w in data['warnings'][:10]:
            print(f"      WARN: {w}")

    print(f"\nScanned {len(jobs)} leaf(s), {total_warnings} warnings total.")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_scan_collateral.py -v`
Expected: all 9 PASS

Run: `python -m pytest tests/ -q`
Expected: no regression.

- [ ] **Step 5: Manual smoke test**

Run: `python3 tools/scan_collateral.py --collateral_root tests/fixtures/collateral --node N2P_v1.0 --lib_type test_lib`
Expected: output shows `1 corners, 0 warnings`; file `tests/fixtures/collateral/N2P_v1.0/test_lib/manifest.json` is written.

- [ ] **Step 6: Cleanup**

The manual smoke test wrote a file under tests/fixtures. Remove it:
```bash
rm -f tests/fixtures/collateral/N2P_v1.0/test_lib/manifest.json
```
(The test that needs a manifest creates it in tmp_path.)

- [ ] **Step 7: Commit**

```bash
git add tools/scan_collateral.py tests/test_scan_collateral.py
git commit -m "feat(tools): add scan_collateral.py manifest generator"
```

---


## Task 14: CollateralStore -- basic lookups

**Files:**
- Create: `core/collateral.py`
- Create: `tests/test_collateral_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_collateral_store.py`:

```python
"""Tests for core.collateral.CollateralStore."""
import json
import os
import shutil
import pytest
from core.collateral import CollateralStore, CollateralError

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


@pytest.fixture
def store(tmp_path):
    """Copy fixture into tmp, build manifest, return store."""
    dest_root = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest_root / NODE / LIB))
    # Build manifest
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest_root), NODE, LIB)
    return CollateralStore(str(dest_root), NODE, LIB)


class TestListing:
    def test_list_corners(self, store):
        assert store.list_corners() == [CORNER]

    def test_list_cells(self, store):
        assert 'DFFQ1' in store.list_cells()


class TestGetCorner:
    def test_get_corner_returns_abs_paths(self, store):
        c = store.get_corner(CORNER)
        assert os.path.isabs(c['template_tcl'])
        assert os.path.isabs(c['char']['cons'])
        assert os.path.isabs(c['model']['base'])

    def test_get_corner_missing_raises(self, store):
        with pytest.raises(CollateralError):
            store.get_corner('does_not_exist')


class TestPickCharFile:
    def test_constraint_arc_picks_cons(self, store):
        path = store.pick_char_file(CORNER, 'hold')
        assert path.endswith('.cons.tcl')

    def test_non_cons_arc_picks_non_cons(self, store):
        path = store.pick_char_file(CORNER, 'combinational')
        assert path.endswith('.non_cons.tcl')


class TestPickModelFile:
    def test_delay_arc_uses_delay_inc(self, store):
        # non_cons.tcl has extsim_model_include -type delay -> delay.inc
        path = store.pick_model_file(CORNER, 'delay')
        assert path is not None
        assert path.endswith('.delay.inc')

    def test_combinational_normalized_to_delay(self, store):
        path = store.pick_model_file(CORNER, 'combinational')
        assert path is not None
        # cons.tcl has no extsim_model_include; but non_cons.tcl does.
        # combinational -> 'delay' normalization, must find delay entry.
        assert path.endswith('.delay.inc')

    def test_unknown_arc_type_returns_none_when_no_traditional(self, store):
        # Ensure non-existent key doesn't raise
        path = store.pick_model_file(CORNER, 'some_unknown_type')
        # Should fall back to 'traditional' if exactly one entry -- here there
        # are multiple, so returns None
        assert path is None or path.endswith('.inc')


class TestGetTemplateTcl:
    def test_returns_abs_path(self, store):
        path = store.get_template_tcl(CORNER)
        assert os.path.isabs(path)
        assert path.endswith('.template.tcl')


class TestGetNetlistDir:
    def test_returns_abs_path(self, store):
        d = store.get_netlist_dir(CORNER)
        assert os.path.isabs(d)
        assert os.path.isdir(d)


class TestErrorReporting:
    def test_error_includes_suggestions(self, store):
        try:
            store.get_corner('ssgnp_0p450v_m40c')  # missing rc suffix
        except CollateralError as e:
            msg = str(e)
            assert CORNER in msg  # suggestion should list real corner
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_collateral_store.py -v`
Expected: FAIL with "No module named 'core.collateral'"

- [ ] **Step 3: Implement CollateralStore**

Create `core/collateral.py`:

```python
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
            raise CollateralError(
                f"manifest.json not found at {self.manifest_path}\n"
                f"  x Run: python3 tools/scan_collateral.py "
                f"--node {self.node} --lib_type {self.lib_type}")
        with open(self.manifest_path) as f:
            return json.load(f)

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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_collateral_store.py -v`
Expected: all PASS

Run: `python -m pytest tests/ -q`
Expected: no regression.

- [ ] **Step 5: Commit**

```bash
git add core/collateral.py tests/test_collateral_store.py
git commit -m "feat(collateral): add CollateralStore with manifest-based lookup"
```

---

## Task 15: CollateralStore auto-rescan on staleness

**Files:**
- Modify: `core/collateral.py`
- Modify: `tests/test_collateral_store.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_collateral_store.py`:

```python
class TestAutoRescan:
    def test_rescan_when_char_dir_newer(self, tmp_path):
        """If Char/ mtime is newer than manifest, store regenerates silently."""
        import shutil, time
        dest_root = tmp_path / 'collateral'
        shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                        str(dest_root / NODE / LIB))
        from tools.scan_collateral import build_manifest
        build_manifest(str(dest_root), NODE, LIB)

        # Make manifest 10s old, Char/ current
        manifest_path = dest_root / NODE / LIB / 'manifest.json'
        old = time.time() - 10
        os.utime(str(manifest_path), (old, old))
        # Touch char dir
        char_dir = dest_root / NODE / LIB / 'Char'
        os.utime(str(char_dir), None)

        # Constructing store should regenerate manifest
        store = CollateralStore(str(dest_root), NODE, LIB)
        # New manifest mtime should be >= old + 5
        assert os.path.getmtime(str(manifest_path)) > old + 5
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_collateral_store.py::TestAutoRescan -v`
Expected: FAIL (store doesn't rescan)

- [ ] **Step 3: Implement auto-rescan**

Modify `_load` method in `core/collateral.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_collateral_store.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/collateral.py tests/test_collateral_store.py
git commit -m "feat(collateral): auto-rescan manifest when subdirs are newer"
```

---


## Task 16: arc_info_builder -- compose full arc_info for non-cons arcs

**Files:**
- Create: `core/arc_info_builder.py`
- Create: `tests/test_arc_info_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_arc_info_builder.py`:

```python
"""Tests for core.arc_info_builder.build_arc_info (non-cons subset)."""
import os
import pytest
from core.arc_info_builder import build_arc_info, format_index_value
from core.parsers.chartcl import chartcl_parse_all
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')


@pytest.fixture
def template_info():
    return parse_template_tcl_full(
        os.path.join(FIX, 'template_tcl', 'non_cons_full.tcl'))


@pytest.fixture
def chartcl():
    return chartcl_parse_all(
        os.path.join(FIX, 'collateral', 'N2P_v1.0', 'test_lib', 'Char',
                     'char_test_lib_ssgnp_0p450v_m40c_cworst_CCworst_T.non_cons.tcl'))


@pytest.fixture
def delay_arc(template_info):
    return [a for a in template_info['arcs']
            if a['arc_type'] == 'combinational'][0]


@pytest.fixture
def dffq1_cell(template_info):
    return template_info['cells']['DFFQ1']


@pytest.fixture
def fake_corner():
    return {
        'process':     'ssgnp',
        'vdd':         '0.450',
        'temperature': '-40',
        'rc_type':     'cworst_CCworst_T',
        'netlist_dir': '/fake/netlist/dir',
    }


class TestCoreFields:
    def test_cell_and_arc_type(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='/fake/DFFQ1_c.spi', netlist_pins='VDD VSS CP D Q SE SI',
            include_file='/fake/model.delay.inc', waveform_file='/fake/wv.spi',
            overrides={})
        assert info['CELL_NAME'] == 'DFFQ1'
        assert info['ARC_TYPE']  == 'combinational'

    def test_rel_and_constr_pins(self, delay_arc, dffq1_cell, template_info,
                                  chartcl, fake_corner):
        # non-cons: CONSTR_PIN == REL_PIN
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='/fake', netlist_pins='',
            include_file='', waveform_file='', overrides={})
        assert info['REL_PIN']    == 'CP'
        assert info['CONSTR_PIN'] == 'CP'
        assert info['REL_PIN_DIR']    == 'rise'
        assert info['CONSTR_PIN_DIR'] == 'rise'

    def test_probe_pin_1(self, delay_arc, dffq1_cell, template_info,
                          chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='/fake', netlist_pins='',
            include_file='', waveform_file='', overrides={})
        assert info['PROBE_PIN_1'] == 'Q'


class TestWhenFields:
    def test_when_and_lit_when_separate(self, delay_arc, dffq1_cell,
                                         template_info, chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='',
            include_file='', waveform_file='', overrides={})
        assert info['WHEN']     == '!SE&SI'
        assert info['LIT_WHEN'] == 'notSE_SI'


class TestVectorAndPinlist:
    def test_vector_propagated(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['VECTOR'] == 'RxxRxx'

    def test_template_pinlist(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['TEMPLATE_PINLIST'] == 'VDD VSS CP D Q SE SI'


class TestIndexValues:
    def test_index_1_value_nanoseconds(self, delay_arc, dffq1_cell,
                                         template_info, chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={'index_1_index': 1, 'index_2_index': 1})
        # index_1 = [0.05, 0.1, 0.2, 0.5, 1.0], index at 1 = 0.05
        assert info['INDEX_1_VALUE'] == '0.05n'

    def test_index_2_value_picoseconds_for_non_cons(self, delay_arc,
                                                      dffq1_cell, template_info,
                                                      chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={'index_1_index': 1, 'index_2_index': 1})
        # non-cons: INDEX_2_VALUE suffix is 'p'
        # index_2 = [0.0005, 0.001, ...] * 1000 = 0.5p
        # Value at index 1 = 0.0005 pF = 0.5 pF (just treated as is + 'p')
        assert info['INDEX_2_VALUE'].endswith('p')


class TestEnvironmentFields:
    def test_vdd_and_temp_from_corner(self, delay_arc, dffq1_cell,
                                        template_info, chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['VDD_VALUE']   == '0.450'
        assert info['TEMPERATURE'] == '-40'

    def test_override_vdd_wins(self, delay_arc, dffq1_cell, template_info,
                                chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={'vdd': '0.999'})
        assert info['VDD_VALUE'] == '0.999'


class TestChartclFields:
    def test_glitch_from_chartcl(self, delay_arc, dffq1_cell, template_info,
                                   chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        # non_cons.tcl has constraint_glitch_peak 0.05
        assert info['GLITCH'] == '0.05'

    def test_pushout_from_chartcl(self, delay_arc, dffq1_cell, template_info,
                                    chartcl, fake_corner):
        info = build_arc_info(
            arc=delay_arc, cell_info=dffq1_cell,
            template_info=template_info, chartcl=chartcl,
            corner=fake_corner,
            netlist_path='', netlist_pins='', include_file='',
            waveform_file='', overrides={})
        assert info['PUSHOUT_PER'] == '0.25'


class TestFormatIndexValue:
    def test_nanosecond_suffix(self):
        assert format_index_value(0.05, 'n') == '0.05n'

    def test_picosecond_suffix(self):
        assert format_index_value(0.5, 'p') == '0.5p'

    def test_integer_value(self):
        assert format_index_value(1.0, 'n') == '1n'
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_arc_info_builder.py -v`
Expected: FAIL with "No module named 'core.arc_info_builder'"

- [ ] **Step 3: Implement arc_info_builder**

Create `core/arc_info_builder.py`:

```python
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


def build_arc_info(arc, cell_info, template_info, chartcl, corner,
                   netlist_path, netlist_pins, include_file, waveform_file,
                   overrides=None):
    """Compose the complete arc_info dict for a non-cons arc.

    Args:
        arc:           one entry from template_info['arcs']
        cell_info:     template_info['cells'][cell_name]
        template_info: full parse_template_tcl_full output
        chartcl:       ChartclParser instance (post chartcl_parse_all)
        corner:        manifest corner entry (with 'vdd', 'temperature', ...)
        netlist_path:  absolute path to cell netlist .spi
        netlist_pins:  pin-list string from .subckt line
        include_file:  absolute path to model .inc
        waveform_file: absolute path to waveform .spi
        overrides:     dict of user overrides (vdd, temperature, index_*_index, ...)

    Returns:
        arc_info dict with all MCQC-parity non-cons fields.
    """
    overrides = overrides or {}
    cell_name = arc['cell']
    arc_type  = arc['arc_type']

    # --- Index lookup ----------------------------------------------------
    template_name = _pick_template_for_arc(cell_info, arc_type)
    tpl = template_info['templates'].get(template_name, {}) if template_name else {}
    index_1_list = tpl.get('index_1', []) or template_info['global'].get('index_1', [])
    index_2_list = tpl.get('index_2', []) or template_info['global'].get('index_2', [])
    index_3_list = tpl.get('index_3', [])

    idx1 = overrides.get('index_1_index')
    idx2 = overrides.get('index_2_index')

    def _val(lst, idx, unit):
        if idx is None or not lst or idx < 1 or idx > len(lst):
            return ''
        return format_index_value(lst[idx - 1], unit)

    index_1_value = _val(index_1_list, idx1, 'n')
    index_2_value = _val(index_2_list, idx2, _index_2_unit_suffix(arc_type))

    max_slew = format_index_value(max(index_1_list), 'n') if index_1_list else ''

    # --- chartcl-derived fields -----------------------------------------
    chart = resolve_chartcl_for_arc(chartcl, cell_name, arc_type) if chartcl else {
        'GLITCH': '', 'PUSHOUT_PER': '', 'OUTPUT_LOAD_INDEX': None,
    }

    # --- output_load (MCQC: index_2[output_load_index - 1]) -------------
    output_load = ''
    ol_idx = chart.get('OUTPUT_LOAD_INDEX')
    if ol_idx is not None:
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
    # Ensure PROBE_PIN_1 exists (even if empty) for template substitution safety
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
        'HEADER_INFO':      template_info.get('global', {}).get('header_info', ''),
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

    info.update(probe_fields)

    return info
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_arc_info_builder.py -v`
Expected: all PASS

Run: `python -m pytest tests/ -q`
Expected: no regression.

- [ ] **Step 5: Commit**

```bash
git add core/arc_info_builder.py tests/test_arc_info_builder.py
git commit -m "feat(arc_info): add builder for non-cons MCQC-parity arc_info"
```

---


## Task 17: resolve_all_from_collateral -- orchestrator

**Files:**
- Modify: `core/resolver.py` (append function)
- Create: `tests/test_resolve_from_collateral.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_resolve_from_collateral.py`:

```python
"""Tests for core.resolver.resolve_all_from_collateral -- end-to-end orchestration."""
import os
import shutil
import pytest
from core.resolver import resolve_all_from_collateral

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), NODE, LIB)
    return str(dest)


def test_resolves_combinational_arc(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root,
        overrides={'index_1_index': 1, 'index_2_index': 1})
    assert info['CELL_NAME'] == 'DFFQ1'
    assert info['ARC_TYPE']  == 'combinational'


def test_include_file_from_extsim_model_include(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root,
        overrides={})
    # non_cons.tcl says: extsim_model_include -type delay ".../delay.inc"
    # combinational normalizes to 'delay' -> delay.inc
    assert info['INCLUDE_FILE'].endswith('.delay.inc')


def test_vdd_from_corner(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root, overrides={})
    assert info['VDD_VALUE']   == '0.450'
    assert info['TEMPERATURE'] == '-40'


def test_glitch_from_chartcl(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root, overrides={})
    # non_cons.tcl: constraint_glitch_peak 0.05
    assert info['GLITCH'] == '0.05'


def test_pushout_per_from_chartcl(collateral_root):
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root, overrides={})
    assert info['PUSHOUT_PER'] == '0.25'
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_resolve_from_collateral.py -v`
Expected: FAIL with "cannot import name 'resolve_all_from_collateral'"

- [ ] **Step 3: Implement resolve_all_from_collateral**

Append to `core/resolver.py`:

```python
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
    # Local imports to avoid cycles and keep the legacy path free of new deps.
    from core.collateral import CollateralStore, CollateralError
    from core.parsers.chartcl import chartcl_parse_all
    from core.parsers.template_tcl import parse_template_tcl_full
    from core.arc_info_builder import build_arc_info

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

    # 4. Resolve model file (.inc) via chartcl
    include_file = store.pick_model_file(corner_name, arc_type) or ''

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

    # 6. Netlist (override or discover under corner['netlist_dir'])
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

    # 7. Waveform -- hardcoded default with override option
    waveform_file = waveform_override or overrides.get(
        'waveform_file', '/server/default/stdvs_wv.spi')

    # 8. Hand off to arc_info_builder
    return build_arc_info(
        arc=arc, cell_info=cell_info,
        template_info=template_info, chartcl=chartcl,
        corner=corner,
        netlist_path=netlist_path, netlist_pins=netlist_pins,
        include_file=include_file, waveform_file=waveform_file,
        overrides=overrides)


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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_resolve_from_collateral.py -v`
Expected: all PASS

Run: `python -m pytest tests/ -q`
Expected: no regression.

- [ ] **Step 5: Commit**

```bash
git add core/resolver.py tests/test_resolve_from_collateral.py
git commit -m "feat(resolver): add resolve_all_from_collateral orchestrator"
```

---

## Task 18: deck_builder -- MCQC-parity $VAR substitutions

**Files:**
- Modify: `core/deck_builder.py`
- Modify: `tests/test_end_to_end.py` (only if needed; otherwise add a new test)

- [ ] **Step 1: Read current substitution block**

Read `core/deck_builder.py` and locate the loop that performs `line.replace('$...', ...)`. We need the exact context to insert new substitutions cleanly.

```bash
grep -n "replace(\\\$" core/deck_builder.py
```

Expected output: a list of existing `line.replace('$X', value)` calls. Record the file:line range.

- [ ] **Step 2: Write failing test for new substitutions**

Append to `tests/test_end_to_end.py` (bottom of file) or create `tests/test_deck_builder_substitutions.py`:

```python
"""Tests for new MCQC-parity substitutions in deck_builder."""
import pytest
from core.deck_builder import build_deck


def _fake_arc_info(**overrides):
    base = {
        'CELL_NAME': 'DFFQ1', 'ARC_TYPE': 'combinational',
        'REL_PIN': 'CP', 'REL_PIN_DIR': 'rise',
        'CONSTR_PIN': 'CP', 'CONSTR_PIN_DIR': 'rise',
        'PROBE_PIN_1': 'Q',
        'TEMPLATE_DECK_PATH': '',  # will be set by fixture
        'NETLIST_PATH': '/fake/DFFQ1_c.spi',
        'NETLIST_PINS': 'VDD VSS CP D Q SE SI',
        'VDD_VALUE': '0.450', 'TEMPERATURE': '-40',
        'INCLUDE_FILE': '/fake/model.inc',
        'WAVEFORM_FILE': '/fake/wv.spi',
        'GLITCH': '0.1', 'PUSHOUT_PER': '0.4', 'PUSHOUT_DIR': 'high',
        'WHEN': '!SE&SI', 'LIT_WHEN': 'notSE_SI',
        'VECTOR': 'RxxRxx',
        'SIDE_PIN_STATES': 'SE=0 SI=1',
        'DONT_TOUCH_PINS': 'VDD VSS',
        'OUTPUT_PINS': 'Q',
        'TEMPLATE_PINLIST': 'VDD VSS CP D Q SE SI',
        'HEADER_INFO': 'test_header',
        'INDEX_1_INDEX': '1', 'INDEX_1_VALUE': '0.05n',
        'INDEX_2_INDEX': '1', 'INDEX_2_VALUE': '0.5p',
        'INDEX_3_INDEX': '',
        'OUTPUT_LOAD': '0.5p', 'MAX_SLEW': '1n',
    }
    base.update(overrides)
    return base


def test_all_new_vars_substituted(tmp_path):
    """Every new $VAR in a template must be replaced by the arc_info value."""
    tpl = tmp_path / 'test.sp'
    tpl.write_text(
        "* $CELL_NAME $WHEN $LIT_WHEN $VECTOR\n"
        "* $SIDE_PIN_STATES $DONT_TOUCH_PINS $OUTPUT_PINS\n"
        "* $TEMPLATE_PINLIST $HEADER_INFO\n"
        "* $INDEX_1_VALUE $INDEX_2_VALUE $OUTPUT_LOAD $MAX_SLEW\n"
        "* $GLITCH $PUSHOUT_PER $PUSHOUT_DIR\n"
    )
    info = _fake_arc_info(TEMPLATE_DECK_PATH=str(tpl))
    lines = build_deck(info, slew=('0.05n', '0.05n'), load='0.5p',
                       when='!SE&SI', max_slew='1n')
    text = '\n'.join(lines)
    assert '$CELL_NAME' not in text
    assert 'DFFQ1' in text
    assert '!SE&SI' in text
    assert 'notSE_SI' in text
    assert 'RxxRxx' in text
    assert 'SE=0 SI=1' in text
    assert 'test_header' in text
    assert '0.05n' in text
    assert '0.5p' in text
    assert '0.1' in text


def test_missing_var_substitutes_empty(tmp_path):
    """Missing arc_info keys substitute to empty string (MCQC parity)."""
    tpl = tmp_path / 'test.sp'
    tpl.write_text("* $VECTOR $HEADER_INFO\n")
    info = _fake_arc_info(TEMPLATE_DECK_PATH=str(tpl),
                           VECTOR='', HEADER_INFO='')
    lines = build_deck(info, slew=('0n', '0n'), load='0p',
                       when='NO_CONDITION', max_slew='0n')
    text = '\n'.join(lines)
    assert '$VECTOR' not in text
    assert '$HEADER_INFO' not in text
```

- [ ] **Step 3: Run tests to verify failure**

Run: `python -m pytest tests/test_deck_builder_substitutions.py -v`
Expected: FAIL because new $VARs remain unsubstituted.

- [ ] **Step 4: Add substitutions to deck_builder**

In `core/deck_builder.build_deck()`, locate the block where existing substitutions are applied (`line.replace('$CELL_NAME', ...)` etc.). Add these additional replacements right after the existing ones, before the line is appended to output:

```python
        # MCQC-parity substitutions (Point 2a)
        line = line.replace('$WHEN',            str(arc_info.get('WHEN', '')))
        line = line.replace('$LIT_WHEN',        str(arc_info.get('LIT_WHEN', '')))
        line = line.replace('$VECTOR',          str(arc_info.get('VECTOR', '')))
        line = line.replace('$SIDE_PIN_STATES', str(arc_info.get('SIDE_PIN_STATES', '')))
        line = line.replace('$DONT_TOUCH_PINS', str(arc_info.get('DONT_TOUCH_PINS', '')))
        line = line.replace('$OUTPUT_PINS',     str(arc_info.get('OUTPUT_PINS', '')))
        line = line.replace('$TEMPLATE_PINLIST', str(arc_info.get('TEMPLATE_PINLIST', '')))
        line = line.replace('$HEADER_INFO',     str(arc_info.get('HEADER_INFO', '')))
        line = line.replace('$INDEX_1_INDEX',   str(arc_info.get('INDEX_1_INDEX', '')))
        line = line.replace('$INDEX_1_VALUE',   str(arc_info.get('INDEX_1_VALUE', '')))
        line = line.replace('$INDEX_2_INDEX',   str(arc_info.get('INDEX_2_INDEX', '')))
        line = line.replace('$INDEX_2_VALUE',   str(arc_info.get('INDEX_2_VALUE', '')))
        line = line.replace('$INDEX_3_INDEX',   str(arc_info.get('INDEX_3_INDEX', '')))
        line = line.replace('$OUTPUT_LOAD',     str(arc_info.get('OUTPUT_LOAD', '')))
        line = line.replace('$MAX_SLEW',        str(arc_info.get('MAX_SLEW', '')))
        line = line.replace('$GLITCH',          str(arc_info.get('GLITCH', '')))
        line = line.replace('$PUSHOUT_PER',     str(arc_info.get('PUSHOUT_PER', '0.4')))
        line = line.replace('$PUSHOUT_DIR',     str(arc_info.get('PUSHOUT_DIR', '')))
        line = line.replace('$TEMPLATE_DECK',   str(arc_info.get('TEMPLATE_DECK', '')))
        line = line.replace('$TEMPLATE_TCL',    str(arc_info.get('TEMPLATE_TCL', '')))
```

(Exact insertion location: immediately after the existing `$REL_PIN` / `$CELL_NAME` substitutions. If you cannot find a clear anchor, post a grep to choose a unique preceding line and use it as the Edit anchor.)

- [ ] **Step 5: Run tests to verify pass**

Run: `python -m pytest tests/test_deck_builder_substitutions.py tests/test_end_to_end.py -v`
Expected: all PASS

Run: `python -m pytest tests/ -q`
Expected: no regression on any of the existing 96 tests.

- [ ] **Step 6: Commit**

```bash
git add core/deck_builder.py tests/test_deck_builder_substitutions.py
git commit -m "feat(deck_builder): add MCQC-parity \$VAR substitutions (non-cons)"
```

---


## Task 19: batch.py -- accept node + lib_type

**Files:**
- Modify: `core/batch.py`

- [ ] **Step 1: Read current plan_jobs signature**

```bash
grep -n "def plan_jobs" core/batch.py
```

- [ ] **Step 2: Add params and collateral-path dispatch**

Edit `core/batch.plan_jobs` signature:

```python
def plan_jobs(arc_ids, corner_names, files, overrides=None,
              node=None, lib_type=None, collateral_root='collateral'):
    """When node and lib_type are both set, use the MCQC-parity collateral
    resolver. Otherwise, fall back to the legacy raw-path resolver.
    """
```

Near the top of the function body, after `overrides = overrides or {}`, add:

```python
    if node and lib_type:
        return _plan_jobs_from_collateral(
            arc_ids, corner_names, node, lib_type,
            collateral_root, overrides)
```

Append the new helper at module level:

```python
def _plan_jobs_from_collateral(arc_ids, corner_names, node, lib_type,
                                collateral_root, overrides):
    """Collateral-backed planning. Returns (jobs, errors).

    For each (arc_id, corner) pair, calls resolve_all_from_collateral and
    produces a job dict compatible with execute_jobs.
    """
    from core.parsers.arc import parse_arc_identifier
    from core.parsers.corner import parse_corner_name
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

        for corner_name in corner_names:
            corner_name = corner_name.strip()
            if not corner_name:
                continue
            job_id += 1
            try:
                arc_info = resolve_all_from_collateral(
                    cell_name=arc['cell_name'],
                    arc_type=arc['arc_type'],
                    rel_pin=arc['rel_pin'],
                    rel_dir=arc['rel_dir'],
                    constr_pin=overrides.get('constr_pin', arc['rel_pin']),
                    constr_dir=overrides.get('constr_dir', arc['rel_dir']),
                    probe_pin=arc['probe_pin'],
                    node=node, lib_type=lib_type, corner_name=corner_name,
                    collateral_root=collateral_root,
                    overrides=overrides,
                )
                jobs.append({
                    'id': job_id,
                    'arc_id': arc_id,
                    'corner': corner_name,
                    'cell': arc['cell_name'],
                    'arc_type': arc['arc_type'],
                    'vdd': arc_info['VDD_VALUE'],
                    'temperature': arc_info['TEMPERATURE'],
                    'template': None,   # arc_info-driven path
                    'arc_info': arc_info,
                    'warnings': [],
                    'error': None,
                })
            except ResolutionError as e:
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

    return jobs, errors
```

- [ ] **Step 3: Run existing batch tests to verify no regression**

Run: `python -m pytest tests/test_end_to_end.py -v`
Expected: all batch tests still PASS (they don't supply node/lib_type, so the legacy path is used).

Run: `python -m pytest tests/ -q`
Expected: 96+ tests pass.

- [ ] **Step 4: Commit**

```bash
git add core/batch.py
git commit -m "feat(batch): add node/lib_type params for collateral-backed planning"
```

---

## Task 20: deckgen.py CLI flags

**Files:**
- Modify: `deckgen.py`

- [ ] **Step 1: Add argparse flags**

Edit `deckgen.py`, in `parse_args()`, add:

```python
    # Collateral mode (MCQC-parity, non-cons arcs)
    p.add_argument('--node', default=None,
                   help='Process node (e.g. N2P_v1.0). Enables collateral mode.')
    p.add_argument('--lib_type', default=None,
                   help='Library type subdir under {node}/ (required with --node).')
    p.add_argument('--rescan', action='store_true',
                   help='Force rescan of collateral manifest before running.')
```

- [ ] **Step 2: Add validation + rescan wiring in main flow**

In `_run_batch`, near the top (after `_is_batch_mode` check passes), add:

```python
    # Collateral mode validation
    if args.node and not args.lib_type:
        print("ERROR: --node requires --lib_type", file=sys.stderr)
        sys.exit(1)
    if args.lib_type and not args.node:
        print("ERROR: --lib_type requires --node", file=sys.stderr)
        sys.exit(1)

    if args.rescan and args.node and args.lib_type:
        from tools.scan_collateral import build_manifest
        collateral_root = os.path.join(script_dir, 'collateral')
        build_manifest(collateral_root, args.node, args.lib_type)
```

Pass `node=args.node, lib_type=args.lib_type` through to `run_batch(...)`. In `core/batch.run_batch`, accept and forward to `plan_jobs`:

```python
def run_batch(arc_ids, corner_names, files, overrides=None, output_dir='.',
              selected_ids=None, nominal_only=False, num_samples=5000,
              node=None, lib_type=None, collateral_root='collateral'):
    jobs, errors = plan_jobs(arc_ids, corner_names, files, overrides,
                              node=node, lib_type=lib_type,
                              collateral_root=collateral_root)
    # ... rest unchanged
```

In `deckgen._run_batch`, update the `run_batch(...)` call:

```python
    jobs, results, errors = run_batch(
        arc_ids=arc_ids,
        corner_names=corner_names,
        files=files,
        overrides=overrides,
        output_dir=args.output,
        nominal_only=args.nominal_only,
        num_samples=args.num_samples,
        node=args.node,
        lib_type=args.lib_type,
    )
```

- [ ] **Step 3: Smoke-test the new CLI surface**

```bash
python3 deckgen.py --help 2>&1 | grep -E "node|lib_type|rescan"
```
Expected: 3 matching lines.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: no regression.

- [ ] **Step 5: Commit**

```bash
git add deckgen.py core/batch.py
git commit -m "feat(cli): add --node / --lib_type / --rescan for collateral mode"
```

---


## Task 21: End-to-end test -- 1 non-cons deck from fixture collateral

**Files:**
- Create: `tests/test_end_to_end_non_cons.py`

- [ ] **Step 1: Write the test**

Create `tests/test_end_to_end_non_cons.py`:

```python
"""End-to-end: generate one non-cons deck from the fixture collateral.

Verifies that resolve_all_from_collateral + deck_builder produce a complete
SPICE deck using a real template (from templates/N2P_v1.0/mpw/) with
MCQC-parity substitutions.
"""
import os
import shutil
import pytest
from core.deck_builder import build_deck
from core.resolver import resolve_all_from_collateral

FIXTURE_ROOT = os.path.join(
    os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB  = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'
DECKGEN_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..'))
TEMPLATE = os.path.join(
    DECKGEN_ROOT, 'templates', 'N2P_v1.0', 'mpw',
    'template__CP__rise__fall__1.sp')


@pytest.fixture
def collateral_root(tmp_path):
    dest = tmp_path / 'collateral'
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    str(dest / NODE / LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), NODE, LIB)
    return str(dest)


def test_generates_deck_with_substitutions(collateral_root):
    """Build a combinational deck; verify no $VAR placeholders survive."""
    info = resolve_all_from_collateral(
        cell_name='DFFQ1', arc_type='combinational',
        rel_pin='CP', rel_dir='rise',
        constr_pin='CP', constr_dir='rise',
        probe_pin='Q',
        node=NODE, lib_type=LIB, corner_name=CORNER,
        collateral_root=collateral_root,
        overrides={'index_1_index': 1, 'index_2_index': 1})

    # Inject the template path manually for this smoke test
    info['TEMPLATE_DECK_PATH'] = TEMPLATE

    lines = build_deck(info, slew=('0.05n', '0.05n'), load='0.5p',
                       when=info['WHEN'], max_slew=info['MAX_SLEW'])
    text = '\n'.join(lines)

    # No unresolved placeholders for MCQC-parity fields
    for placeholder in ('$CELL_NAME', '$VDD_VALUE', '$TEMPERATURE',
                         '$INCLUDE_FILE', '$WAVEFORM_FILE',
                         '$GLITCH', '$PUSHOUT_PER'):
        assert placeholder not in text, \
            f"{placeholder} still present in generated deck"

    # Known values are present
    assert 'DFFQ1'   in text
    assert '0.450'   in text
    assert '-40'     in text
```

- [ ] **Step 2: Run test to verify pass**

Run: `python -m pytest tests/test_end_to_end_non_cons.py -v`
Expected: PASS.

Note: some placeholders like `$WHEN`, `$VECTOR`, `$INDEX_*` may not exist in the legacy MPW templates -- that's fine (the assertion list above only checks placeholders that the MPW templates actually use).

- [ ] **Step 3: Full test suite check**

Run: `python -m pytest tests/ -q`
Expected: all PASS, no regression (should be well over 100 tests now).

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end_non_cons.py
git commit -m "test(e2e): add non-cons deck generation from fixture collateral"
```

---

## Task 22: Update docs/task.md

**Files:**
- Modify: `docs/task.md`

- [ ] **Step 1: Append Point 2a completion + 2b open items**

Append to `docs/task.md` (after the existing TODO-4 section):

```markdown
---

## Point 2a -- Done

Non-cons collateral dataset + resolvers (MCQC parity). Spec:
`docs/superpowers/specs/2026-04-23-point2a-non-cons-collateral-design.md`.
Plan: `docs/superpowers/plans/2026-04-23-point2a-non-cons-collateral.md`.

Delivered:
- `collateral/{node}/{lib_type}/` layout (user manually populated) + auto-
  generated `manifest.json`
- `core/parsers/chartcl.py` -- faithful port of MCQC ChartclParser
- `core/parsers/chartcl_helpers.py` -- read_chartcl, parse_chartcl_for_cells,
  parse_chartcl_for_inc
- `core/parsers/template_tcl.py::parse_template_tcl_full` -- cells + arcs +
  templates
- `core/collateral.CollateralStore` -- auto-rescan on staleness
- `core/arc_info_builder.build_arc_info` -- MCQC-parity arc_info for non-cons
  arcs
- `core/resolver.resolve_all_from_collateral`
- `core/deck_builder` -- expanded `$VAR` substitutions
- `core/batch` + `deckgen.py` -- `--node`, `--lib_type`, `--rescan`
- `tools/scan_collateral.py` -- manifest generator

---

## Point 2b -- Constraint Parity (open)

Builds on 2a. Required for hold/setup/mpw/si_immunity arcs.

- [ ] 3D constraint detection (5x5x5) and deck expansion (1 -> 3 decks with
      `-2`/`-3`/`-4` suffixes per MCQC)
- [ ] `define_index` override matching in `parse_template_tcl_full` -- per-
      (pin, rel_pin, when) overrides of index_1/index_2
- [ ] SIS template sidecar parser -- `Template_sis/*.sis` -> per-pintype
      `{PINTYPE}_GLITCH_HIGH_THRESHOLD` / `_LOW_THRESHOLD` fields
- [ ] Per-arc `metric` / `metric_thresh` extraction
- [ ] Constraint-arc verification against MCQC
- [ ] (optional) MPW skip logic (MB/SYNC/CKL cell arc filtering)
```

- [ ] **Step 2: Non-ASCII check**

Run: `python3 -c "open('docs/task.md','rb').read().decode('ascii'); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add docs/task.md
git commit -m "docs(task): mark Point 2a done, list 2b open items"
```

---

## Task 23: Final regression run + push

**Files:** none modified.

- [ ] **Step 1: Run full test suite one last time**

Run: `python -m pytest tests/ -v 2>&1 | tail -30`
Expected: all tests PASS. Total count should be 96 + ~40 new tests = ~136 tests.

- [ ] **Step 2: Non-ASCII scan across all source files**

Run:
```bash
python3 -c "
import os
violations = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', '.omc', '__pycache__')]
    for f in files:
        if not any(f.endswith(ext) for ext in ('.py','.yaml','.sp','.md','.tcl','.inc','.l','.spi')):
            continue
        path = os.path.join(root, f)
        try:
            open(path,'rb').read().decode('ascii')
        except UnicodeDecodeError as e:
            violations.append(f'{path}: {e}')
if violations:
    for v in violations: print(v)
    import sys; sys.exit(1)
else:
    print('OK - no non-ASCII bytes')
"
```
Expected: `OK - no non-ASCII bytes`

- [ ] **Step 3: Push to GitHub**

Set up the remote if not configured:

```bash
git remote -v
# If 'origin' is missing or pointing elsewhere:
git remote add origin https://github.com/Yuxuannie/DeckGen.git 2>/dev/null || \
  git remote set-url origin https://github.com/Yuxuannie/DeckGen.git
```

Push the current branch:

```bash
git push -u origin HEAD
```

If 2FA / password auth is needed, ask the user to provide credentials or use an SSH remote.

- [ ] **Step 4: Report completion**

Summarize to the user: total commits added, test count, GitHub push URL.

---

## Completion Checklist

- [ ] All 23 tasks complete
- [ ] All tests pass (96 legacy + ~40 new)
- [ ] No non-ASCII bytes anywhere
- [ ] manifest.json committed in git; raw collateral data gitignored
- [ ] Plan file and spec file both committed
- [ ] GitHub push successful

