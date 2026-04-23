# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
this repository.

## Project Overview

**DeckGen** is a direct SPICE deck generator for semiconductor library
characterization. Given a specific `(cell, arc_type, PT)` target and a PVT
corner, it generates a ready-to-simulate SPICE deck. It supports **batch
mode** (N arcs x M corners) and both CLI and browser-based GUI.

Contrast with MCQC (the large parent tool in `../Project/0-MCQC/`): MCQC is
top-down and filter-heavy (you set up a full characterization flow, and the
tool parses every cell and drops arcs silently at many stages). DeckGen is
bottom-up: the user says exactly what they want, and the tool either gives
them the deck or tells them exactly why it can't.

## Directory Layout

```
deckgen/
├── README.md             User-facing docs
├── CLAUDE.md             This file
├── requirements.txt      Python deps (pyyaml)
├── deckgen.py            CLI entry point
├── gui.py                Browser-based GUI entry point
├── core/                 Core library (importable as `core.*`)
│   ├── __init__.py
│   ├── resolver.py       Template + netlist + corner resolution
│   ├── deck_builder.py   Template $VAR substitution, when-conditions
│   ├── writer.py         Nominal + MC deck file output
│   └── parsers/
│       ├── __init__.py
│       ├── arc.py            cell_arc_pt identifier parser
│       ├── corner.py         corner name parser (ssgnp_0p450v_m40c)
│       └── template_tcl.py   Liberty template.tcl parser
├── config/
│   ├── config.yaml               Global defaults
│   ├── template_registry.yaml    Cell pattern -> template mapping
│   └── corners/
│       └── example_corner.yaml
├── templates/
│   └── min_pulse_width/          63 original TSMC SPICE templates
├── docs/
│   ├── design.md                 Architecture + design decisions
│   └── task.md                   Remaining work items
└── tests/                         (currently empty, see docs/task.md)
```

## Commands

### Run the CLI

```bash
python3 deckgen.py --cell DFFQ1 --arc_type hold \
    --rel_pin CP --rel_dir rise --constr_pin D --constr_dir fall \
    --probe_pin Q --slew 2.5n --rel_slew 1.2n --load 0.5f \
    --vdd 0.45 --temp -40 --when '!SE&SI' \
    --netlist /path/to/DFFQ1.spi \
    --model /path/to/model.spi --waveform /path/to/wv.spi \
    --output ./output/
```

### Run the GUI

```bash
python3 gui.py              # opens http://127.0.0.1:8585
python3 gui.py --port 9090  # custom port
```

### Install dependencies

```bash
pip install -r requirements.txt    # just pyyaml (note: package name is pyyaml, not yaml)
```

### Run tests (after they are written per docs/task.md)

```bash
python -m pytest tests/
```

## Architecture

### Data flow

```
User input (CLI args or GUI form)
    |
    v
core.parsers.arc       <- cell_arc_pt identifier -> {cell, arc_type, rel_pin, ...}
core.parsers.corner    <- corner name            -> {vdd, temperature, ...}
core.parsers.template_tcl  <- template.tcl (optional) -> slew/load per (i1, i2)
    |
    v
core.resolver.resolve_all
    |
    +-- TemplateResolver  (cell pattern -> .sp file via config/template_registry.yaml)
    +-- NetlistResolver   (cell name -> .spi file + pin list)
    +-- CornerResolver    (validates VDD/temp/model_file/waveform_file)
    |
    v
core.deck_builder.build_deck  (substitutes $VAR, injects when-condition pins)
core.deck_builder.build_mc_deck  (adds Monte Carlo sweep line)
    |
    v
core.writer.write_nominal_and_mc  -> {output}/{deck_dirname}/{nominal,mc}_sim.sp
```

### Template Registry

`config/template_registry.yaml` maps cell patterns to SPICE templates:

