# DeckGen Task List (for local Claude Code continuation)

Branch to pull from: `claude/analyze-repo-structure-i8J6b` (or merge to main
first). Read `design.md` and `../CLAUDE.md` alongside this file.

## Status Snapshot

**Done:**
- Backend modules (`core/resolver.py`, `core/deck_builder.py`,
  `core/writer.py`, CLI `deckgen.py`)
- 63 real MCQC SPICE templates moved to `templates/generic/mpw/`
- Template registry (`config/template_registry.yaml`) with cell pattern ->
  template mapping (updated paths to generic/mpw/)
- Corner name parser (`core/parsers/corner.py`):
  `ssgnp_0p450v_m40c` -> VDD/temp
- Cell_arc_pt identifier parser (`core/parsers/arc.py`)
- Template.tcl index parser (`core/parsers/template_tcl.py`)
- All non-ASCII characters stripped from code + templates
- v0.2 GUI works for single-arc generation
- Folder reorganization: core/, config/, docs/, tests/
- Package files: requirements.txt, CLAUDE.md
- Batch backend (`core/batch.py`): plan_jobs + execute_jobs + run_batch
- CLI batch mode: --arcs_file, --corners, --corners_file, --template_tcl_dir
- 96 tests passing (arc parser, corner parser, template_tcl parser, end-to-end)
- Template structure: `templates/{node}/{arc_type}/` (node-aware)
- `core/template_map.py`: MCQC if-chain port (partial; MPW + basic hold/delay rules)
- `tools/import_templates.py`: imports SCLD templates into `templates/{node}/`

**Remaining:** GUI rewrite; full template_map.py port (800+ rules); delay/hold
templates from SCLD; Point 2 (collateral dataset); Point 5 (GUI polish).

---

## Task 1: Rewrite `gui.py` to v0.3

Replace `gui.py` with a redesigned version matching `design.md`.

### 1.1 HTML layout (two-column)

- Top bar: title + "Run Batch", "Preview", "Clear" buttons
- Left column (inputs):
  - Textarea for cell_arc_pt identifiers (one per line)
  - Textarea for corner names (one per line or comma-separated)
  - File path inputs with Browse buttons: netlist_dir, model, waveform,
    template.tcl (optional), output_dir
  - Collapsible "Overrides" panel: VDD, Temp, Slew, Load, MaxSlew,
    num_samples, nominal_only
  - Collapsible "Single Mode" accordion (for users without an identifier):
    cell, arc_type, rel_pin, rel_dir, constr_pin, constr_dir, probe_pin, when
- Right column (output):
  - Job preview table (scrollable)
  - Log / error panel
  - SPICE preview panel (when a single job selected)

### 1.2 Design tokens (CSS)

Use the palette from `design.md`:
- Primary: `#2563eb`
- Success: `#10b981`
- Error: `#ef4444`
- Bg: `#f8fafc`
- Panel: `#ffffff`
- Border: `#e2e8f0`
- Text: `#0f172a`

Fonts: system stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
Helvetica, Arial, sans-serif`). Monospace: `'SF Mono', Menlo, Consolas,
'Courier New', monospace`.

**Critical:** zero non-ASCII characters in the HTML. No emojis, no em-dashes,
no smart quotes. After writing, verify with:
```bash
python3 -c "open('gui.py','rb').read().decode('ascii')"
```

### 1.3 Client-side logic

- On paste into Targets textarea, highlight each line as valid/invalid
  (call `/api/parse_arcs` with debounce ~300ms)
- On paste into Corners textarea, same with `/api/parse_corners`
- Browse buttons: trigger `<input type="file">` for files, or let user paste
  absolute path. For directory pick, try `webkitdirectory` attribute as a
  best-effort (HTML5 limitation: absolute path is not exposed; the text input
  is the authoritative source)
- Run Batch: POST `/api/generate_batch`, stream results into the job table
- Preview: POST `/api/preview_batch`, populate job table without writing files
- Click a row in the job table to load its SPICE preview into the right panel

### 1.4 New API endpoints

Add these to `DeckgenHandler`:

```python
POST /api/parse_arcs
  in:  {"text": "arc1\narc2\n..."}
  out: {"arcs": [{parsed_dict, ...}], "errors": ["line 3: ..."]}

POST /api/parse_corners
  in:  {"text": "corner1, corner2"}
  out: {"corners": [{parsed_dict, ...}], "errors": [...]}

POST /api/preview_batch
  in:  {
         "arc_ids": ["..."],
         "corner_names": ["..."],
         "netlist_dir": "...",
         "model": "...",
         "waveform": "...",
         "template_tcl_dir": "...",   # optional
         "overrides": {"vdd": "...", "slew": "...", ...}
       }
  out: {
         "jobs": [
           {
             "id": 1,
             "cell": "...", "arc_type": "...",
             "rel_pin": "...", "rel_dir": "...",
             "corner": "...", "vdd": "...", "temp": "...",
             "template": "templates/...",
             "constr_slew": "...", "rel_slew": "...",
             "output_load": "...", "max_slew": "...",
             "netlist": "...", "netlist_pins": "...",
             "warnings": [...]
           },
           ...
         ],
         "errors": [...]
       }

