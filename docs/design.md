# DeckGen Design Document

## Purpose

A direct SPICE deck generator for library characterization. User specifies
exactly what they want (one or many `cell_arc_pt` targets, one or more
PVT corners) and the tool generates decks -- with explicit errors if
anything is missing.

Contrast with MCQC: MCQC is top-down (parse everything, filter many stages,
hope your arc survives). DeckGen is bottom-up (say what you want, get it or
know why not).

## Current State (as of this handoff)

### Working backend modules

| File | Status | Purpose |
|------|--------|---------|
| `core/resolver.py` | Done | Template + netlist + corner parameter resolution |
| `core/deck_builder.py` | Done | Template `$VAR` substitution, when-condition lines |
| `core/writer.py` | Done | Nominal + MC deck file output |
| `deckgen.py` | Done | CLI entry point (top-level) |
| `core/parsers/corner.py` | Done | Parses `ssgnp_0p450v_m40c` -> process/VDD/temp |
| `core/parsers/arc.py` | Done | Parses cell_arc_pt identifier strings |
| `core/parsers/template_tcl.py` | Done | Extracts index_1/2/3 from template.tcl |

### Templates & Config

- `templates/min_pulse_width/*.sp` -- 63 original TSMC templates, cleaned
  of non-ASCII characters
- `config/template_registry.yaml` -- cell pattern -> template mapping
- `config/config.yaml` -- global defaults
- `config/corners/*.yaml` -- per-corner configs

### GUI

- `gui.py` -- browser-based GUI (v0.2). Works for single-arc generation.
  **Needs redesign** to handle batch mode + auto-fill from identifier.

## Cell_Arc_PT Identifier Format

```
{arc_type}_{cell_name}_{probe_pin}_{probe_dir}_{rel_pin}_{rel_dir}_{when}_{i1}_{i2}
```

Examples:
```
combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4
combinational_MUX4MDLIMZD0P7BWP130HPNPN3P48CPD_Z_rise_S1_rise_notI0_notI1_notI2_I3_S0_4_4
hold_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2
```

### Parser output (`core.parsers.arc.parse_arc_identifier`)

```python
{
    'arc_type':  'combinational',
    'cell_name': 'ND2MDLIMZD0P7BWP130HPNPN3P48CPD',
    'probe_pin': 'ZN',
    'probe_dir': 'rise',
    'rel_pin':   'A1',
    'rel_dir':   'fall',
    'when':      'NO_CONDITION',      # or '!I0&!I1&!I2&I3&S0'
    'i1':        4,                    # table index 1
    'i2':        4,                    # table index 2
    'raw':       '<original string>',
}
```

**Notes on parsing logic:**
- Arc type is matched against a known list (combinational, hold, setup,
  removal, recovery, min_pulse_width, etc.)
- Tail is `{i1}_{i2}` as integers
- Middle is scanned for two direction keywords (rise/fall). First is
  probe direction, second is rel_pin direction
- `notX` prefixes in the when condition become `!X`
- `NO_CONDITION` is preserved as a sentinel

## Corner Name Format

```
{process}_{voltage}v_{temperature}c
```

Examples:
```
ssgnp_0p450v_m40c  -> process=ssgnp, vdd=0.450, temp=-40
ttgnp_0p800v_25c   -> process=ttgnp, vdd=0.800, temp=25
ffgnp_0p900v_125c  -> process=ffgnp, vdd=0.900, temp=125
```

### Parser output (`core.parsers.corner.parse_corner_name`)

```python
{
    'process':     'ssgnp',
    'vdd':         '0.450',
    'temperature': '-40',
    'raw':         'ssgnp_0p450v_m40c',
}
```

## Template.tcl Parsing

`core.parsers.template_tcl.parse_template_tcl(path)` extracts `index_1/2/3`
lists from Liberty-style template.tcl files.

`core.parsers.template_tcl.lookup_slew_load(parsed, i1, i2, arc_type)` returns:
```python
{
    'constr_pin_slew': '2.5n',
    'rel_pin_slew':    '1.2n',
    'output_load':     '0.5f',
    'max_slew':        '10n',  # max of index_1 list
}
```

Arc-type-aware logic:
- For constraints (hold/setup): `index_1` is constrained-pin slew,
  `index_2` is related-pin slew, `index_3` is output load
- For delay/slew: `index_1` is input slew (maps to both constr+rel pin
  slew), `index_2` is output load

## Input Model (New Design)

The tool will accept **any combination** of:

1. **Arc spec** -- one of:
   - A cell_arc_pt identifier (auto-parsed)
   - Manual fields (cell name, arc type, pins, dirs, when)
2. **Corners** -- list of corner names (comma/newline separated)
3. **Files** -- paths to:
   - Netlist (file or directory of netlists)
   - Model file
   - Waveform file
   - Template.tcl (optional, enables slew/load auto-fill)
4. **Overrides** -- any parameter can be manually set to override
   auto-detected values

## Batch Mode

User can provide:
- N arc identifiers (one per line in a textarea)
- M corners (comma separated)

Tool generates `N x M` decks. Each deck has its own output subdirectory
(based on `get_deck_dirname` with corner appended).

### Batch preview (before generation)

Before running, show a table:
```
#   Cell           Arc              Corner            Template        Slew    Load
1   ND2MDL...      ZN_rise_A1_fall  ssgnp_0p450v_m40c  delay/CP_...    1.2n   0.5f
2   ND2MDL...      ZN_rise_A1_fall  ttgnp_0p800v_25c   delay/CP_...    1.2n   0.5f
3   MUX4MD...      Z_rise_S1_rise   ssgnp_0p450v_m40c  delay/CP_...    2.5n   0.8f
```

User can toggle individual rows off before generation.

