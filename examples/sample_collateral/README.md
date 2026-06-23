# Sample collateral (one inverter)

A minimal, **synthetic** collateral bundle that the deck-generation flow can run
end-to-end against. Use it as the template for your own packages: drop your real
files into the same directory layout and point the GUI/CLI at the root.

The cell `INVD1` is a plain inverter (`ZN = !I`). The netlist is a 2-transistor
stub, not real IP -- it only illustrates the format.

## Layout

```
sample_collateral/
+-- N2P_v1.0/                      <node>
    +-- demo_lib/                  <lib_type>
        +-- Template/
        |   +-- demo_lib_<corner>.template.tcl   ALAPI: define_cell + define_arc
        +-- Netlist/
        |   +-- LPE_<...>/<cell>_c.spi           .subckt per cell (pin order)
        +-- Char/
            +-- demo_lib_<corner>.inc            model includes (.lib)
            +-- ... .delay.inc / .hold.inc / .usage.l / char_*.cons.tcl
```

- **Corner** here is `ssgnp_0p450v_m40c_cworst_CCworst_T`.
- The `template.tcl` is in **ALAPI** form: each cell sits in an
  `ALAPI_active_cell` block with one `define_cell` (pinlist/output/template) and
  one `define_arc` per edge (`-vector {FR|RF} -related_pin I -pin ZN`). Add more
  cells by repeating the block.
- The netlist file is found by `<cell_name>_c.spi` (also `.spi`, `.sp` accepted)
  and the cell's pins come from its `.subckt` line.

## Run it

GUI:

```bash
python3 gui_deckgen.py --collateral_root examples/sample_collateral
# http://127.0.0.1:8585  ->  node N2P_v1.0 / lib demo_lib / corner ... / cell INVD1
```

CLI -- cross-validate the two deck-generation paths (should be ALL MATCH):

```bash
python3 tools/deck_diff.py --cell INVD1 \
    --corner ssgnp_0p450v_m40c_cworst_CCworst_T \
    --node N2P_v1.0 --lib_type demo_lib \
    --collateral_root examples/sample_collateral
```

CLI -- generate decks + an interactive report via the programmatic generator:

```bash
python3 tools/gen_cell_report.py --collateral_root examples/sample_collateral \
    --node N2P_v1.0 --lib_type demo_lib \
    --corner ssgnp_0p450v_m40c_cworst_CCworst_T \
    --cell INVD1 --method generator --output ./demo_out
```

## Using your real collateral

Copy this directory, then replace the three pieces with your real files
(keeping the names consistent with the lib and corner):

1. `Template/<lib>_<corner>.template.tcl` -- your real ALAPI template.tcl.
2. `Netlist/LPE_*/<cell>_c.spi` -- your real LPE netlists (one `.subckt` per cell).
3. `Char/<lib>_<corner>.inc` (+ siblings) -- your real model includes.

Then point the GUI at the new root. Any cell present in both the template.tcl
and the netlist directory becomes selectable; unseen cells generate directly --
no per-cell `template_*.sp` required.
