# DeckGen

Direct SPICE deck generator for semiconductor library characterization.
Generate a ready-to-simulate SPICE deck for a specific **(cell, arc_type, PT)**
combination without setting up a full characterization flow.

Supports: **delay**, **slew**, **hold** arc types. Batch mode: N arcs x M corners.

## Why?

Traditional library characterization flows (MCQC, etc.) are top-down: configure
the full stack, parse every cell, filter arcs through silent stages, and hope
your target survives. Dropped arcs get no feedback.

DeckGen flips this: you specify exactly what you want, and it resolves,
generates, and reports -- with explicit errors if anything is missing.

## Install

```bash
pip install pyyaml      # only external dependency (Python 3.8+ required)
```

## Quick Start

### GUI (browser-based)

```bash
python3 gui.py              # opens http://127.0.0.1:8585
python3 gui.py --port 9090  # custom port
```

The GUI supports:
- **Single-arc mode** -- fill in cell/arc fields, generate one deck
- **Batch mode** -- paste arc identifiers and corner names, preview all jobs,
  then generate with live progress
- Auto-fill slew/load from a `template.tcl` file when corners are parsed
- Template match preview before generating
- Copy button on generated decks

### CLI -- single arc

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

### CLI -- batch mode (N arcs x M corners)

```bash
python3 deckgen.py \
    --arcs_file arcs.txt \
    --corners ssgnp_0p450v_m40c,ttgnp_0p800v_25c \
    --netlist_dir /path/to/netlists/ \
    --model /path/to/model.spi \
    --waveform /path/to/wv.spi \
    --template_tcl_dir /path/to/tcl/ \
    --output ./output/
```

`arcs.txt` contains one cell_arc_pt identifier per line (see format below).
`--corners_file corners.txt` is accepted as an alternative to `--corners`.

## Cell_Arc_PT Identifier Format

Arc identifiers use a fixed underscore-delimited format:

```
{arc_type}_{cell_name}_{probe_pin}_{probe_dir}_{rel_pin}_{rel_dir}_{when}_{i1}_{i2}
```

Example:
```
hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1
combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4
```

- `arc_type` -- `delay`, `slew`, `hold`, `setup`, `removal`, `recovery`, etc.
- `probe_pin` / `probe_dir` -- output pin and its transition direction
- `rel_pin` / `rel_dir` -- related (clocking) pin and direction
- `when` -- `NO_CONDITION` (no condition) or encoded condition string
  (`notI0_notI1_I2` becomes `!I0&!I1&I2`)
- `i1`, `i2` -- 1-based indices into `index_1` / `index_2` of the
  template.tcl lookup table (used for slew/load auto-fill)

## Corner Name Format

```
{process}_{voltage}v_{temperature}c
```

Examples:
```
ssgnp_0p450v_m40c    ->  SS, 0.450 V, -40 C
ttgnp_0p800v_25c     ->  TT, 0.800 V, +25 C
ffgnp_0p900v_125c    ->  FF, 0.900 V, +125 C
```

- Voltage: `p` is the decimal separator (`0p450` = 0.450 V)
- Temperature: `m` prefix means negative (`m40` = -40 C)

## File Layout

```
deckgen/
+-- deckgen.py              CLI entry point
+-- gui.py                  Browser-based GUI
+-- requirements.txt        Python deps (pyyaml)
+-- core/
|   +-- resolver.py         Template + netlist + corner resolution
|   +-- deck_builder.py     Template substitution, when-condition
|   +-- writer.py           File output (nominal + MC decks)
|   +-- batch.py            N-arc x M-corner batch runner
|   +-- parsers/
|       +-- arc.py          cell_arc_pt identifier parser
|       +-- corner.py       Corner name parser
|       +-- template_tcl.py Liberty template.tcl parser
+-- config/
|   +-- config.yaml               Global defaults
|   +-- template_registry.yaml    Cell pattern -> template mapping
|   +-- corners/
|       +-- example_corner.yaml
+-- templates/
|   +-- min_pulse_width/    SPICE deck templates (63 cell patterns)
+-- docs/
|   +-- design.md           Architecture and design decisions
|   +-- task.md             Task execution plan
+-- tests/
    +-- conftest.py
    +-- test_arc_parser.py
    +-- test_corner_parser.py
    +-- test_template_tcl_parser.py
    +-- test_end_to_end.py
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Template Registry

`config/template_registry.yaml` maps cell patterns to SPICE templates.
Patterns use `fnmatch` syntax; more-specific entries win.

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
- `pattern` -- fnmatch glob (e.g. `*DFF*`, `*SYNC[23]*`, `*`)
- `arc_type` -- `delay`, `slew`, `hold`, or `any`
- `rel_pin` -- related pin name or `any`
- `rel_dir` -- `rise`, `fall`, or `any`
- `constr_dir` -- `rise`, `fall`, or `any`
- `template` -- path under `templates/`

Bypass the registry entirely with `--template /path/to/your.sp`.

## Error Reporting

If a deck cannot be generated, DeckGen reports exactly why:

```
Cannot generate deck for MYCELL / hold / CLK->D:
  x No template match for (MYCELL, hold, CLK/rise, constr_dir=rise)
  x Closest matches:
  x   - pattern=*SYNC2* arc_type=any rel_pin=CP/fall -> .../template__CP__sync2__D__fall__rise__1.sp
  x   - pattern=* arc_type=any rel_pin=any/fall constr_dir=rise -> .../template__CP__fall__rise__1.sp
```

## Arc Type Differences

| Parameter       | Delay             | Slew              | Hold                        |
|-----------------|-------------------|-------------------|-----------------------------|
| Waveform model  | stdvs_rise/fall   | stdvs_rise/fall   | stdvs_mpw_* (multi-phase)   |
| Timing points   | t01-t03           | t01-t03           | t01-t07                     |
| Measurements    | cp2q_del1         | slew_rise/fall    | cp2q_del1 + cp2cp           |
| Nodeset init    | Q/QN only         | Q/QN only         | Latch internals + Q/QN      |
| Hold-only param | --                | --                | constr_pin_offset (optim.)  |

## License

Templates under `templates/min_pulse_width/` are derived from TSMC ADC Timing
Team source material. Use accordingly.
