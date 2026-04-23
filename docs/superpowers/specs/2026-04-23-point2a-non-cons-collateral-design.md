# Point 2a: Non-Cons Collateral Dataset + Resolvers (Design)

**Status:** draft -- awaiting user review before writing-plans
**Scope:** non-cons arcs only (delay, slew, combinational, edge, three_state_*, clear, preset)
**Out of scope (-> Point 2b):** constraint arcs (hold, setup, removal, recovery, non_seq_*, nochange_*, mpw, si_immunity), 3D constraint expansion, define_index overrides, SIS glitch thresholds, per-arc metric extraction
**Prerequisite:** template rename "generic" -> "N2P_v1.0" (done)

---

## 1. Purpose

DeckGen today can only generate MPW decks, and its deck-builder does not substitute the MCQC-mandatory fields `$GLITCH`, `$PUSHOUT_PER`, `$VECTOR`, `$WHEN`/`$LIT_WHEN`, `$SIDE_PIN_STATES`, `$INDEX_*_VALUE`, and others. As a result:

1. Deck output cannot achieve parity with MCQC's 1-general flow.
2. There is no way to look up per-corner collateral (model `.inc`, netlist, template.tcl, char*.tcl) from a user-specified `(node, lib_type, corner)` tuple.

Point 2a delivers the **foundation** required to generate non-cons decks that match MCQC bit-for-bit. It builds:

- A manually-populated **collateral dataset** layout keyed by `(node, lib_type)` with an **automatically generated manifest.json** for lookup.
- A **faithful port** of MCQC's `ChartclParser` (from `1-general/chartcl_helper/parser.py`).
- An extended **template.tcl parser** that emits the full MCQC `template_info` dict (define_template, define_cell, define_arc).
- A new **arc_info builder** module that mirrors `parseQACharacteristicsInfo()` from `1-general/timingArcInfo/funcs.py`, producing the complete MCQC-parity field set for non-cons arcs.
- Extended **deck_builder substitutions** covering every new `$VAR`.
- **Batch + CLI + GUI plumbing** exposing `--node` and `--lib_type` alongside the existing `--corners`.

Point 2b will add constraint-arc parity (3D expansion, define_index, SIS, metrics) in a subsequent spec.

---

## 2. Architecture

```
deckgen/
  collateral/                                # gitignored except manifest.json + README
    README.md                                # how to populate + run scanner
    N2P_v1.0/
      tcb02p_bwph130pnpnl3p48cpd_base_svt/
        Char/                                # gitignored
        Template/                            # gitignored
        Netlist/                             # gitignored
        manifest.json                        # COMMITTED -- auto-generated
      tcb02p_bwph130pnpnl3p48cpd_base_hvt/
        ...
    A14/
      lg_tcba14_bwph110dpnpnl3p44cpd_mb_svt_c250926_051a/
        ...

  core/
    parsers/
      chartcl.py                             # NEW  -- faithful MCQC ChartclParser port
      chartcl_helpers.py                     # NEW  -- read_chartcl, parse_chartcl_for_cells, parse_chartcl_for_inc
      template_tcl.py                        # EXTEND -- add parse_template_tcl_full()
    collateral.py                            # NEW  -- CollateralStore
    arc_info_builder.py                      # NEW  -- port of parseQACharacteristicsInfo (non-cons subset)
    resolver.py                              # EXTEND -- add resolve_all_from_collateral()
    deck_builder.py                          # EXTEND -- expand $VAR substitutions
    batch.py                                 # EXTEND -- accept node + lib_type

  tools/
    scan_collateral.py                       # NEW  -- walk {node}/{lib_type}/ and emit manifest.json

  tests/
    fixtures/
      chartcl/                               # NEW  -- hand-crafted char*.tcl fixtures
      collateral/                            # NEW  -- tiny collateral fixture
    test_chartcl_parser.py                   # NEW
    test_chartcl_helpers.py                  # NEW
    test_template_tcl_full.py                # NEW
    test_scan_collateral.py                  # NEW
    test_collateral_store.py                 # NEW
    test_arc_info_builder.py                 # NEW
    test_resolve_from_collateral.py          # NEW
    test_end_to_end_non_cons.py              # NEW  -- 1 cell x 1 non-cons arc x 1 corner, compare to fixture output
```

All existing 96 tests must keep passing unchanged.

---

## 3. Collateral Layout & Manifest

