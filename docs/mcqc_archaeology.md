# MCQC Archaeology

Reverse-engineering of MCQC v3.5.5 (`scld__mcqc.py` + supporting modules).
Source: `/Users/nieyuxuan/Downloads/Work/4-MCQC/mcqc_flow/1-general/`.

This document is precise enough that someone could reimplement MCQC from it.

> **Erratum** (2026-05-06): This document originally stated that
> `templateFileMap/funcs.py` was "not available locally." This was incorrect.
> The file exists at `/Users/nieyuxuan/Downloads/Work/4-MCQC/mcqc_flow/2-flow/funcs.py`
> (18,624 lines, containing `mapCharacteristicsToTemplate` at line 21,
> `getHspiceTemplateName` at line 67, `getThanosTemplateName` at line 14,753).
> See `docs/foundation/A_templatefilemap_check.md` for the authoritative
> source analysis and 30-rule extraction fidelity check.
>
> Three sections below are superseded by this finding:
> - SS5h (Template deck selection) -- marked inline
> - Q1 (templateFileMap Source) -- marked inline
> - Appendix C row "Template deck map" -- marked inline

> **Phase 1.5 Supersessions** (2026-05-06):
> - Section 3.8 (templateFileMap as black box): **Superseded** by
>   `docs/foundation/A_templatefilemap_check.md`. The file IS locally available
>   at `mcqc_flow/2-flow/funcs.py` (18,624 lines). 26/30 sampled rules verified
>   exact; 4/30 have incomplete OR-alternative extraction.
> - Q2 (do same-signature rules map to same template?): **Answered** by
>   `docs/foundation/B_rule_groupby.md`. No -- 71% of rules are in
>   discriminating groups where cell pattern matters. But the discrimination
>   follows 8 categorizable patterns, not arbitrary per-cell overrides.
> - Template path structure: **Analyzed** in
>   `docs/foundation/C_template_path_clusters.md`. 457 templates, 412 families,
>   98.9% covered by a BNF grammar with 142-token vocabulary.
> - Shipped template calibration: **Validated** in
>   `docs/foundation/D_template_calibration.md`. All 63 shipped MPW templates
>   are structurally consistent; zero inconsistencies with rule predictions.

---

## 1. Pipeline Stage Map

### Overview

MCQC generates SPICE decks for Monte Carlo quality checking of library
characterization. The pipeline has 7 sequential stages:

```
CLI Input + globals.cfg
        |
        v
[Stage 1] Input Parsing & Globals Loading
        |
        v
[Stage 2] Kit Path Resolution (template.tcl, char.tcl, netlist, model)
        |
        v
[Stage 3] Template.tcl Parsing (charTemplateParser)
        |
        v
[Stage 4] Char.tcl Parsing (chartcl_helper)
        |
        v
[Stage 5] Arc Extraction & Template Deck Selection (qaTemplateMaker)
        |
        v
[Stage 6] SPICE Info Assembly (timingArcInfo)
        |
        v
[Stage 7] Deck Generation & File Output (spiceDeckMaker)
```

### Stage 1: Input Parsing & Globals Loading

**Files**: `scld__mcqc.py:148-221`, `globalsFileReader/funcs.py`

**Input**: CLI args (`--globals_file`, `--lib_type`, `--lg`, `--vt`, `--corner`,
`--output_path`, `--char_type`, `--spice_deck_format`)

**Output**: `user_options` dict with all config merged

**Process**:
1. Parse CLI args via `getopt` (`scld__mcqc.py:148-221`)
2. Load defaults (`globalsFileReader/funcs.py:54-80`):
   - `PUSHOUT_PER = "0.4"`
   - `PUSHOUT_DIR = "POSITIVE"`
   - `CELL_PATTERN_LIST = ["*D1B*"]` (only D1-size cells by default)
   - `VALID_ARC_TYPES_LIST = ["hold", "removal"]` (constraints only by default)
   - `MAX_NUM_WHEN = 1`
   - `NUM_SAMPLES = 5000`
3. Read globals file (`globalsFileReader/funcs.py:9-51`):
   - `set_var` lines parsed, `_list` suffix vars treated as space-delimited lists
   - Key vars: `KIT_PATH`, `TEMPLATE_DECK_PATH`, `TEMPLATE_LUT_PATH`,
     `USER_MODEL_FILE`, `WAVEFORM_FILE`, `CELL_PATTERN_LIST`,
     `VALID_ARC_TYPES_LIST`, `TABLE_POINTS_LIST`, `MAX_NUM_WHEN`, `NUM_SAMPLES`
4. Construct `lgvt = lg + vt` (e.g., "8svt")
5. Insert `TEMPLATE_LUT_PATH` into `sys.path` for dynamic import of
   `templateFileMap` module (`scld__mcqc.py:403-414`)

**Failure modes**:
- Missing globals file: Python traceback, no structured error
- Missing `TEMPLATE_LUT_PATH`: `sys.exit` with message about missing variable

**Silent drops**: None at this stage.

**Principled vs empirical**: Principled -- straightforward config loading.

---

### Stage 2: Kit Path Resolution

**Files**: `scld__mcqc.py:224-330`

**Input**: `user_options` with `KIT_PATH`, `lib_type`, `lgvt`, `corner`

**Output**: Paths added to `user_options`:
- `TEMPLATE_FILE` -- path to `*.template.tcl`
- `CHARTCL_FILE` -- path to `char_*.tcl`
- `VDD_VALUE` -- extracted from char.tcl (`set VOLT ...`)
- `TEMPERATURE` -- extracted from char.tcl (`set TEMP ...`)
- `ROOT_NETLIST_PATH` -- netlist directory
- `INCLUDE_FILE_LOOKUP` -- model card paths per arc type

**Process**:
1. Template file: glob `{kit_path}/{lib_type}/{lgvt}/Template/*{corner}*.template.tcl`
   - HOLD_TAX/HT variants: path includes `/HOLD_TAX/` or `/HT/` subdirectory
   - Must find exactly 1 match; 0 or 2+ is fatal (`scld__mcqc.py:237-252`)
2. Char file: glob `{kit_path}/{lib_type}/{lgvt}/Char/char_{corner}{char_type}.tcl`
   - `char_type` suffix: `.cons`, `.non_cons`, `.cons_mixvt`, `.non_cons_mixvt`,
     or empty (`scld__mcqc.py:255-261`)
3. VDD: grep `set VOLT` in char.tcl, take last word (`scld__mcqc.py:300-303`)
4. Temperature: grep `set TEMP` in char.tcl, take last word (`scld__mcqc.py:306-309`)
5. Netlist path: scan char.tcl bottom-up for line containing both `Netlist` and
   `spi`, extract subdirectory name (`scld__mcqc.py:312-324`)
6. Include file: parse `set_var extsim_model_include` from char.tcl, keyed by
   `-type` (e.g., hold, mpw, traditional) (`hybrid_char_helper.py:20-53`)
7. Copy include files to output dir (`scld__mcqc.py:339-361`) -- includes a
   3-second `time.sleep(3)` (likely NFS sync workaround)