POST /api/generate_batch
  in:  {same as preview_batch + "selected_ids": [1, 3, 5]}
  out: [
         {"id": 1, "success": true, "nominal": "...", "mc": "..."},
         {"id": 3, "success": false, "error": "..."},
       ]
  Stream these as newline-delimited JSON for live updates.
```

### 1.5 Keep existing endpoints working

`/api/generate` (single) and `/api/match` -- keep them for CLI parity and
the Single Mode accordion.

---

## Task 2: Auto-fill integration

### 2.1 Arc spec auto-fill

When `core.parsers.arc.parse_arc_identifier()` succeeds for a given ID:
- Populate cell, arc_type, rel_pin, rel_dir, probe_pin in the resolver call
- `constr_pin` and `constr_dir` are NOT in the identifier. For delay/slew,
  they can be `rel_pin` (arc is on itself). For hold/setup, infer from the
  template match or require override.

### 2.2 Corner auto-fill

For each corner in the list, `core.parsers.corner.parse_corner_name()` gives
VDD and temperature. Override order:
1. User override (if set)
2. Parsed from corner name
3. Error if neither

### 2.3 Slew/Load auto-fill (from template.tcl)

If `template_tcl_dir` is provided:
1. Look for `{template_tcl_dir}/{corner_name}.template.tcl`
2. If missing, try `{template_tcl_dir}/template.tcl`
3. Parse with `core.parsers.template_tcl.parse_template_tcl()`
4. Call `core.parsers.template_tcl.lookup_slew_load(parsed, i1, i2, arc_type)`
   to get slew/load
5. User overrides win if set

If template.tcl is missing, use user overrides or error.

### 2.4 Netlist auto-discovery

Given `netlist_dir`, for each cell call `NetlistResolver.resolve(cell_name)`.
Pin list comes from the netlist, always. No user-entered pin list.

---

## Task 3: Batch generation logic

Add to `deckgen.py` or a new `batch.py`:

```python
def run_batch(arc_ids, corner_names, files, overrides, output_dir,
              selected_ids=None, nominal_only=False, num_samples=5000):
    """
    Iterate over arcs x corners. For each combination:
      1. Parse arc identifier
      2. Parse corner name
      3. Resolve template (via registry)
      4. Resolve netlist (via netlist_dir)
      5. Resolve slew/load (via template.tcl if provided, else overrides)
      6. Build deck via build_deck()
      7. Write to output_dir/{dirname}_{corner}/

    Returns list of job result dicts.
    """
```

Use `concurrent.futures.ThreadPoolExecutor(max_workers=8)` for parallelism.

---

## Task 4: CLI support for batch

Update `deckgen.py` to accept:
- `--arcs_file arcs.txt` -- one identifier per line
- `--corners_file corners.txt` -- one corner per line
- `--corners ssgnp_0p450v_m40c,ttgnp_0p800v_25c` -- comma list
- `--template_tcl_dir ./tcl/` -- enables slew/load auto-fill

Keep existing single-arc flags as-is (they stay useful).

---

## Task 5: Tests

Create `tests/` directory with:

### `tests/test_arc_parser.py`
```python
import pytest
from core.parsers.arc import parse_arc_identifier

def test_combinational_no_condition():
    r = parse_arc_identifier(
        'combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4'
    )
    assert r['arc_type'] == 'combinational'
    assert r['cell_name'] == 'ND2MDLIMZD0P7BWP130HPNPN3P48CPD'
    assert r['probe_pin'] == 'ZN' and r['probe_dir'] == 'rise'
    assert r['rel_pin'] == 'A1' and r['rel_dir'] == 'fall'
    assert r['when'] == 'NO_CONDITION'
    assert r['i1'] == 4 and r['i2'] == 4

def test_with_when_condition():
    r = parse_arc_identifier(
        'combinational_MUX4MDLIMZD0P7BWP130HPNPN3P48CPD_Z_rise_S1_rise_notI0_notI1_notI2_I3_S0_4_4'
    )
    assert r['when'] == '!I0&!I1&!I2&I3&S0'

def test_hold():
    r = parse_arc_identifier('hold_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2')
    assert r['arc_type'] == 'hold'
    assert r['i1'] == 3 and r['i2'] == 2

def test_invalid():
    assert parse_arc_identifier('garbage') is None
    assert parse_arc_identifier('') is None
```

### `tests/test_corner_parser.py`
```python
from core.parsers.corner import parse_corner_name, parse_corner_list

def test_basic_corners():
    cases = [
        ('ssgnp_0p450v_m40c', 'ssgnp', '0.450', '-40'),
        ('ttgnp_0p800v_25c',  'ttgnp', '0.800', '25'),
        ('ffgnp_0p900v_125c', 'ffgnp', '0.900', '125'),
    ]
    for name, proc, vdd, temp in cases:
        r = parse_corner_name(name)
        assert r['process'] == proc
        assert r['vdd'] == vdd
        assert r['temperature'] == temp