### 3.1 Directory layout

User manually drops SCLD files into:
```
collateral/{node}/{lib_type}/{Char | Template | Netlist}/
```

Filenames are kept SCLD-native (lib_type embedded). Example under `collateral/N2P_v1.0/tcb02p_bwph130pnpnl3p48cpd_base_svt/`:
- `Char/tcb02p_bwph130pnpnl3p48cpd_base_svt_ssgnp_0p450v_m40c_cworst_CCworst_T.inc`
- `Char/tcb02p_bwph130pnpnl3p48cpd_base_svt_ssgnp_0p450v_m40c_cworst_CCworst_T.delay.inc`
- `Char/tcb02p_bwph130pnpnl3p48cpd_base_svt_ssgnp_0p450v_m40c_cworst_CCworst_T.usage.l`
- `Char/char_tcb02p_bwph130pnpnl3p48cpd_base_svt_ssgnp_0p450v_m40c_cworst_CCworst_T.cons.tcl`
- `Char/char_tcb02p_bwph130pnpnl3p48cpd_base_svt_ssgnp_0p450v_m40c_cworst_CCworst_T.non_cons.tcl`
- `Char/char_trio_groupLPE_ssgnp_cworst_25c__cons.tcl`    (group-level, covers multiple voltages)
- `Template/tcb02p_bwph130pnpnl3p48cpd_base_svt_ssgnp_0p450v_m40c_cworst_CCworst_T.template.tcl`
- `Netlist/LPE_cworst_CCworst_T_m40c/DFFQ1_c.spi`

### 3.2 Git

`.gitignore` adds:
```
collateral/*/*/Char/
collateral/*/*/Template/
collateral/*/*/Netlist/
```
Commit: `collateral/README.md`, `collateral/*/*/manifest.json`.

### 3.3 Manifest schema (auto-generated by `tools/scan_collateral.py`)

```json
{
  "schema_version": 1,
  "node": "N2P_v1.0",
  "lib_type": "tcb02p_bwph130pnpnl3p48cpd_base_svt",
  "collateral_root": "collateral/N2P_v1.0/tcb02p_bwph130pnpnl3p48cpd_base_svt",
  "generated_at": "2026-04-23T14:32:01Z",

  "corners": {
    "ssgnp_0p450v_m40c_cworst_CCworst_T": {
      "process":     "ssgnp",
      "vdd":         "0.450",
      "temperature": "-40",
      "rc_type":     "cworst_CCworst_T",

      "char": {
        "combined":       null,
        "cons":           "Char/char_..._ssgnp_0p450v_m40c_cworst_CCworst_T.cons.tcl",
        "non_cons":       "Char/char_..._ssgnp_0p450v_m40c_cworst_CCworst_T.non_cons.tcl",
        "group_combined": null,
        "group_cons":     "Char/char_trio_groupLPE_ssgnp_cworst_CCworst_T_m40c__cons.tcl",
        "group_non_cons": null
      },

      "model": {
        "base":  "Char/..._ssgnp_0p450v_m40c_cworst_CCworst_T.inc",
        "delay": "Char/..._ssgnp_0p450v_m40c_cworst_CCworst_T.delay.inc",
        "hold":  "Char/..._ssgnp_0p450v_m40c_cworst_CCworst_T.hold.inc",
        "setup": "Char/..._ssgnp_0p450v_m40c_cworst_CCworst_T.setup.inc",
        "mpw":   "Char/..._ssgnp_0p450v_m40c_cworst_CCworst_T.mpw.inc"
      },

      "usage_l":      "Char/..._ssgnp_0p450v_m40c_cworst_CCworst_T.usage.l",
      "template_tcl": "Template/..._ssgnp_0p450v_m40c_cworst_CCworst_T.template.tcl",
      "netlist_dir":  "Netlist/LPE_cworst_CCworst_T_m40c"
    }
  },

  "cells": {
    "DFFQ1":    ["LPE_cworst_CCworst_T_m40c", "LPE_typical_T_25c"],
    "SYNC2DFF": ["LPE_cworst_CCworst_T_m40c"]
  },

  "warnings": [
    "Corner ssgnp_0p450v_m40c_cworst_CCworst_T: non_cons present but no cons",
    "File 'Char/stray_file.tcl' did not match any known pattern"
  ]
}
```