**Failure modes**:
- Template count != 1: `ValueError` with count + pattern shown
- Char file count != 1: `ValueError` with count + pattern shown
- Netlist path parse fail: `UnboundLocalError` on `netlist_subdir` -- **silent crash**

**Silent drops**: The netlist path extraction scans bottom-up and takes the
first `Netlist` + `spi` match. If char.tcl structure differs, wrong path is
silently used.

**Principled vs empirical**:
- Directory structure convention is empirical (hardcoded path format)
- VDD/temp extraction via grep is fragile but principled

---

### Stage 3: Template.tcl Parsing

**Files**: `charTemplateParser/funcs.py` (636 lines), `charTemplateParser/classes.py`
(560 lines)

**Input**: `template_file` path

**Output**: `TemplateInfo` object containing:
- `_tool_vars`: dict of `set_var` variables
- `_tcl_vars`: dict of `set` variables (includes `cells` list)
- `_define_template_list`: dict of `DefineTemplateInfo` (index axes definitions)
- `_cell_list`: dict of `Cell` objects (each with arcs, index overrides)
- `_sis_template`: dict of SIS glitch threshold vars

**Process** (line-by-line scan using `linecache`):

1. `set_var` lines -> `_tool_vars` (`funcs.py:122-160`)
2. `set` lines -> `_tcl_vars` (`funcs.py:163-244`)
   - Multi-line brace-delimited lists: `set cells { ... }` parsed into a set
   - **Bug/quirk**: uses `set()` not `list()`, so cell order is lost