```yaml
templates:
  - pattern: "*SYNC2*"       # fnmatch glob
    arc_type: any             # any / delay / slew / hold
    rel_pin: CP               # any or specific pin name
    rel_dir: fall             # any / rise / fall
    constr_dir: rise
    template: min_pulse_width/template__CP__sync2__D__fall__rise__1.sp
```

Matching is scored: more specific entries win. The `--template` override
bypasses the registry entirely.

### Cell_Arc_PT Identifier Format

```
{arc_type}_{cell_name}_{probe_pin}_{probe_dir}_{rel_pin}_{rel_dir}_{when}_{i1}_{i2}
```

Example:
`combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4`

- `i1`, `i2` are 1-based table point indices into `index_1` and `index_2`
  of the template.tcl (used to look up slew and load values)
- `when` uses `&` as separator; `notX` in the raw string becomes `!X` after
  parsing (e.g. `notI0_notI1_I2` -> `!I0&!I1&I2`)
- `NO_CONDITION` is a sentinel meaning no when-condition pins

### Corner Name Format

```
{process}_{voltage}v_{temperature}c
```

Examples: `ssgnp_0p450v_m40c`, `ttgnp_0p800v_25c`, `ffgnp_0p900v_125c`

- Voltage uses `p` as decimal separator (`0p450` = 0.450 V)
- Temperature can be negative using `m` prefix (`m40` = -40 C)

## Important Conventions

### Python imports

Entry scripts (`deckgen.py`, `gui.py`) at the top level import from the
`core` package:

```python
from core.resolver import resolve_all, ResolutionError
from core.parsers.arc import parse_arc_identifier
```

Running the scripts from the `deckgen/` directory works because Python adds
the current directory to `sys.path`. If you need to run from elsewhere,
set `PYTHONPATH=/path/to/deckgen`.

### Config paths

Entry scripts build config paths relative to the script location:
```python
script_dir = os.path.dirname(os.path.abspath(__file__))
registry_path = os.path.join(script_dir, 'config', 'template_registry.yaml')
templates_dir = os.path.join(script_dir, 'templates')
```

Do not hardcode absolute paths.

### Non-ASCII policy

**Zero non-ASCII bytes anywhere.** No emojis, no em-dashes, no smart quotes,
no non-breaking spaces. The original MCQC templates had `\xc2\xa0`
characters that broke parsers; these have been scrubbed.

Before committing, verify:
```bash
grep -rPn '[\x80-\xff]' . --include='*.py' --include='*.yaml' \
  --include='*.sp' --include='*.md'
```

Output should be empty.

### Error reporting

Resolution failures must list what was tried and suggest fixes:

```
Cannot generate deck for WEIRDCELL / hold / CLK->D:
  x No template match for (WEIRDCELL, hold, CLK/rise, constr_dir=rise)
  x Closest matches:
    - pattern=*SYNC2* ...
    - pattern=* rel_pin=any/rise constr_dir=fall -> ...
```

Never fail silently. Never drop arcs without telling the user.

### Git signing

The parent repo has `commit.gpgsign=true` globally with a custom signing
server at `/tmp/code-sign`. If you hit "missing source" signing errors
while committing from outside the primary repo path, either:
- Do the work from within the primary repo (it signs correctly there), or
- Set `git config --local commit.gpgsign false` temporarily

Do not push unsigned commits without checking with the user first.

## Dependencies

- **Python 3.8+** (tested on 3.11)
- **PyYAML** (`pip install pyyaml` -- note: import is `yaml`, but the pip
  package name is `pyyaml`, not `yaml`. `pip install yaml` will fail.)
- No other runtime deps. Standard library only for HTTP server (http.server),
  CLI (argparse), etc.

## Status (check `docs/task.md` for latest)

**Done:** backend modules, parsers, CLI, 63 SPICE templates, v0.2 GUI
(single-arc mode)

**Remaining:** GUI v0.3 rewrite for batch mode + auto-fill from identifier,
template.tcl slew/load auto-fill integration, tests, README updates.

See `docs/design.md` for architecture and design decisions.
See `docs/task.md` for a task-by-task execution plan.