Notes:
- `model` is informational/audit only; runtime lookup goes through `extsim_model_include` parsed from char*.tcl (Section 4.3).
- `usage_l` is informational only; HSPICE resolves it transparently via `.lib` directive inside the `.inc` file.
- Paths are stored relative to `collateral_root` (manifest is portable across machines).

### 3.4 Scanner (`tools/scan_collateral.py`)

Does NOT copy files. Walks `{node}/{lib_type}/{Char,Template,Netlist}/` and emits manifest.json in the leaf.

**CLI:**
```bash
python3 tools/scan_collateral.py --node N2P_v1.0 --lib_type tcb02p_..._svt
python3 tools/scan_collateral.py --node N2P_v1.0 --all     # every lib_type under the node
python3 tools/scan_collateral.py --all                     # every (node, lib_type) leaf
```

**Filename parsing strategy** (regex-based, logs unmatched files as warnings):
```python
# Known suffixes (longest first to avoid ambiguity)
SUFFIXES = [
    '.template.tcl', '.cons.tcl', '.non_cons.tcl',
    '.delay.inc', '.hold.inc', '.setup.inc', '.mpw.inc', '.inc',
    '.usage.l',
]

# Per-corner: full corner {process}_{vddWithPrefixP}v_{temperatureWithOptionalM}c_{rc_type}
CORNER_RE = re.compile(r'(?P<prefix>.*?)(?P<corner>\w+_\d+p\d+v_m?\d+c_\w+?_T)(?P<suffix>\.\S+)$')

# Group: {process}_{rc}_{temp}  -- drops voltage
GROUP_RE  = re.compile(r'(?P<prefix>.*?group\w*)_(?P<process>\w+?)_(?P<rc>\w+?_T)_(?P<temp>m?\d+c)__?(?P<suffix>\S+)$')
```

**Ambiguity handling:** if multiple matches exist for the same (corner, kind) or (group_key, kind), keep the first (lexicographic sort) and add a warning listing all collisions.

**Non-ASCII check:** scanner runs a byte-level ASCII check across all matched files; emits per-file warnings if any.

### 3.5 Automatic regeneration

Three triggers:
1. **Explicit:** `python3 tools/scan_collateral.py ...` (primary path).
2. **Runtime mtime staleness:** `CollateralStore.__init__()` compares manifest.mtime against max(mtime) across `Char/`, `Template/`, `Netlist/` subdirs. If any subdir is newer, regenerate silently and log `"Refreshed manifest for {node}/{lib_type}"`.
3. **GUI / CLI `--rescan`:** force regeneration regardless of mtime.

---

## 4. Parsers

### 4.1 `core/parsers/chartcl.py` -- faithful MCQC port

Principle: **bit-for-bit parity with MCQC**. Copy regex patterns verbatim. Preserve string storage. Preserve last-match-wins. No "improvements."

```python
class ChartclParser:
    """Port of 1-general/chartcl_helper/parser.py + 0-mpw variant."""

    def __init__(self, filepath, variant='general'):
        # variant='general' -> backward iteration with early exit
        # variant='mpw'     -> forward iteration with 'cell setting depend on' sentinel
        self.filepath = filepath
        self.variant  = variant
        self.vars, self.conditions, self.amd_glitch, self.set_cells = {}, {}, {}, []
        self.content_lines, self.content_raw = None, None
        self.load()

    def load(self):                             # readlines() + full string
    def parse_set_var(self):                    # -> self.vars (keys listed below)
    def parse_condition_load(self):             # -> self.conditions[cell]['OUTPUT_LOAD']
    def parse_condition_glitch(self):           # -> self.conditions[cell]['GLITCH']
    def parse_condition_delay_degrade(self):    # -> self.conditions[cell]['PUSHOUT_PER']
    def parse_amd_smc_degrade(self):            # -> self.vars['smc_degrade']
    def parse_amd_glitch_high_threshold(self):  # -> self.vars['amd_glitch']
    def process_amd_raw_glitch(self, glitch):
    def process_amd_glitch_cell(self, line):
```

**set_var recognitions:**
- `constraint_glitch_peak` (string substring match)
- `constraint_delay_degrade` (plus `-stage variation` form)
- `constraint_output_load` (post-process: strip `index_` prefix)
- `smc_degrade` (via `set_config_opt -type lvf smc_degrade`)
- `amd_glitch` composite (`set_config_opt -type {*hold*}` blocks)
- `mpw_input_threshold` (0-mpw variant only)

