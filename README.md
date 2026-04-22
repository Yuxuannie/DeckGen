# DeckGen

Direct SPICE deck generator for semiconductor library characterization.
Generate a SPICE simulation deck for a specific **(cell, arc_type, PT)**
combination without setting up a full characterization flow.

Supports: **delay**, **slew**, **hold** arc types.

## Why?

Traditional library characterization flows (MCQC, etc.) are top-down: set up
the full configuration stack, parse every cell, filter arcs through several
silent stages, and hope your target arc survives. If it gets dropped, there's
no feedback about which stage rejected it.

DeckGen flips this: you specify the exact arc you want, and it resolves,
generates, and reports — with explicit errors if anything is missing.

## Install

No dependencies beyond Python 3.8+ and PyYAML. Just clone and run.

```bash
git clone https://github.com/Yuxuannie/DeckGen.git
cd DeckGen
pip install pyyaml      # only external dependency
```

## Quick Start

### GUI (browser-based)

```bash
python3 gui.py
```

Opens a local web UI at `http://127.0.0.1:8585` with form fields for cell
specification, electrical parameters, and file paths. Includes:

- **Check Template Match** button — preview which template would be chosen
  before generating
- **Preview Only** — generate the deck in-memory without writing files
- **Load Last Input** — remembers your previous form values via localStorage
- **Copy** button on generated decks
- Help tooltips on tricky fields

### CLI

```bash
python3 deckgen.py \
    --cell DFFQ1 --arc_type hold \
    --rel_pin CP --rel_dir rise \
    --constr_pin D --constr_dir fall \
    --probe_pin Q \
    --slew 2.5n --rel_slew 1.2n --load 0.5f \
    --vdd 0.45 --temp -40 \
    --when '!SE&SI' \
    --netlist /path/to/DFFQ1.spi \
    --model /path/to/ss_model.spi \
    --waveform /path/to/std_wv.spi \
    --output ./output/
```

## Architecture

```
┌────────────────────────────────────────────────────┐
│  CLI (deckgen.py)   or   GUI (gui.py)              │
└──────────────┬─────────────────────────────────────┘
               ▼
┌────────────────────────────────────────────────────┐
│  resolver.py                                        │
│  ├─ TemplateResolver  (cell pattern → .sp file)    │
│  ├─ NetlistResolver   (cell → LPE netlist + pins)  │
│  └─ CornerResolver    (VDD, temp, model paths)     │
│  *** Reports EXACTLY what cannot be resolved ***   │
└──────────────┬─────────────────────────────────────┘
               ▼
┌────────────────────────────────────────────────────┐
│  deck_builder.py                                    │
│  ├─ Variable substitution ($VAR → value)            │
│  ├─ When-condition → pin voltage source lines      │
│  └─ Output load injection                           │
└──────────────┬─────────────────────────────────────┘
               ▼
┌────────────────────────────────────────────────────┐
│  writer.py  → nominal_sim.sp + mc_sim.sp           │
└────────────────────────────────────────────────────┘
```

## File Layout

```
DeckGen/
├── deckgen.py              # CLI entry point
├── gui.py                  # Browser-based GUI
├── resolver.py             # Template + netlist + corner resolution
├── deck_builder.py         # Template substitution, when-condition
├── writer.py               # File output
├── config.yaml             # Global defaults
├── template_registry.yaml  # Cell pattern → template mapping
├── corners/                # Example PVT corner configs
│   └── example_corner.yaml
└── templates/
    └── min_pulse_width/    # SPICE deck templates (63 cell patterns)
```

## Template Registry

The registry maps cell patterns to SPICE templates. Patterns use `fnmatch`
syntax, and entries are scored by specificity (more specific wins).

```yaml
templates:
  - pattern: "*SYNC2*"
    arc_type: any
    rel_pin: CP
    rel_dir: fall
    constr_dir: rise
    template: min_pulse_width/template__CP__sync2__D__fall__rise__1.sp

  - pattern: "*"            # fallback
    arc_type: any
    rel_pin: CP
    rel_dir: rise
    constr_dir: fall
    template: min_pulse_width/template__CP__rise__fall__1.sp
```

Fields:
- `pattern` — fnmatch glob (e.g. `*DFF*`, `*SYNC[23]*`, `*`)
- `arc_type` — `delay`, `slew`, `hold`, or `any`
- `rel_pin` — related pin name or `any`
- `rel_dir` — `rise`, `fall`, or `any`
- `constr_dir` — `rise`, `fall`, or `any`
- `template` — path under `templates/`

You can always bypass the registry with `--template /path/to/your.sp`.

## Corner Config

Optional YAML file to bundle PVT parameters:

```yaml
# corners/ss_0p45v_m40c.yaml
vdd: "0.450"
temperature: "-40"
model_file: /path/to/ss_model.spi
waveform_file: /path/to/std_wv.spi
pushout_per: "0.4"
```

Use with `--corner_config corners/ss_0p45v_m40c.yaml`.

## Error Reporting

If a deck can't be generated, DeckGen tells you exactly why:

```
Cannot generate deck for MYCELL / hold / CLK->D:
  ✗ No template match for (MYCELL, hold, CLK/rise, constr_dir=rise)
  ✗ Closest matches:
  ✗   - pattern=*SYNC2* arc_type=any rel_pin=CP/fall → .../template__CP__sync2__D__fall__rise__1.sp
  ✗   - pattern=* arc_type=any rel_pin=any/fall constr_dir=rise → .../template__CP__fall__rise__1.sp
```

## Arc Type Differences

| Parameter           | Delay               | Slew                | Hold                           |
|---------------------|---------------------|---------------------|--------------------------------|
| Waveform model      | `stdvs_rise/fall`   | `stdvs_rise/fall`   | `stdvs_mpw_*` (multi-phase)    |
| Timing points       | t01–t03             | t01–t03             | t01–t07                        |
| Measurements        | `cp2q_del1`         | `slew_rise/fall`    | `cp2q_del1` + `cp2cp`          |
| Nodeset init        | Q/QN only           | Q/QN only           | Latch internals + Q/QN         |
| Hold-only param     | —                   | —                   | `constr_pin_offset` (optim.)   |

## License

Templates under `templates/min_pulse_width/` are derived from TSMC ADC Timing
Team source material. Use accordingly.
