# DeckGen

@README.md

Direct SPICE deck generator for semiconductor library characterization.
Bottom-up: user specifies exact arc, tool generates deck or reports exactly why it can't.

## Directory Layout

- `deckgen.py` -- CLI entry point
- `gui.py` -- browser GUI (default port 8585)
- `core/` -- importable library: `resolver`, `deck_builder`, `writer`, `parsers/`
- `config/` -- `config.yaml`, `template_registry.yaml`, `corners/`
- `templates/` -- SPICE deck templates (min_pulse_width/ + node-specific subdirs)
- `config/delay_template_rules.py` -- delay arc template selection rules
- `core/template_rules.py` -- MCQC-parity hold/setup/mpw/removal/recovery rules (688+ rules)
- `core/arc_info_builder.py` -- MCQC-parity arc_info dict composition
- `docs/design.md` -- architecture decisions
- `docs/task.md` -- remaining work items

## Commands

```bash
# CLI
python3 deckgen.py --cell DFFQ1 --arc_type hold \
    --rel_pin CP --rel_dir rise --constr_pin D --constr_dir fall \
    --probe_pin Q --slew 2.5n --rel_slew 1.2n --load 0.5f \
    --vdd 0.45 --temp -40 --when '!SE&SI' \
    --netlist /path/to/DFFQ1.spi \
    --model /path/to/model.spi --waveform /path/to/wv.spi \
    --output ./output/

# GUI
python3 gui.py              # http://127.0.0.1:8585
python3 gui.py --port 9090

# Tests
python -m pytest tests/

# Install deps
pip install -r requirements.txt
```

## Cell_Arc_PT Identifier Format

```
{arc_type}_{cell}_{probe_pin}_{probe_dir}_{rel_pin}_{rel_dir}_{when}_{i1}_{i2}
```

Example: `combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4`

- `i1`/`i2`: 1-based indices into template.tcl `index_1`/`index_2`
- `when`: `&`-separated; `notX` in raw string -> `!X` after parsing
- `NO_CONDITION` = no when-condition pins

## Corner Name Format

```
{process}_{voltage}v_{temperature}c
```

Examples: `ssgnp_0p450v_m40c`, `ttgnp_0p800v_25c`, `ffgnp_0p900v_125c`

- Voltage: `p` as decimal separator (`0p450` = 0.450 V)
- Temperature: `m` prefix for negative (`m40` = -40 C)

## Conventions

**Imports:** Entry scripts import `from core.resolver import ...`. Run from `deckgen/` dir
(Python adds cwd to `sys.path`), or set `PYTHONPATH=/path/to/deckgen`.

**Config paths:** Always relative to script location -- never hardcode absolute paths:
```python
script_dir = os.path.dirname(os.path.abspath(__file__))
registry_path = os.path.join(script_dir, 'config', 'template_registry.yaml')
```

**Non-ASCII:** IMPORTANT -- zero non-ASCII bytes anywhere. Verify before committing:
```bash
grep -rPn '[\x80-\xff]' . --include='*.py' --include='*.yaml' --include='*.sp' --include='*.md'
```
Output must be empty.

**Error reporting:** Resolution failures must list what was tried and suggest fixes.
Never fail silently. Never drop arcs without telling the user.

## Gotchas

- **PyYAML install:** `pip install pyyaml` (NOT `pip install yaml` -- that package is unrelated)
- **Git signing:** Repo has `commit.gpgsign=true` with signing server at `/tmp/code-sign`.
  On signing errors: `git config --local commit.gpgsign false` temporarily.
  Do not push unsigned commits without checking with user.

## Status

See `docs/task.md` for the full task list.

Done: backend modules, parsers, CLI, SPICE templates, GUI v2.0 with:
- 3-tab layout: Explore / Direct / Validate
- ALAPI template.tcl parser (auto-detect + full Tcl tokenizer)
- MCQC-parity template selection (688+ hold/setup/mpw rules + delay rules)
- Inline source viewer (Monaco Editor, tcl/SPICE syntax highlighting)
- LUT grid picker (inline per arc-type, Shift+click rectangle selection)
- Collateral-backed deck generation (netlist/model/waveform auto-resolved)
- i1/i2 table-point index lookup from template.tcl

Remaining: additional test coverage, template.tcl slew/load edge cases.