**Regex patterns (verbatim from MCQC, `re.DOTALL`):**
```python
_COND_LOAD_RE    = re.compile(r'if.{0,50}\{.{0,10}string compare.{0,10}"(\w{0,50})".{0,50}constraint_output_load.{0,10}index_(\w{0,2})',         flags=re.DOTALL)
_COND_GLITCH_RE  = re.compile(r'if.{0,50}\{.{0,10}string compare.{0,10}"(\w{0,50})".{0,50}constraint_glitch_peak ([0-9\.\-\+e]{0,4})',          flags=re.DOTALL)
_COND_PUSHOUT_RE = re.compile(r'if.{0,50}\{.{0,10}string compare.{0,10}"(\w{0,50})".{0,50}constraint_delay_degrade ([0-9\.\-\+e]{0,4})',        flags=re.DOTALL)
_AMD_GLITCH_RE   = re.compile(r'set_config_opt -type \{\*hold\*\}(.*\n){1,2}.*glitch_high_threshold([ \w\.]+\n)+\}',                             flags=re.DOTALL)
```

**High-level wrapper:**
```python
def chartcl_parse_all(filepath, variant='general') -> ChartclParser:
    """Mirror runMonteCarlo.chartcl_parsing() sequence."""
    p = ChartclParser(filepath, variant=variant)
    p.parse_set_var()
    p.parse_condition_glitch()
    p.parse_condition_load()
    p.parse_condition_delay_degrade()
    p.parse_amd_smc_degrade()
    p.parse_amd_glitch_high_threshold()
    p.set_cells = parse_chartcl_for_cells(filepath)
    return p

def resolve_chartcl_for_arc(parser, cell_name, arc_type) -> dict:
    """Mirror timingArcInfo.parseQACharacteristicsInfo() precedence for
    GLITCH, PUSHOUT_PER, OUTPUT_LOAD_INDEX.

    GLITCH precedence (last wins, exact MCQC order):
      1. parser.vars['constraint_glitch_peak'] (if present)
         else parser.vars['amd_glitch']:
           - 'hold' in arc_type + cell in amd['cells']        -> amd['cell_glitch']
           - 'hold' in arc_type + cell NOT in amd['cells']    -> amd['hold_glitch']
           - else                                              -> amd['default_glitch']
      2. parser.conditions[cell]['GLITCH']          (overrides 1 if present)

    PUSHOUT_PER precedence:
      1. parser.vars['constraint_delay_degrade']
         else parser.vars['smc_degrade']
      2. parser.conditions[cell]['PUSHOUT_PER']     (overrides 1 if present)

    OUTPUT_LOAD_INDEX precedence:
      1. parser.vars['constraint_output_load']
      2. parser.conditions[cell]['OUTPUT_LOAD']     (overrides 1 if present)
    """
```

### 4.2 `core/parsers/chartcl_helpers.py` -- companion utilities

Port of MCQC's `hybrid_char_helper.py` + `qaTemplateMaker/chartcl_condition.py`:
```python
def read_chartcl(path: str) -> str                          # raw file reader
def parse_chartcl_for_cells(path: str) -> list[str]         # 'set cells {...}' line
def parse_chartcl_for_inc(path: str) -> dict[str, str]      # extsim_model_include -> {'delay': '/path/...', 'hold': '...', 'traditional': '...'}
```

### 4.3 Model file resolution (MCQC-exact)

MCQC does **not** filesystem-search for arc-type-specific `.inc` files. Instead:

1. Parse char*.tcl for `extsim_model_include` (via `parse_chartcl_for_inc`) -> dict.
2. Normalize arc_type:
   - `min_pulse_width`, `mpw` -> key `mpw`
   - `nochange_*` (any startswith) -> key `nochange`
   - `combinational`, `edge`, `combinational_rise`, `combinational_fall`, `rising_edge`, `falling_edge` -> key `delay`
   - else -> arc_type as-is
3. Return `lookup[normalized]`.
4. Fallback: if normalized key is missing AND lookup has exactly one entry, use key `traditional`.
5. Else -> None (caller issues warning).

Implementation lives in `core/collateral.py` (section 5.2).

### 4.4 `core/parsers/template_tcl.py` -- extend, do not rewrite

Existing `lookup_slew_load(i1, i2, arc_type)` stays (covers non-cons slew/load lookup correctly per MCQC).