3. `define_template` blocks -> `DefineTemplateInfo` (`funcs.py:247-329`)
   - Reads `-type`, `-index_1`, `-index_2`, `-index_3`, and block name
   - Block name is the last non-continuation line (no trailing `\`)
4. `define_cell` blocks -> `Cell` objects (`funcs.py:332-431`)
   - Reads `-pinlist`, `-input`, `-output`, `-clock`, `-delay`, `-constraint`,
     `-mpw`, `-async`, `-scan`, `-power`, `-harness`, `-internal`, etc.
   - **Quirk**: `-async` renamed to `aasync` to avoid Python keyword collision
     (`funcs.py:424-426`)
   - `-when` blocks are **skipped entirely** (`funcs.py:371-382`) -- the parser
     advances past multi-line when blocks without storing them
   - `-user_arcs_only` flag is skipped (`funcs.py:368-369`)
5. `define_arc` blocks -> `Arc` objects (`funcs.py:435-483`)
   - Reads all `-flag value` pairs into dict
   - **Critical default**: if `type` not in arc dict, sets `type = 'combinational'`
     (`funcs.py:481`)
   - **Critical default**: if `when` not in arc dict, sets `when = 'NO_CONDITION'`
     (`funcs.py:478-479`)
6. `define_index` blocks -> `Index` objects (override entries) (`funcs.py:527-612`)
   - Contains `-pin`, `-related_pin`, `-when`, `-type`, `-index_1`, `-index_2`
   - Used to override the default index axes for specific pin/arc combinations
7. SIS template (`funcs.py:79-102`): if `Template_sis/` sibling exists, parse
   `glitch_high_threshold` / `glitch_low_threshold` per pintype

**Failure modes**:
- Malformed block (no closing line without `\`): infinite loop reading empty lines
- `define_cell` with no name: `sys.exit(0)` with error message

**Silent drops**:
- Cell-level `-when` conditions are silently discarded
- `define_cell` attributes not in the `Cell.__init__` parameter list cause
  `TypeError` -- the parser does not handle unknown attributes gracefully

**Principled vs empirical**:
- The block-parsing structure is principled (it mirrors Liberate's grammar)
- The `linecache`-based line-by-line scan is empirical (no proper tokenizer)
- The `type='combinational'` default is a **critical methodology rule**

---

### Stage 4: Char.tcl Parsing

**Files**: `chartcl_helper/parser.py` (117 lines), `hybrid_char_helper.py` (69 lines)

**Input**: `CHARTCL_FILE` path

**Output**: `ChartclParser` object with:
- `vars`: dict of extracted settings
  - `constraint_glitch_peak`: glitch threshold for constraint arcs
  - `constraint_delay_degrade`: pushout percentage
  - `constraint_output_load`: which index to use for output load
  - `smc_degrade`: AMD-specific pushout override
  - `amd_glitch`: AMD-specific glitch thresholds (per cell pattern)
- `conditions`: dict of per-cell overrides (glitch, pushout, output load index)
- `set_cells`: list of cells from `set cells { ... }` blocks

**Process**:
1. Parse `set_var constraint_glitch_peak` (reverse scan, last value wins)
2. Parse `set_var constraint_delay_degrade` (same)
3. Parse `set_var constraint_output_load` -> strip `index_` prefix
4. Per-cell condition overrides via regex on `if { [string compare "$cell" ...}`
   patterns (`parser.py:45-69`)
5. AMD-specific: `set_config_opt -type {*hold*} ... glitch_high_threshold`
   blocks parsed into `amd_glitch` dict (`parser.py:78-115`)
6. AMD-specific: `set_config_opt -type lvf smc_degrade` -> `smc_degrade`
7. Cell list: parse `set cells { ... }` blocks (`hybrid_char_helper.py:56-67`)

**Failure modes**:
- Regex patterns are fragile -- whitespace variations or multi-line formats
  may cause silent miss

**Silent drops**:
- Char.tcl vars not matching the hardcoded patterns are silently ignored
- If `constraint_glitch_peak` appears before last occurrence, earlier values
  are overwritten without warning

**Principled vs empirical**:
- Entirely empirical. The regexes are hand-tuned to known char.tcl formats.
- The AMD-specific paths (`smc_degrade`, `amd_glitch`) are vendor-specific
  extensions layered onto the base flow.

---

### Stage 5: Arc Extraction & Template Deck Selection

**Files**: `qaTemplateMaker/funcs.py` (888 lines), `templateFileMap/funcs.py`
(not available locally -- on remote server)

**Input**: `TemplateInfo`, `valid_arc_types`, `cell_pattern_list`,
`template_deck_type`, `chartcl_file`

**Output**: `arc_list` -- list of `ArcInfo` objects, each with:
- Cell name, arc type, pin, pin_dir, rel_pin, rel_pin_dir
- When condition (both logical and literal forms)
- Probe list, output pinlist, cell pinlist
- Index_1 (slew), index_2 (slew/load), index_3 (3D constraint load)
- Output load value
- Side pin states
- Template deck path (from templateFileMap)
- Metric, metric_thresh, vector

**Process** (`getQAArcCharacteristics`, `funcs.py:217-322`):

```
for each cell in template_info:
    if cell not in cell_pattern_list: SKIP
    if cell not in tcl_vars['cells']: SKIP        # <-- dual filter
    if cell has 0 arcs: SKIP
    get cell_pinlist, output_pinlist
    sort arcs
    for each arc:
        get arc_type
        if arc_type not in valid_arc_types: SKIP   # <-- type filter
        get index_1, index_2, index_3 (with define_index overrides)
        get output_load (default index_2[2], or per-cell override)
        get pin, rel_pin, when, probe_list, vector
        get pin_dir, rel_pin_dir (from vector + pinlist position)
        get metric, metric_thresh
        if NO_CONDITION: extract side_pin_state from vector
        MAP to template deck via templateFileMap.mapCharacteristicsToTemplate()
        CHECK when-count limit (max_num_when per (arc_type, pin, rel_pin, vector))
        if 3D constraint (5x5x5): expand into 3 ArcInfo objects (index_3 = 1,2,3)
        else: create 1 ArcInfo object
        if template_deck is not None: count as identified
```

**Key sub-operations**:

#### 5a. Cell validation (`checkValidCell`, `funcs.py:677-714`)
- Custom glob matching (not `fnmatch`): handles `*prefix*`, `prefix*`, `*suffix`,
  and exact match separately
- **Dual filter**: cell must match BOTH `cell_pattern_list` AND `tcl_vars['cells']`
  (`funcs.py:244`)

#### 5b. Arc type validation (`checkValidArc`, `funcs.py:734-770`)
- If `valid_arc_types` includes `"delay"` or `"slew"`, the following types are
  **automatically added** (`funcs.py:754-764`):
  - `combinational`, `combinational_fall`, `combinational_rise`
  - `falling_edge`, `rising_edge`
  - `three_state_disable`, `three_state_enable`
  - `clear`, `preset`, `edge`
- This is a **critical methodology rule**: "delay" is not a template.tcl type;
  it is an umbrella covering all non-constraint arcs that produce output transitions

#### 5c. Index resolution with overrides (`getIndexEntriesForArc`, `funcs.py:542-594`)
- Default indices come from the `define_template` block referenced by the cell's
  `-delay`, `-constraint`, or `-mpw` attribute
- Override path: `define_index` blocks can override `index_1` and `index_2`
  for specific `(pin, related_pin, when)` combinations
- Matching priority: exact pin match > wildcard pin match > no override
- Arc type determines which template to look up:
  - constraint types (hold, removal, setup, recovery, nochange, min_pulse_width)
    -> `cell.constraint()`
  - mpw -> `cell.mpw()`
  - si_immunity -> `cell.siImmunity()`
  - everything else (delay/slew/combinational) -> `cell.delay()`

#### 5d. Output load resolution (`getCellOutputLoad`, `funcs.py:489-539`)
- Default: `index_2[load_index]` where `load_index=2` (3rd entry, 0-based)
- Per-cell override: char.tcl's `constraint_output_load` regex sets custom index
- 3D constraint (5x5x5): returns all 5 `index_3` values, expanded later

#### 5e. Pin direction from vector (`getPinDir`, `funcs.py:819-853`)
- Each character in the vector string maps 1:1 to the pinlist
- `R` -> `rise`, `F` -> `fall`, `1` -> `high`, `0` -> `low`, `x` -> `None`
- **This is a principled operation**: vector encoding is the ground truth for
  pin transition directions

#### 5f. When condition encoding (`parseLogicalWhenCondition`, `funcs.py:379-402`)
- `!SE&SI` -> `notSE_SI` (literal form for filenames)
- Split on `&`, prefix `not` for `!`-prefixed terms

#### 5g. When count limiting (`checkWhenCount`, `funcs.py:405-452`)
- Tracks existing arcs by `(arc_type, pin, rel_pin, vector)` tuple
- If this tuple already has `max_num_when` distinct when conditions stored,
  skip additional when conditions
- Default `max_num_when = 1`: only one when condition per arc signature
- **This is the primary arc-dropping mechanism** -- all but one when condition
  per unique arc shape are silently dropped

#### 5h. Template deck selection (`templateFileMap.mapCharacteristicsToTemplate`)

> [SUPERSEDED -- see foundation/A] The claim below that this module is "not
> available locally" was incorrect. The file is at `mcqc_flow/2-flow/funcs.py`
> (18,624 lines). See `docs/foundation/A_templatefilemap_check.md`.

- ~~**Not available locally**~~ -- this is the 18K-line if-chain ~~on the server~~
  at `mcqc_flow/2-flow/funcs.py`
  that maps `(cell_name, arc_type, pin, pin_dir, rel_pin, rel_pin_dir,
  probe_list, when, template_type)` to a template `.sp` file path
- DeckGen's replacement: `core/template_rules.py` with 688 HSPICE rules
  extracted from the if-chain as JSON
- If no match: returns `None` -> arc is **dropped** (with count but no per-arc
  error message)

**Failure modes**:
- Cell in `cell_pattern_list` but not in `tcl_vars['cells']`: silently skipped
- Arc type not in valid list: silently skipped
- Template deck = None: arc counted but not included in output list; only the
  total count is printed (`"Extracted %s arcs"`)

**Silent drops**:
1. Cells not matching `cell_pattern_list` -- no message
2. Cells not in `tcl_vars['cells']` (char.tcl's `set cells`) -- no message
3. Arc types not in `valid_arc_types` expanded set -- no message
4. When conditions beyond `max_num_when` -- no message
5. Arcs with no template deck match -- counted in total but not in `num_arcs_identified`;
   no per-arc diagnostic

---

### Stage 6: SPICE Info Assembly

**Files**: `timingArcInfo/funcs.py` (410 lines)

**Input**: `arc_list` (from Stage 5), physical parameters (netlist_path, slew
indices, VDD, temperature, waveform, include files, pushout settings,
chartcl vars/conditions)

**Output**: `spice_info` dict keyed by `table_point` -> `arc_count` -> arc dict

**Process** (`parseQACharacteristicsInfo`, `funcs.py:15-159`):

For each `table_point` in `TABLE_POINTS_LIST` (e.g., `"(1,1)"`, `"(3,3)"`):
  For each arc in `arc_list` (skipping `template_deck == None`):
  1. Determine include file by mapping arc_type -> key in `include_file_lookup`:
     - `min_pulse_width`/`mpw` -> `'mpw'`
     - `nochange*` -> `'nochange'`
     - `combinational`/`edge` -> `'delay'`
     - others -> arc_type as-is
     - Fallback: if only one entry (`'traditional'`), use that
  2. Build `HEADER_INFO` string (arc info + slew info + template deck info)
  3. Resolve netlist path: try `{cell}_c_qa.spi`, then `{cell}_c.spi`, then
     `{cell}.spi` (`funcs.py:390-402`)
  4. Extract `NETLIST_PINS` from `.subckt` line in netlist file
  5. Select `INDEX_1_VALUE` and `INDEX_2_VALUE` from the arc's index lists
     using 1-based table point indices
  6. For delay arc types: `INDEX_2_VALUE` gets `'p'` suffix (load in pF)
     For constraint arc types: `INDEX_2_VALUE` gets `'n'` suffix (slew in ns)
     (`funcs.py:361-370`)
  7. `OUTPUT_LOAD` gets `'p'` suffix (`funcs.py:310-311`)
  8. `MAX_SLEW` = max of index_1 and index_2, gets `'n'` suffix
  9. Apply chartcl overrides:
     - `constraint_glitch_peak` -> `GLITCH`
     - `amd_glitch` -> `GLITCH` (cell-specific or hold-specific or default)
     - `constraint_delay_degrade` / `smc_degrade` -> `PUSHOUT_PER`
     - Per-cell conditions from chartcl -> override `GLITCH`, `PUSHOUT_PER`
     - Per-arc `metric_thresh` -> override `GLITCH`, `PUSHOUT_PER`
  10. SIS template vars (glitch thresholds per pintype) added to arc dict
  11. `VECTOR` stored for deck generation
  12. `VALID_ARC = True` (default; can be overridden by arc filter)

**Key data fields in output arc dict**:
```
ARC_TYPE, TEMPLATE_DECK, HEADER_INFO, CELL_NAME, NETLIST_PATH,
REL_PIN, REL_PIN_DIR, CONSTR_PIN, CONSTR_PIN_DIR, OUTPUT_PINS,
SIDE_PIN_STATES, PROBE_PIN_1..N, WHEN, LIT_WHEN, OUTPUT_LOAD,
TEMPLATE_PINLIST, MAX_SLEW, NETLIST_PINS, INDEX_1_INDEX, INDEX_1_VALUE,
INDEX_2_INDEX, INDEX_2_VALUE, INDEX_3_INDEX, VDD_VALUE, TEMPERATURE,
WAVEFORM_FILE, INCLUDE_FILE, PUSHOUT_PER, PUSHOUT_DIR, GLITCH,
VECTOR, VALID_ARC
```

**Failure modes**:
- Netlist file not found: `FileNotFoundError` when reading `.subckt` line
- Include file key mismatch: `ValueError` with message about missing .inc file
- `INDEX_1_VALUE` / `INDEX_2_VALUE` index out of range: `IndexError`

**Silent drops**: None -- arcs with `template_deck == None` were already
filtered in Stage 5.

**Principled vs empirical**:
- The delay/constraint distinction for index suffixes (`'p'` vs `'n'`) is
  principled (reflects the physical meaning: load for delay, slew for constraint)
- The glitch/pushout override cascade is empirical (vendor-specific layering)
- The netlist fallback chain (`_c_qa.spi` -> `_c.spi` -> `.spi`) is empirical

---

### Stage 7: Deck Generation & File Output

**Files**: `spiceDeckMaker/funcs.py` (455 lines), `runMonteCarlo.py:119-279`,
`vcp_helper.py`

**Input**: `spice_info` dict, template deck directory, output path, num_samples

**Output**: Directory tree of SPICE deck files:
```
DECKS/
  {arc_type}_{cell}_{constr_pin}_{dir}_{rel_pin}_{dir}_{when}_{point}/
    nominal_sim.sp
    mc_sim.sp
    [VDD_nominal_sim.sp]    # for VCP decks only
    [VSS_nominal_sim.sp]    # for VCP decks only
```

**Process**:

#### 7a. Arc filtering (`runMonteCarlo.py:214-225`)
- Optional CSV filter: if `arc_csv_filter_file` provided, match arcs against
  filter by (cell, arc_type, pin, pin_tran, rel_pin, rel_pin_tran, when, point)
- Non-matching arcs get `VALID_ARC = False`, skipped in generation

#### 7b. Nominal deck generation (`spiceDeckMaker/funcs.py:25-130`)
1. Read template deck file line by line
2. **`$VAR` substitution**: lines containing `$` have variable names replaced
   with values from `arc_info` dict (`funcs.py:291-324`)
   - Variables: `$HEADER_INFO`, `$VDD_VALUE`, `$TEMPERATURE`, `$WAVEFORM_FILE`,
     `$INCLUDE_FILE`, `$NETLIST_PATH`, `$OUTPUT_LOAD`, `$INDEX_1_VALUE`,
     `$INDEX_2_VALUE`, `$PUSHOUT_PER`, `$CELL_NAME`, `$REL_PIN`, `$CONSTR_PIN`,
     `$PROBE_PIN_1`, `$MAX_SLEW`, etc.
3. **Output load section** (`* Output Load`): insert `C{pin} {pin} 0 'cl'`
   for each output pin (`funcs.py:268-279`)
4. **When condition section** (`* Pin definitions`): insert voltage sources
   for side pins (`funcs.py:148-265`):
   - When-condition pins: `V{pin} {pin} 0 'vdd_value'` or `'vss_value'`
     based on `!` prefix
   - Unspecified pins (not in when, not pin/rel_pin/output): default to
     `vdd_value` (high), unless vector specifies `0` or `1`
   - User-fixed side pins: from `SIDE_PIN_STATES` list
   - Don't-touch pins (line 2 of template deck): excluded from all pin
     assignments
5. **Extra power pins** (`* Voltage`): any netlist pin not in template pinlist
   and not a standard power pin (VDD/VSS/VPP/VBB) gets a voltage source
   (`funcs.py:133-145`)
6. **Glitch measurement lines**: special handling for `glitch__minq` and
   `glitch__maxq` header types -- threshold values substituted into `.meas`
   lines (`funcs.py:403-454`)
7. **Pushout measurement**: `pushout_per` lines get `PUSHOUT_PER` value
   substituted (`funcs.py:122-126`)

#### 7c. MC deck generation (`runMonteCarlo.py:183-197`)
- Copy nominal buffer, append `sweep monte={num_samples}` to `.tran` line
- Write as `mc_sim.sp`

#### 7d. VCP (Voltage Compliance Power) decks (`vcp_helper.py`)
- For specific non_seq_hold/non_seq_setup templates (11 hardcoded paths in
  `VCP_DECK` set), generate additional `VDD_nominal_sim.sp` and
  `VSS_nominal_sim.sp` variants
- These replace `VCP CP 0 'vss_value'` with `VCP CP 0 'vdd_value'` (or vice
  versa), or use `_Vdd.sp`/`_Vss.sp` template variants
- PMC (Power Management Cell) template path is hardcoded to server

**Failure modes**:
- Template deck not found: `FileNotFoundError`
- `$VAR` not in `arc_info`: `sys.exit(0)` with error message about missing
  option (`funcs.py:393-400`)
- DONT_TOUCH_PINS line missing from template deck: `IndexError` on line 2

**Silent drops**: None at this stage (arcs already filtered).

**Principled vs empirical**:
- The `$VAR` substitution is principled (clean template instantiation)
- The when-condition pin assignment logic is principled (derives from
  boolean condition + vector encoding)
- The unspecified-pin default (high/vdd) is empirical but defensible
  (most standard-cell side inputs are active-high)
- VCP deck handling is entirely empirical (hardcoded template list)
- The glitch measurement substitution is empirical (pattern-matched against
  specific `.meas` line formats)

---

## 2. Stage-by-Stage Design Notes

### Stage 1: Input Parsing
- **Job**: Merge CLI args, defaults, and globals file into one config dict.
- **Breaking inputs**: Missing globals file; globals file with no `set_var` prefix;
  `_list` suffix on a non-list variable (silently splits on spaces).
- **Logic type**: Principled. Standard config loading.
- **Failure modes**: Missing required vars cause later stages to crash, not this
  stage. No upfront validation.

### Stage 2: Kit Path Resolution
- **Job**: Locate the 4 key files (template.tcl, char.tcl, netlist dir, model)
  from the kit directory structure.
- **Breaking inputs**: Kit path with non-standard directory layout; corner name
  not in any filename; HOLD_TAX/HT subdirectories missing for those modes.
- **Logic type**: Empirical -- hardcoded directory structure convention
  (`{kit_path}/{lib_type}/{lgvt}/[HOLD_TAX|HT/]Template/`).
  Lines `scld__mcqc.py:224-292`.
- **Failure modes**: Template/char file count != 1 raises `ValueError` (good).
  Netlist extraction can fail silently if `'Netlist'` string not found in
  char.tcl bottom-up scan.

### Stage 3: Template.tcl Parsing
- **Job**: Parse Liberate's template.tcl into structured data for downstream arc
  extraction.
- **Breaking inputs**: ALAPI-format template.tcl (not Liberate format);
  `define_arc` blocks with attributes not in `Arc.__init__`; multi-line values
  not using `\` continuation.
- **Logic type**: Principled structure (mirrors Liberate grammar), empirical
  implementation (linecache line-by-line, no tokenizer).
  Critical lines: `funcs.py:477-482` (combinational default).
- **Failure modes**: Unknown `define_cell` attributes cause `TypeError`.
  No handling of malformed blocks.

### Stage 4: Char.tcl Parsing
- **Job**: Extract per-cell and global measurement parameters from the
  characterization configuration file.
- **Breaking inputs**: Char.tcl with different formatting; vendor-specific
  extensions not matching hardcoded patterns.
- **Logic type**: Empirical -- regex-based extraction tuned to known formats.
  Lines: `chartcl_helper/parser.py:24-115`.
- **Failure modes**: Regex miss causes silent omission of glitch/pushout overrides.
  No validation that expected vars were found.

### Stage 5: Arc Extraction
- **Job**: Filter template.tcl arcs by cell pattern + arc type, resolve LUT
  indices, and map each qualifying arc to a SPICE template deck.
- **Breaking inputs**: Cell in pattern list but not in char.tcl cells list;
  arc types not in the hardcoded expansion map; `define_index` overrides with
  ambiguous matching.
- **Logic type**: Mixed. Cell/arc filtering is principled. Index override
  matching is principled (specificity-based). Template deck selection
  (`templateFileMap`) is entirely empirical (18K-line if-chain).
  Critical lines: `funcs.py:244` (dual filter), `funcs.py:754-764` (type
  expansion), `funcs.py:293-296` (template map call).
- **Failure modes**: No template match -> `None` -> arc dropped from count.
  Only the aggregate count is printed, not per-arc diagnostics.
  `max_num_when` drops are completely silent.

### Stage 6: SPICE Info Assembly
- **Job**: Enrich each arc with physical parameters (slew values, load, netlist
  path, model file, VDD, temp) at a specific table point.
- **Breaking inputs**: Table point index exceeding index list length; netlist
  file not found; include file key mismatch.
- **Logic type**: Principled (selects specific LUT point, resolves physical
  files). The glitch/pushout override cascade is empirical.
  Lines: `timingArcInfo/funcs.py:15-159`.
- **Failure modes**: Index out of range -> `IndexError`. Netlist not found ->
  `FileNotFoundError`. Include file mismatch -> `ValueError` with message.

### Stage 7: Deck Generation
- **Job**: Instantiate template SPICE decks by variable substitution, add
  when-condition pin biasing, output load, and measurement configuration.
- **Breaking inputs**: Template deck missing expected `$VAR`; template deck
  without DONT_TOUCH_PINS on line 2; `.meas` lines not matching glitch
  substitution patterns.
- **Logic type**: Principled (template substitution is clean). Glitch/VCP
  handling is empirical.
  Lines: `spiceDeckMaker/funcs.py:25-130` (main substitution).
- **Failure modes**: Missing `$VAR` -> `sys.exit(0)`. Template file not found
  -> `FileNotFoundError`.

---

## 3. Special-Case Inventory

### 3.1 Cell Name Pattern Branching

All 688 HSPICE rules in `template_rules.json` branch on cell name patterns.
Distribution of the 688 rules by arc type:

| arc_type | rules | unique templates |
|----------|-------|------------------|
| hold | 255 | 204 |
| nochange_high_high | 72 | ~35 |
| removal | 67 | ~30 |
| nochange_low_high | 63 | ~30 |
| nochange_low_low | 52 | ~25 |
| non_seq_hold | 49 | 39 |
| nochange_high_low | 36 | ~18 |
| min_pulse_width | 36 | 53 |
| setup | 10 | 10 |
| non_seq_setup | 9 | 8 |
| delay_arc_types | 2 | 2 |

Key cell name patterns that appear in the rules:
- `*SYNC2*`, `*SYNC3*`, `*SYNC4*`, `*SYNC5*`, `*SYNC6*` -- multi-stage synchronizers
- `*RETN*`, `*RET*` -- retention cells
- `*SDFF*`, `*SDF*`, `*DFF*` -- scan/D flip-flops
- `*LATCH*`, `*LAT*` -- latches
- `*CKGMUX*`, `*CKGOR*`, `*CKGAND*` -- clock gating cells
- `*ICG*` -- integrated clock gating
- `*MUX*` -- multiplexers
- `*AO*`, `*OA*`, `*AOI*`, `*OAI*` -- AND-OR / OR-AND gates
- `*BUF*`, `*INV*`, `*DEL*` -- buffers/inverters/delays
- `*TIEL*`, `*TIEH*` -- tie cells

### 3.2 Pin Name Branching

**Trigger**: `rel_pin` or `constr_pin` value in template rules

| Pin pattern | Behavior change | Hypothesized reason |
|-------------|-----------------|---------------------|
| `CP` (clock) | Standard constraint template | Clock-triggered measurement |
| `RETN` | Retention-specific templates with special nodeset | Retention mode entry/exit needs multi-phase stimulus |
| `CD` / `SDN` | Async clear/set templates, glitch measurement | Async control must be checked for glitch-through |
| `SE` / `SI` | Scan-related templates | Scan path sensitization differs from data path |
| `CLKEN` | Clock-gating-specific templates | Clock gating has unique enable timing |
| `AO2`, `CKGMUX3`, `CKGOR2` | MPW templates with specific pin patterns | These cells have non-standard clock paths |

### 3.3 Direction Branching

**Trigger**: `rel_pin_dir` and `constr_pin_dir` in template rules

| Direction combo | Behavior change | Hypothesized reason |
|-----------------|-----------------|---------------------|
| rise/fall | Standard: data captured on rising clock, falls to meet hold | Most common setup/hold scenario |
| fall/rise | Negative-edge triggered | Some cells clock on falling edge |
| rise/rise | Data rises to meet rising clock | Same-direction constraint |
| fall/fall | Data falls to meet falling clock | Same-direction constraint |

Each direction combination requires a different waveform timing in the SPICE
deck (different `t01`-`t07` timing points in the waveform model).

### 3.4 Probe Pin Branching

**Trigger**: `probe.contains` and `probe.len` in template rules

| Probe condition | Behavior change | Hypothesized reason |
|-----------------|-----------------|---------------------|
| Contains `Q1` | Multi-stage sync template (measures at internal Q1) | Sync cells: timing is measured at an internal stage, not final output |
| Contains `bl_b` | SRAM-like template with bitline probe | Memory cells need bitline observation |
| `len == 2` | Two-probe template (e.g., Q and QN) | Complementary output cells need both probes |
| Contains `RETN_out` | Retention output probe | Retention cells have dedicated output observation points |

### 3.5 When Condition Branching

**Trigger**: `when` field in template rules (rare -- only a few rules)

| When condition | Behavior change | Hypothesized reason |
|----------------|-----------------|---------------------|
| `"CLKEN" in when` | Clock-gating hold template variant | When condition contains the clock enable, affecting sensitization path |

### 3.6 Arc Type Expansion for Delay/Slew

**Trigger**: `checkValidArc` in `qaTemplateMaker/funcs.py:750-764`

```python
if "delay" in valid_arc_types or "slew" in valid_arc_types:
    valid_arc_types.add("combinational")
    valid_arc_types.add("combinational_fall")
    valid_arc_types.add("combinational_rise")
    valid_arc_types.add("falling_edge")
    valid_arc_types.add("rising_edge")
    valid_arc_types.add("three_state_disable")
    valid_arc_types.add("three_state_enable")
    valid_arc_types.add("clear")
    valid_arc_types.add("preset")
    valid_arc_types.add('edge')
```

**Behavior**: User says "delay" -> MCQC treats all non-constraint arc types as
delay-measurable.

**Reason**: In Liberate's template.tcl, there is no `type=delay`. The absence
of `-type` means combinational delay. `edge` means clock-triggered sequential
delay. `clear`/`preset` are async recovery arcs that also produce output
transitions. All of these need delay/slew measurement templates.

**Classification**: Principled. This maps the Liberate taxonomy to the
measurement taxonomy.

### 3.7 HOLD_TAX / HT Path Variants

**Trigger**: `--holdtax` or `--ht` CLI flags

**Behavior**: Template/Char paths include `/HOLD_TAX/` or `/HT/` subdirectory.

**Reason**: HOLD_TAX (hold tax characterization) and HT (high-temperature)
are alternate characterization runs with different kits.

**Classification**: Empirical (directory convention).

### 3.8 VCP (Voltage Compliance Power) Deck Variants

**Trigger**: `template_deck_name in VCP_DECK` (11 hardcoded paths in
`vcp_helper.py:5-17`)

**Behavior**: For these specific templates, generate additional `VDD_nominal_sim.sp`
and `VSS_nominal_sim.sp` variants that change the clock pin bias.

**Reason**: Non-sequential hold/setup arcs involving retention pin (RETN) need
to be checked at both VDD and VSS clock levels to validate power-mode-crossing
behavior.

**Classification**: Empirical (hardcoded template list). Principle-shaped:
the underlying need (PMC testing) is real, but the implementation is
name-matching rather than topology-derived.

### 3.9 3D Constraint Table (5x5x5)

**Trigger**: `cell.constraint()` matches `*5x5x5*` (`qaTemplateMaker/funcs.py:514`)

**Behavior**: Output load is a 5-element list from `index_3`; each arc is
expanded into 3 `ArcInfo` objects (indices 1, 2, 3).

**Reason**: Some cells have 3-dimensional constraint tables where the third
axis is output load. Each load point needs a separate SPICE deck.

**Classification**: Principled (captures a real physical dimension).

### 3.10 Glitch Threshold Cascade

**Trigger**: Multiple sources (`timingArcInfo/funcs.py:118-147`)

Priority order (last wins):
1. `constraint_glitch_peak` from chartcl `set_var` (global)
2. `amd_glitch` from `set_config_opt` (AMD-specific, per hold/cell)
3. Per-cell condition from char.tcl `if { [string compare ...` blocks
4. Per-arc `metric_thresh` from `define_arc` block

**Behavior**: Sets the `GLITCH` threshold used in `.meas` statements for
glitch checking in the SPICE deck.

**Classification**: Empirical -- layered vendor overrides. The physical need
(glitch detection) is principled, but the priority cascade is ad-hoc.

### 3.11 SIS Template Glitch Thresholds

**Trigger**: `Template_sis/` directory exists alongside `Template/`
(`charTemplateParser/funcs.py:71-76`)

**Behavior**: Parse `glitch_high_threshold` and `glitch_low_threshold` per
pintype from `.sis` file. Values injected into every arc's SPICE info dict.

**Classification**: Empirical (vendor extension).

### 3.12 Default Unspecified Pin State

**Trigger**: `getUnspecifiedPinAssignments` in `spiceDeckMaker/funcs.py:225-265`

**Behavior**: Pins not assigned by when-condition, not pin/rel_pin, not output,
not don't-touch, and not user-fixed get `vdd_value` (logic high) by default.
Exception: if vector specifies `0` or `1`, that value is used.

**Reason**: Most standard-cell side inputs need to be in a known state for
simulation. High (inactive) is the safe default for most cells.

**Classification**: Mostly principled (physics: undriven pins need bias), but
the "default high" assumption is empirical (works for most cells, wrong for
active-high enables that should be low).

---

## 4. Methodology Candidates

### STRONG Candidates

These are confirmed by multiple MCQC sites and represent real physical/measurement
principles.

#### M1: Arc Type Determines Measurement Structure
**When** the arc type is a constraint type (hold, setup, removal, recovery,
nochange, min_pulse_width), **the measurement should** use a multi-phase
waveform with constraint-specific timing points and slew-based LUT indexing,
**because** constraint arcs measure timing margins (not delay values), which
requires a pre-conditioning phase, a clock edge, and a data edge in specific
temporal relationships.

*Evidence*: Different template directories per arc type (hold/, setup/,
non_seq_hold/, etc.). `getIndexEntriesForArc` uses `cell.constraint()` for
constraint types vs `cell.delay()` for delay types. `INDEX_2_VALUE` gets `'n'`
suffix for constraints (slew) vs `'p'` for delay (load).

#### M2: Combinational = No Type Flag
**When** a `define_arc` block has no `-type` flag, **it should be classified
as** `combinational` (delay arc), **because** Liberate only attaches `-type`
to special arc types (hidden, hold, setup, edge, etc.); the default is a
standard input-to-output propagation delay arc.

*Evidence*: `charTemplateParser/funcs.py:481`. DeckGen PROJECT_NOTES.md section
2.2 with cross-validation against AIOI21 ground truth.

#### M3: Pin Direction Derived from Vector Position
**When** determining pin transition direction, **the measurement should** use
the vector character at the pin's position in the pinlist, **because** the
vector encoding is the authoritative source of pin activity in the arc
definition -- it specifies exactly which pins transition and in which direction.

*Evidence*: `getPinDir` (`qaTemplateMaker/funcs.py:819-853`). Used consistently
across all arc types. Cross-validated by AIOI21 ground truth (10 delay arcs).

#### M4: Cell Topology Determines Template Structure (Sync Stages)
**When** a cell name contains `SYNC{N}` (N=2,3,4,5,6), **the measurement
should** use a template with N flip-flop stages in the SPICE netlist, probing
at the first internal stage (Q1), **because** multi-stage synchronizers have
internal timing paths that are physically different from the final output path.

*Evidence*: 6 distinct sync template families in rules (sync2, sync3, sync4,
sync5, sync6). Templates have different numbers of `.ic` (initial condition)
statements and probe points.

#### M5: Constraint Index Override by Pin
**When** a `define_index` block specifies index values for a specific
`(-pin, -related_pin, -when)` combination, **these values should override**
the cell's default template indices, **because** different pin-to-pin paths
within the same cell may have different operating ranges (e.g., scan input vs
data input may need different slew ranges).

*Evidence*: `getMatchingDefineIndexBlocks` and `getOverridingDefineIndexBlock`
(`qaTemplateMaker/funcs.py:597-655`). Matching uses specificity (exact pin >
wildcard > no override).

#### M6: Delay Type Expansion is a Taxonomy Mapping
**When** the user requests "delay" or "slew" arcs, **the system should include**
all non-constraint arc types (combinational, combinational_rise/fall, edge,
rising_edge, falling_edge, three_state_enable/disable, clear, preset),
**because** these are all Liberate-internal type names for arcs that produce
output transitions and require delay/slew measurement.

*Evidence*: `checkValidArc` (`qaTemplateMaker/funcs.py:750-764`). This mapping
is the same in both `1-general` and `0-mpw` variants.

#### M7: When Condition Encodes Side-Input Sensitization
**When** an arc has a `-when` condition, **the SPICE deck should bias** the
specified side-input pins to the states indicated (`!pin` = low, `pin` = high),
**because** the when condition specifies the exact input combination under which
the timing arc is valid -- different states produce different RC paths in the
CMOS network.

*Evidence*: `getWhenConditionLines` (`spiceDeckMaker/funcs.py:148-171`).
AIOI21 ground truth shows 3 distinct when conditions for pin B, each
representing a physically different pull-up path impedance.

### WEAK Candidates

These appear in one or few sites and may be coincidence or obsolete patterns.

#### M8: Retention Cells Need Multi-Phase VCP Testing
**When** a cell is a retention cell (name contains `RETN`), **the measurement
should** generate additional VDD/VSS deck variants for power-mode-crossing
verification, **because** retention cells must maintain state across power
domain transitions.

*Evidence*: `VCP_DECK` set in `vcp_helper.py` (11 paths, all involving RETN).
The underlying need is real, but the implementation is fully hardcoded.

#### M9: Latch Cells May Need Different Output Load Index
**When** a cell's char.tcl has a per-cell `constraint_output_load` override,
**the output load should be taken from the specified index** rather than the
default (index 2), **because** some cells (typically latches) have different
capacitance characteristics at different operating points.

*Evidence*: `parse_condition_load` regex in `chartcl_condition.py:24-26`.
Only triggered for cells explicitly listed in char.tcl conditionals.

#### M10: Async Clear/Set Arcs Need Glitch Measurement
**When** an arc involves async control pins (CD, SDN), **the measurement should
include glitch detection** (glitch_minq, glitch_maxq), **because** async
control can cause transient glitches on the output that must be bounded.

*Evidence*: Templates in `non_seq_hold/` contain `glitch__minq`/`glitch__maxq`
in their names. `get_glitch_minq_line`/`get_glitch_maxq_line` in
`spiceDeckMaker/funcs.py:403-454`.

#### M11: Don't-Touch Pins Are Template-Defined
**When** a SPICE template declares pins on its line 2 as DONT_TOUCH_PINS,
**these pins should not receive** voltage source assignments from the
when-condition or unspecified-pin logic, **because** they are already driven
by the template's internal circuitry (e.g., pre-existing stimulus).

*Evidence*: `getDontTouchPins` (`spiceDeckMaker/funcs.py:14-22`). Every
template deck must have this on line 2.

#### M12: Pushout Direction Can Be Negative
**When** `PUSHOUT_PER` is negative, **the measurement should** flag the
pushout direction as NEGATIVE in a comment line, **because** some arcs have
timing margins that decrease rather than increase under variation.

*Evidence*: `fillTemplateLine` (`spiceDeckMaker/funcs.py:291-306`). Only
triggers when `MEAS_DEGRADE_PER` is in the template line.

#### M13: Netlist Fallback Chain
**When** looking up a cell's LPE netlist, **the system should try** `_c_qa.spi`
first, then `_c.spi`, then `.spi`, **because** different netlist variants exist
(compacted QA, compacted, original) and the most reduced variant should be
preferred for simulation efficiency.

*Evidence*: `getNetlistPath` (`timingArcInfo/funcs.py:390-402`). Three-level
fallback.

---

## 5. Open Questions for Yuxuan

### Q1: templateFileMap Source

> [SUPERSEDED -- see foundation/A] This question is resolved. The file is at
> `mcqc_flow/2-flow/funcs.py` (18,624 lines). 26/30 sampled rules verified
> exact; 4/30 have incomplete OR-alternative extraction. See
> `docs/foundation/A_templatefilemap_check.md`.

~~The `templateFileMap/funcs.py` module (the 18K-line if-chain that maps arc
characteristics to template deck paths) is not available locally.~~ It is
imported at runtime via `sys.path.insert(0, TEMPLATE_LUT_PATH)`.

- ~~**Where is this module deployed?**~~ At `mcqc_flow/2-flow/funcs.py`.
- **Is the extracted `template_rules.json` (854 rules) a complete representation?**
  26/30 sampled exact; 4/30 have incomplete OR-alternatives (false negatives).
- **Are there version differences?** The JSON was extracted from `2-flow/funcs.py`
  which IS the production `templateFileMap`.

### Q2: Rule Reduction Feasibility
Of the 688 HSPICE rules:
- 255 are hold, mapping to 204 unique templates
- Many rules differ only in cell name pattern while using the same template

**Can you confirm**: do rules with the same `(arc_type, rel_pin, rel_pin_dir,
constr_pin_dir, probe)` but different `cell_pattern` always map to the same
template? If so, the cell pattern is only used for "is this cell eligible"
rather than "which template to use" -- and the rule count would collapse
dramatically.

### Q3: When Count Limit
The default `MAX_NUM_WHEN = 1` means only one when condition per
`(arc_type, pin, rel_pin, vector)` tuple is generated. The remaining are
silently dropped.

- **Is this intentional?** For MCQC's purpose (quality checking), one when
  condition per arc shape may be sufficient. But for full characterization
  verification, all when conditions matter.
- **For DeckGen v2**: should we default to generating all when conditions,
  or keep the limit as a user option?

### Q4: Glitch/Pushout Override Cascade
The override priority is: global < AMD-specific < per-cell char.tcl <
per-arc metric_thresh. This cascade is spread across 3 files and 30+ lines.

- **Is this priority order correct and intentional?**
- **Are there cases where it produces wrong values?**
- **For v2**: should we simplify to a flat lookup (per-arc if available,
  else per-cell, else global)?

### Q5: Non-Constraint Delay Template Selection
The `template_rules.json` has only 2 `delay_arc_types` rules. In practice,
delay/slew arcs seem to use a much simpler template selection (essentially
one template per direction combination, not per cell pattern).

- **Is the delay template selection really much simpler than constraint?**
- **Does `config/delay_template_rules.py` in DeckGen capture the full logic?**

### Q6: 3D Constraint Tables
The 5x5x5 case expands each arc into 3 sub-arcs with different output loads.

- **Which cells have 3D constraint tables?** Is this limited to specific
  cell families?
- **Is index_3 always output load?** Or can it represent other physical
  quantities?

### Q7: SIS Template
The SIS (Signal Integrity Simulation?) template parsing adds
`glitch_high_threshold` and `glitch_low_threshold` per pintype.

- **What is the SIS template's role in the flow?** Is it used for all cells
  or only specific ones?
- **Are these thresholds used in the SPICE deck directly, or only for
  post-processing?**

### Q8: Char.tcl Cell List vs Template.tcl Cell List
Stage 5 requires cells to be in BOTH `cell_pattern_list` (from globals) AND
`tcl_vars['cells']` (from char.tcl's `set cells` block). But if `set cells`
is not present in char.tcl, the code falls through without this filter
(`runMonteCarlo.py:293-295`).

- **When is `set cells` present vs absent?** Is this a version difference
  in char.tcl format?
- **Is the dual filter intentional?** It means a cell can be in the user's
  pattern list but still dropped if char.tcl doesn't list it.

### Q9: DONT_TOUCH_PINS Convention
Every SPICE template must have `DONT_TOUCH_PINS` as a comma-separated list
on line 2 (hardcoded line index).

- **What determines which pins are don't-touch?** Is this the pin/rel_pin
  of the specific arc, or is it template-specific?
- **For v2**: can we derive don't-touch from the arc definition instead of
  hardcoding it in the template?

### Q10: MPW vs General Flow
The `0-mpw/` and `1-general/` variants have nearly identical `scld__mcqc.py`
(formatting differences only). But the `qaTemplateMaker` and `templateFileMap`
may differ.

- **Are the MPW and general flows still separate?** Or have they been merged
  in production?
- **Does the template deck set differ between the two?**

---

## Appendix A: Module Dependency Graph

```
scld__mcqc.py (CLI entry point)
  |-- globalsFileReader/funcs.py (config loading)
  |-- hybrid_char_helper.py (char.tcl include file parsing + cell list)
  |-- runMonteCarlo.py (orchestrator)
      |-- charTemplateParser/funcs.py (template.tcl parser)
      |   |-- charTemplateParser/classes.py (TemplateInfo, Cell, Arc, Index)
      |-- chartcl_helper/parser.py (char.tcl parser)
      |-- qaTemplateMaker/funcs.py (arc extraction + template selection)
      |   |-- qaTemplateMaker/classes.py (ArcInfo)
      |   |-- qaTemplateMaker/chartcl_condition.py (per-cell load/glitch regex)
      |   |-- templateFileMap/funcs.py (18K-line if-chain, remote)
      |-- timingArcInfo/funcs.py (SPICE info assembly)
      |-- spiceDeckMaker/funcs.py (deck generation)
      |-- arcFilters/funcs.py (optional CSV-based arc filter)
      |-- vcp_helper.py (VCP deck variants)
      |-- runtime/funcs.py (CPU estimation)
```

## Appendix B: Data Flow Summary

```
globals.cfg          -->  user_options dict
kit_path/            -->  template.tcl path, char.tcl path, netlist dir
template.tcl         -->  TemplateInfo (cells, arcs, indices, templates)
char.tcl             -->  ChartclParser (glitch, pushout, load overrides, cell list)
                          |
                          v
              [Arc Extraction: filter cells x filter arc types]
                          |
                          v
              arc_list: [ArcInfo, ArcInfo, ...]
              (each has: cell, type, pins, dirs, when, indices,
               output_load, template_deck, metric, vector)
                          |
                          v
              [SPICE Info: enrich with physical params per table point]
                          |
                          v
              spice_info[table_point][arc_num] = {
                  CELL_NAME, ARC_TYPE, TEMPLATE_DECK,
                  REL_PIN, CONSTR_PIN, their dirs,
                  WHEN, OUTPUT_LOAD, INDEX_1/2_VALUE,
                  VDD_VALUE, TEMPERATURE, NETLIST_PATH,
                  WAVEFORM_FILE, INCLUDE_FILE,
                  PUSHOUT_PER, GLITCH, VECTOR, ...
              }
                          |
                          v
              [Deck Generation: $VAR substitution + pin biasing]
                          |
                          v
              DECKS/{arc}_{cell}_{pins}_{when}_{point}/
                  nominal_sim.sp
                  mc_sim.sp
```

## Appendix C: Key Line References

| What | File | Lines | Notes |
|------|------|-------|-------|
| CLI arg parsing | scld__mcqc.py | 148-221 | `getopt`-based |
| Default options | globalsFileReader/funcs.py | 54-80 | `CELL_PATTERN_LIST=["*D1B*"]` |
| Globals file parse | globalsFileReader/funcs.py | 9-51 | `set_var` prefix |
| Template.tcl locate | scld__mcqc.py | 224-252 | Glob + count check |
| Char.tcl locate | scld__mcqc.py | 264-291 | Glob + count check |
| VDD extraction | scld__mcqc.py | 300-303 | Grep `set VOLT` |
| Temperature extraction | scld__mcqc.py | 306-309 | Grep `set TEMP` |
| Netlist path extraction | scld__mcqc.py | 312-324 | Bottom-up scan, fragile |
| Include file parse | hybrid_char_helper.py | 20-53 | `extsim_model_include` |
| **Type=combinational default** | charTemplateParser/funcs.py | 477-482 | **Critical rule** |
| When=NO_CONDITION default | charTemplateParser/funcs.py | 478-479 | Default for no -when |
| Cell validation (dual) | qaTemplateMaker/funcs.py | 244 | Both pattern + tcl_vars |
| **Delay type expansion** | qaTemplateMaker/funcs.py | 750-764 | **Critical mapping** |
| Index override matching | qaTemplateMaker/funcs.py | 597-655 | Specificity-based |
| Output load default | qaTemplateMaker/funcs.py | 489-539 | `index_2[2]` |
| Pin dir from vector | qaTemplateMaker/funcs.py | 819-853 | Position-based |
| When count limit | qaTemplateMaker/funcs.py | 405-452 | `max_num_when` gate |
| Template deck map | templateFileMap/funcs.py | N/A | ~~Remote~~, 18K lines [SUPERSEDED -- see foundation/A: local at `mcqc_flow/2-flow/funcs.py`] |
| Index suffix logic | timingArcInfo/funcs.py | 361-370 | `'p'` for delay, `'n'` for constraint |
| Netlist fallback | timingArcInfo/funcs.py | 390-402 | `_c_qa` > `_c` > plain |
| $VAR substitution | spiceDeckMaker/funcs.py | 291-324 | Template instantiation |
| When-condition pins | spiceDeckMaker/funcs.py | 148-171 | `!pin` = low, `pin` = high |
| Unspecified pin default | spiceDeckMaker/funcs.py | 225-265 | Default = high |
| Don't-touch pins | spiceDeckMaker/funcs.py | 14-22 | Line 2 of template |
| VCP deck set | vcp_helper.py | 5-17 | 11 hardcoded paths |
| Glitch line substitution | spiceDeckMaker/funcs.py | 403-454 | Pattern-matched .meas |