def test_batch():
    corners = parse_corner_list('ssgnp_0p450v_m40c, ffgnp_0p900v_125c')
    assert len(corners) == 2
```

### `tests/test_end_to_end.py`
Reuse the test fixtures from `/tmp/deckgen_test/` (create them in a setup
fixture). Generate 2 arcs x 2 corners = 4 decks, verify files exist.

---

## Task 6: Documentation

Update `README.md`:
- Batch mode usage examples
- Cell_arc_pt identifier format explanation
- Corner name format
- Template.tcl expected format

Keep `design.md` and `task.md` in the repo for future reference.

---

## Task 7: Final polish

- Add `requirements.txt` with just `pyyaml>=5.0`
- Add `pytest` to dev dependencies (optional)
- Run final non-ASCII scan: `grep -rPn '[\x80-\xff]' .`
- Verify the GUI renders correctly in Chrome, Firefox, Safari
- Test with 10 arcs x 2 corners (20 decks) to confirm batch works

---

---

## TODO-3: LLM Agent Interface (future)

Add a natural-language interface so users can describe an arc in plain English
and have an LLM translate it into a cell_arc_pt identifier + corner + files.

Key points:
- LLM parses the user's description into structured arc parameters
- DeckGen backend generates the deck as-is
- Could be a new mode in the GUI or a separate CLI entry point
- Requires an LLM API key; keep it optional (graceful degradation if absent)
- Do NOT start until the backend + GUI are stable and MCQC-parity validated

---

## TODO-4: FMC Run + Result Parsing + Visualization (future)

Add an interface to:
1. Launch the FMC simulation run from DeckGen (submit job or run locally)
2. Parse the FMC output (timing measurements, convergence status)
3. Visualize results: per-arc delay/slew scatter, corner comparison, waveform overlays

Key points:
- FMC output format must be documented before implementation starts
- Visualization can be embedded in the GUI or exported as standalone HTML
- Do NOT start until Point 2 (collateral dataset auto-resolver) is complete
  and the run infrastructure is confirmed ready

---

## Suggested Execution Order

1. Task 5.1 + 5.2 (parser tests) -- validate the parsers before relying on them
2. Task 3 (batch generation logic) -- backend first
3. Task 4 (CLI batch support) -- thin wrapper over Task 3
4. Task 1 (GUI rewrite) -- depends on batch backend
5. Task 5.3 (end-to-end test)
6. Task 6, 7 (docs, polish)

---

## Gotchas

- **`constr_pin` for delay/slew:** the cell_arc_pt identifier does not have
  a separate constrained pin. The "arc" is from rel_pin to probe_pin. Pass
  `rel_pin` as the `constr_pin` to `resolve_all()` for delay/slew arcs.
- **`constr_dir` for hold:** the identifier encodes `rel_dir` but not
  `constr_dir`. The hold templates require `constr_dir`. Convention in
  MCQC: `constr_dir` is the opposite of `rel_dir` (hold is about holding
  a stable value while clock edge happens). Decide: always opposite, or
  require a user override.
- **Pin list source:** auto from netlist via `NetlistResolver`. If netlist
  cannot be read, surface the error to the GUI -- do not ask user to type
  pins manually.
- **Output dir collisions:** current `get_deck_dirname()` does not include
  the corner name. In batch mode with multiple corners, append
  `_{corner_raw}` to avoid overwriting.
- **Signed commits:** the repo has `commit.gpgsign=true` globally. Normal
  commits work; if you hit signing errors, check `/tmp/code-sign` is
  available, or locally set `git config --local commit.gpgsign false`.

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

---

## Point 2b -- Done

Constraint parity delivered:
- `define_index` override parser + `find_define_index_override` lookup helper
- `build_arc_infos` (plural) with 3D constraint expansion (5x5x5 -> 3 decks)
- SIS template sidecar parsing + pintype glitch injection (O/I)
- Per-arc `metric_thresh` precedence (highest glitch override)
- `core/mpw_skip.skip_this_arc` for SYNC2/3/4 Q removal arcs
- `core/resolver.resolve_all_from_collateral` returns list for 3D, dict otherwise (back-compat)
- Batch deck directories get `-2/-3/-4` suffix for 3D arcs

## Point 5 -- Done

GUI polish delivered:
- `/api/nodes`, `/api/lib_types`, `/api/corners`, `/api/cells`, `/api/rescan`
- `/api/preview_v2`, `/api/generate_v2` endpoints (collateral-backed)
- Collateral Mode panel in existing GUI: node/lib_type dropdowns, corner multi-select,
  Rescan button, Populate Arcs+Corners, Preview v2, Generate v2
- Collapsible panel; does not displace legacy v0.3 batch mode UI

Final test count: 200 passing (96 legacy + 104 new across 2a + 2b + GUI).