New function emits the full MCQC `template_info`:
```python
def parse_template_tcl_full(path: str) -> dict:
    """Return:
    {
      'templates': {template_name: {index_1: [...], index_2: [...], index_3: [...]}},
      'cells':     {cell_name: {
          'pinlist':              'VDD VSS CP D Q SE SI',
          'output_pins':          ['Q'],
          'constraint_template':  'hold_template_5x5',  # or None
          'delay_template':       'delay_template_5x5',
          'mpw_template':         'mpw_template',
          'si_immunity_template': None,
      }},
      'arcs':      [{
          'cell':           'DFFQ1',
          'arc_type':       'combinational',
          'pin':            'Q',
          'pin_dir':        'rise',
          'rel_pin':        'CP',
          'rel_pin_dir':    'rise',
          'when':           '!SE&SI',
          'lit_when':       'notSE_SI',
          'probe_list':     ['Q'],
          'metric':         '',
          'metric_thresh':  '',
          'vector':         'RxxRxx',
      }],
      'global': <existing structure, preserved for legacy callers>,
    }
    """
```

**Deferred to 2b:**
- `define_index` override blocks (per-(pin, rel_pin, when) overrides of index_1/index_2)
- SIS template sidecar (`Template_sis/*.sis`) parsing for pintype glitch thresholds

---

## 5. Collateral Store

### 5.1 Class API

```python
class CollateralStore:
    def __init__(self, collateral_root, node, lib_type):
        """Load manifest.json; auto-regenerate if stale."""
        self.root     = os.path.join(collateral_root, node, lib_type)
        self.node     = node
        self.lib_type = lib_type
        self.manifest = self._load_or_rescan()

    def list_corners(self) -> list[str]
    def list_cells(self) -> list[str]
    def get_corner(self, corner_name) -> dict                   # abs paths
    def pick_char_file(self, corner_name, arc_type) -> str | None
    def pick_model_file(self, corner_name, arc_type) -> str | None   # uses extsim_model_include
    def get_usage_l(self, corner_name) -> str | None                 # informational
    def get_template_tcl(self, corner_name) -> str | None
    def get_netlist_dir(self, corner_name) -> str | None


class CollateralError(ResolutionError):
    """Raised on lookup failure. Always includes actionable suggestions."""
```

### 5.2 `pick_char_file` precedence

For each (corner_name, arc_type):
1. `combined` (corner-specific, covers both cons + non_cons)
2. `cons` for constraint arcs / `non_cons` for non-cons arcs (corner-specific)
3. `group_combined` (group-level)
4. `group_cons` / `group_non_cons` (group-level)

Logs the chosen path so parity issues are traceable.

### 5.3 `pick_model_file` implementation

Per Section 4.3: parse char*.tcl for `extsim_model_include`, normalize arc_type, look up.

### 5.4 Error reporting

Every lookup failure raises `CollateralError` listing:
1. what was asked for (node, lib_type, corner, arc_type, cell)
2. what the manifest has (sorted closest matches, truncated to 10)
3. how to fix (re-run `tools/scan_collateral.py`, check path, etc.)

Example:
```
CollateralError: No corner 'ssgnp_0p450v_m40c' in node 'N2P_v1.0' / lib_type 'tcb02p_..._svt'
  x Closest matches (did you mean?):
  x   - ssgnp_0p450v_m40c_cworst_CCworst_T
  x   - ssgnp_0p450v_m40c_typical_T
  x Note: corners include the RC subtype suffix.
  x Manifest: collateral/N2P_v1.0/tcb02p_..._svt/manifest.json
```

---

## 6. Arc Info Builder (`core/arc_info_builder.py`)

Faithful port of `parseQACharacteristicsInfo()` from `1-general/timingArcInfo/funcs.py`, scoped to non-cons arcs.

```python
def build_arc_info(
    arc:          dict,           # one entry from template_info['arcs']
    cell_info:    dict,           # template_info['cells'][cell_name]
    template_info: dict,          # full template.tcl parse output
    chartcl:      ChartclParser,  # parsed char*.tcl
    corner:       dict,           # manifest corner entry (abs paths)
    netlist_path: str,
    netlist_pins: str,
    include_file: str,
    waveform_file: str,
    overrides:    dict,           # user overrides (vdd, temp, etc.)
) -> dict:
    """Produce the complete arc_info dict for a non-cons arc.

    Returns a dict with the fields listed below. Missing fields are set to
    '' (empty string) -- MCQC parity.
    """
```