## GUI Redesign Spec

### Layout: two-column, top-bar

```
+--------------------------------------------------------------+
| deckgen v0.3    [Run Batch]  [Preview]  [Clear]              |
+----------------------------------+---------------------------+
|  INPUT PANEL (left)              |  RESULTS PANEL (right)    |
|                                  |                           |
|  [Targets]                       |  [Job Table]              |
|  <textarea, one ID per line>     |  status, path, ...        |
|                                  |                           |
|  [Corners]                       |  [Log / Errors]           |
|  <textarea>                      |  <scrollable>             |
|                                  |                           |
|  [Files]                         |  [Preview]                |
|  netlist_dir: ___  [Browse]      |  <SPICE text>             |
|  model:       ___  [Browse]      |                           |
|  waveform:    ___  [Browse]      |                           |
|  template.tcl:___  [Browse]      |                           |
|                                  |                           |
|  [Output]                        |                           |
|  dir: ____________________       |                           |
|                                  |                           |
|  [Overrides] (collapsible)       |                           |
|  VDD ___  Temp ___  Slew ___     |                           |
|                                  |                           |
+----------------------------------+---------------------------+
```

### Design language

- Typography: system font stack, 14px base, 12px body, 11px labels
- Palette:
  - Primary: `#2563eb` (blue-600)
  - Success: `#10b981` (emerald-500)
  - Error:   `#ef4444` (red-500)
  - Bg:      `#f8fafc` (slate-50)
  - Panel:   `#ffffff`
  - Border:  `#e2e8f0` (slate-200)
  - Text:    `#0f172a` (slate-900)
- Rounded corners: 6px on inputs, 8px on cards
- Monospace areas (paths, IDs, SPICE preview): `'SF Mono', Menlo, Consolas, monospace`
- Subtle shadows: `0 1px 2px rgba(0,0,0,0.04)`
- No emojis, no non-ASCII

### File picker

HTML5 `<input type="file">` is **read-only on the filesystem** -- it only
exposes the filename, not the absolute path. For a local desktop tool,
two options:

**Option A (chosen):** Text input with a "Browse" button that opens the
native file dialog client-side. Since we're on localhost, users can
also paste absolute paths directly.

**Option B:** Add a `/api/browse` endpoint that opens a system file
dialog server-side (Python's `tkinter.filedialog`). Works but adds a
tkinter dependency.

Recommend Option A for simplicity. The text input accepts:
- Absolute path typed/pasted directly
- Drag-and-drop of a file (read `dataTransfer.files[0].path` if
  available on Electron-style contexts; fall back to name-only otherwise)

### New API endpoints

```
POST /api/parse_arcs       body: {text: "..."}  -> list of parsed arc dicts + errors
POST /api/parse_corners    body: {text: "..."}  -> list of parsed corner dicts
POST /api/preview_batch    body: {arcs, corners, files, overrides}
                           -> list of planned jobs with resolved template+slew+load
POST /api/generate_batch   body: {same as preview_batch, plus selected row ids}
                           -> streamed results: {row_id, success, paths/error}
POST /api/generate_one     (existing, keep for CLI parity)
POST /api/match            (existing, template match check)
```

### Removed from GUI

- **Pin list field** -- now auto-extracted from netlist. If extraction
  fails, show the error clearly (not a user input).
- **Individual cell/arc/pin/dir fields** -- hidden by default; shown in
  an "Override / Single Mode" accordion for users who don't have a
  cell_arc_pt identifier.

## Open Design Decisions

1. **Netlist discovery in batch mode**
   - If `netlist_dir` is given, auto-discover each cell's netlist
   - If a single `netlist` file is given, use it for all arcs (error if
     cell names differ)

2. **Template.tcl per corner vs global**
   - Typical flow: one template.tcl per corner. We could let users
     provide `{corner_name: template.tcl_path}` as a mapping, or a
     directory with files named `{corner}.template.tcl`
   - **Decision:** start with directory convention:
     `{template_tcl_dir}/{corner}.template.tcl`

3. **Max slew handling**
   - Currently `max(index_1)` -- but MCQC sometimes uses a fixed `0.1u`.
   - **Decision:** use `max(index_1)` by default, let user override.

4. **Row selection in batch preview**
   - Checkbox per row to include/exclude
   - Bulk select by cell pattern or corner

5. **Generation concurrency**
   - Generating 100+ decks could be slow if done serially
   - Python's `concurrent.futures.ThreadPoolExecutor` would parallelize
   - File I/O-bound, not CPU-bound, so threading is fine

## File Paths of Interest

Referenced during the design:
- Real cell_arc_pt examples:
  `LibCharCerti/1-FMC_golden/gen_DECKs/1-script/2-data_process/get_PR/*.rpt`
- Original MCQC templates:
  `Project/0-MCQC/2-flow/min_pulse_width/*.sp`
- MCQC config/flow code (reference only):
  `Project/0-MCQC/0-mpw/`

## Testing Strategy

Tests are not yet written. Recommended test cases:

1. **arc_parser** -- 10+ representative identifiers covering all arc types
2. **corner_parser** -- common corners + edge cases (negative temp, 3-digit temp)
3. **template_tcl_parser** -- synthetic template.tcl with multiple templates
4. **End-to-end batch** -- 3 arcs x 2 corners = 6 decks, verify all generated
5. **Error reporting** -- missing netlist, no template match, bad identifier

## Code Style Reminders

- Zero non-ASCII characters anywhere (`.sp`, `.py`, `.yaml`, `.md`)
  -- use `grep -rPn '[\x80-\xff]' .` to check
- PyYAML is the only external dependency; install with `pip install pyyaml`
  (package name is `pyyaml`, import is `yaml`)
- Keep `--template /path/to.sp` override available for debugging