### 6.1 Fields produced (non-cons subset)

**Core arc attributes:**
- `CELL_NAME`, `ARC_TYPE`
- `REL_PIN`, `REL_PIN_DIR`
- `CONSTR_PIN`, `CONSTR_PIN_DIR` (for non-cons: `CONSTR_PIN = REL_PIN`, `CONSTR_PIN_DIR = REL_PIN_DIR`)
- `OUTPUT_PINS` (space-joined string)
- `SIDE_PIN_STATES` (space-joined `"pin=0|1"` tuples)
- `DONT_TOUCH_PINS` (space-joined)
- `PROBE_PIN_1`, `PROBE_PIN_2`, ... (from arc['probe_list'], indexed)
- `WHEN`, `LIT_WHEN`  (two separate fields; WHEN = literal "!SE&SI", LIT_WHEN = encoded "notSE_SI")
- `HEADER_INFO` (template_info['global'].get('header_info', ''))
- `TEMPLATE_PINLIST` (cell_info['pinlist'])
- `VECTOR` (arc['vector'])

**Index values** (with correct units):
- `INDEX_1_INDEX`, `INDEX_1_VALUE` (always suffix `'n'`)
- `INDEX_2_INDEX`, `INDEX_2_VALUE` (suffix `'p'` for non-cons load, `'n'` for constraint slew)
- `INDEX_3_INDEX` (None for non-cons; 2b adds 3D expansion)
- `OUTPUT_LOAD` (derived: `index_2[idx-1] + unit`)
- `MAX_SLEW` (max of index_1 list, + `'n'`)

**Environment:**
- `VDD_VALUE`, `TEMPERATURE`  (from corner entry or override)
- `INCLUDE_FILE` (model file resolved via `pick_model_file`)
- `WAVEFORM_FILE` (config default; user override wins)
- `NETLIST_PATH`, `NETLIST_PINS`
- `TEMPLATE_DECK` (resolved template path from `TemplateResolver`)
- `TEMPLATE_TCL` (per-corner template.tcl path)

**Metrics (from `resolve_chartcl_for_arc`):**
- `GLITCH` (empty for non-cons unless chartcl provides a non-hold global)
- `PUSHOUT_PER`, `PUSHOUT_DIR`

### 6.2 Fields NOT produced (deferred to 2b)

- 3D expansion: the builder emits **one** arc_info; if `constraint_template` matches `5x5x5`, a TODO flag `_constraint_is_3d: True` is attached so 2b can split.
- `define_index` overrides
- SIS-template `{PINTYPE}_GLITCH_HIGH_THRESHOLD` / `_LOW_THRESHOLD`
- Per-arc `metric` / `metric_thresh` extraction
- MPW-only: `MPW_INPUT_THRESHOLD`

### 6.3 Arc-type normalization table

Implemented inside `build_arc_info` and `pick_model_file`:
```python
ARC_TYPE_NORMALIZATION = {
    # -> 'mpw'
    'min_pulse_width': 'mpw',  'mpw': 'mpw',
    # -> 'delay'
    'combinational':        'delay', 'edge':         'delay',
    'combinational_rise':   'delay', 'combinational_fall': 'delay',
    'rising_edge':          'delay', 'falling_edge': 'delay',
    'three_state_enable':   'delay', 'three_state_disable': 'delay',
    'clear':                'delay', 'preset':       'delay',
    # startswith('nochange') -> 'nochange' (handled via prefix check, not the dict)
    # else -> arc_type as-is (constraint arcs: hold, setup, removal, recovery, non_seq_*, si_immunity)
}
```

---

## 7. Resolver Integration

```python
def resolve_all_from_collateral(
    cell_name, arc_type, rel_pin, rel_dir, constr_pin, constr_dir, probe_pin,
    node, lib_type, corner_name,
    collateral_root='collateral',
    templates_dir=None, registry_path=None,
    overrides=None,
    template_override=None, netlist_override=None, pins_override=None,
) -> dict:
    """Single-arc resolver that pulls every input from the collateral manifest.

    Steps:
    1. Load CollateralStore(collateral_root, node, lib_type)
    2. store.get_corner(corner_name) -> absolute paths
    3. TemplateResolver.resolve(...) (existing) -> SPICE template path
    4. NetlistResolver.resolve(...) (existing) -> netlist + pins
    5. parse_template_tcl_full(corner.template_tcl) -> template_info
    6. chartcl_parse_all(pick_char_file(corner, arc_type)) -> ChartclParser
    7. pick_model_file(corner, arc_type) via extsim_model_include
    8. Find arc in template_info['arcs'] matching (cell, arc_type, pin, rel_pin, when)
    9. arc_info_builder.build_arc_info(...)
    10. Return arc_info
    """
```

The existing `resolve_all()` stays unchanged for backward compat (single-arc CLI path with raw files). Tests that use it continue passing.

`core/batch.plan_jobs()` gains `node` and `lib_type` parameters:
- When both given -> collateral path (calls `resolve_all_from_collateral`)
- When absent -> legacy path (current behavior)

---

## 8. Deck Builder Substitutions

Extend `core/deck_builder.build_deck()` substitution loop to cover every non-cons arc_info key. Missing keys substitute to `''` (MCQC parity).

**New substitutions:**
```
$WHEN, $LIT_WHEN, $VECTOR, $SIDE_PIN_STATES, $DONT_TOUCH_PINS,
$OUTPUT_PINS, $TEMPLATE_PINLIST, $HEADER_INFO,
$INDEX_1_INDEX, $INDEX_1_VALUE, $INDEX_2_INDEX, $INDEX_2_VALUE, $INDEX_3_INDEX,
$OUTPUT_LOAD, $MAX_SLEW,
$GLITCH, $PUSHOUT_PER, $PUSHOUT_DIR,
$TEMPLATE_DECK, $TEMPLATE_TCL
```

Existing substitutions (`$CELL_NAME`, `$VDD_VALUE`, `$TEMPERATURE`, `$INCLUDE_FILE`, `$WAVEFORM_FILE`, `$REL_PIN`, etc.) are unchanged.

---

## 9. CLI & GUI

### 9.1 `deckgen.py` new flags

```bash
--node N2P_v1.0
--lib_type tcb02p_bwph130pnpnl3p48cpd_base_svt
--corners ssgnp_0p450v_m40c_cworst_CCworst_T,ttgnp_0p800v_25c_typical_T
--rescan              # force manifest regeneration before running
```

Validation:
- If `--node` is given, `--lib_type` is required (error lists available lib_types for that node).
- If `--node` + `--lib_type` given, `--netlist_dir` / `--model` flags are IGNORED with a warning (manifest wins).
- If neither `--node` nor raw paths are given -> error showing both usage modes.

### 9.2 GUI updates

- Two new dropdowns populated from `collateral/*/*/manifest.json`:
  - `Node` dropdown (scans `collateral/*`)
  - `Lib type` dropdown (scans `collateral/{node}/*`, repopulates on node change)
- Corner/cell lists auto-populate from the selected `{node, lib_type}` manifest.
- "Rescan collateral" button -> runs `tools/scan_collateral.py --all`.
- Raw-file mode remains available via a mode toggle for backward compat.

---

## 10. Tests

All existing 96 tests must still pass.

New tests:

**`tests/test_chartcl_parser.py`** -- golden fixtures under `tests/fixtures/chartcl/`:
- `general_set_vars.tcl` -- all 3 constraint vars + `-stage variation` form
- `mpw_set_vars.tcl` -- forward iteration + sentinel + `mpw_input_threshold`
- `conditions_load.tcl` -- multiple cells via `string compare`, elseif chains
- `conditions_glitch.tcl` -- numeric values including scientific notation
- `conditions_pushout.tcl`
- `combined.tcl` -- cons + non_cons merged
- `last_match_wins.tcl` -- same cell in two if-blocks, verify last value kept
- `amd_glitch.tcl` -- `set_config_opt -type {*hold*}` block with `-cell {...}`
- `smc_degrade.tcl`

All assertions use **string-typed** expected values (MCQC's own test assertions are buggy; we match the implementation, not the buggy tests).

**`tests/test_chartcl_helpers.py`** -- `read_chartcl`, `parse_chartcl_for_cells`, `parse_chartcl_for_inc`.

**`tests/test_template_tcl_full.py`** -- `parse_template_tcl_full` on a fixture template.tcl with 1 cell, 2 arcs (one delay, one hold). Asserts cells / arcs / templates sections populated correctly.

**`tests/test_scan_collateral.py`** -- synthetic collateral fixture under `tests/fixtures/collateral/N2P_v1.0/test_lib/` with 2 corners + 1 group file. Runs scanner, asserts manifest.json matches expected.

**`tests/test_collateral_store.py`** -- covers `pick_char_file` precedence chain, `pick_model_file` with `extsim_model_include`, `CollateralError` with suggestions on lookup miss.

**`tests/test_arc_info_builder.py`** -- golden test: one cell, one non-cons arc, hand-crafted fixtures, assert every arc_info field individually (not as blob).

**`tests/test_resolve_from_collateral.py`** -- integrated: `resolve_all_from_collateral()` for a delay arc. Asserts GLITCH/PUSHOUT_PER from char*.tcl, INDEX_*_VALUE from template.tcl, INCLUDE_FILE from `extsim_model_include`.

**`tests/test_end_to_end_non_cons.py`** -- 1 cell x 1 non-cons arc x 1 corner. Generates a full deck. Byte-compare against a golden SPICE output (or spot-check a subset of lines if exact byte match is too brittle).

---

## 11. Parity Bugs Preserved

Documented inline with `# MCQC parity:` comments where intentionally replicated:

- ChartclParser stores values as strings (MCQC tests assert numeric -- tests are buggy; implementation is the source of truth).
- Last-match-wins in `parse_condition_*` methods.
- AMD multi-`-cell` block overwrite.
- No TCL preprocessing (`$var` expansion, comment stripping, brace matching).
- `constraint_output_load` value strips `index_` prefix.

---

## 12. Non-Goals (Explicit)

- No import/copy tool. Users place SCLD files manually.
- No library file (`.lib`) handling. Only `.inc` / `.usage.l` are in scope.
- No 3D constraint expansion (5x5x5 -> 3 decks). Deferred to 2b.
- No `define_index` overrides. Deferred to 2b.
- No SIS template sidecar parsing. Deferred to 2b.
- No per-arc `metric` / `metric_thresh` extraction. Deferred to 2b.
- No MPW-specific skip logic (MB / SYNC / CKL cell arc filtering). Deferred to 2b or a separate MPW parity spec.
- No SPICE post-processing helpers (`post_mb_an2`, `post_lnd2sr`, etc.). Outside DeckGen's scope.

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| char*.tcl regex is fragile -- real files may have unseen patterns | Scanner logs unmatched files as warnings, not errors. Parser fixtures cover the variants we know about; we iterate as validation fails expose new patterns. |
| Group-level char*.tcl regex assumption may be wrong | `scan_collateral.py` logs which files matched which group key; review manifest after first scan. |
| MCQC's `parseQACharacteristicsInfo` has implicit behaviors not captured in the audit | Golden-test deck-level byte-diff against a known-good MCQC deck before closing 2a. First mismatched line -> new test case + fix. |
| `template.tcl` per-corner assumption (user override of audit finding) may conflict with MCQC internals | If validation diffs appear, re-examine shared-vs-per-corner handling in MCQC batch flow. |

---

## 14. Acceptance Criteria

1. All 96 existing tests + new 2a tests pass.
2. `python3 tools/scan_collateral.py --all` produces manifest.json for every populated leaf, with zero warnings on a well-formed SCLD delivery.
3. `python3 deckgen.py --node N2P_v1.0 --lib_type <lib> --corners <corner> --arcs_file ...` generates decks that match MCQC output for **delay and slew arcs** (byte-diff or spot-check).
4. Non-ASCII scan across the new files returns empty.
5. `docs/task.md` updated with 2a completion + 2b open items.

---

## 15. Handoff to Point 2b (Constraint Parity)

Point 2b builds on 2a's foundation and adds:
- 3D constraint detection (5x5x5) and deck expansion (1 -> 3 decks with `-2`, `-3`, `-4` suffixes).
- `define_index` override matching in `parse_template_tcl_full`.
- SIS template parser -- `Template_sis/*.sis` files with per-pintype glitch thresholds injected as `{PINTYPE}_GLITCH_HIGH_THRESHOLD` etc.
- Per-arc `metric` / `metric_thresh` extraction from `define_arc` blocks.
- Constraint-arc verification against MCQC.
- Optional: MPW skip logic (MB/SYNC/CKL cell arc filtering) for a full-MPW validation.
