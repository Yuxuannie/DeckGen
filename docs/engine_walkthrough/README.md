# Engine Walkthrough (presentation material)

Plain-language, slide-ready explanation of how the DeckGen v2 engine derives a
sync cell's structure from a raw layout-extracted netlist -- one stage per page,
each with a figure you can drop straight into a deck.

Running example: `SDFSYNC4RPQSXGMZD1BWP130HPNPN3P48CPD` (scan-DFF, 4-stage
synchronizer; pins CD/CP/D/SE/SI/Q), corner `ssgnp_0p450v_m40c_cworst_CCworst_T`.
The numbers in these pages are the engine's ACTUAL output on that cell.

| Stage | Page | Figure |
|-------|------|--------|
| S0 -- recover the logical schematic (de-parasitic R-merge) | [s0_parse.md](s0_parse.md) | `figs/s0_rmerge.svg` |
| S1 -- find the storage latches from structure | [s1_ccc.md](s1_ccc.md) | `figs/s1_storage.svg` |
| S2 -- sensitization, derived per arc | [s2_sensitize.md](s2_sensitize.md) | `figs/s2_sensitize.svg` |

Figures are SVG (PowerPoint / Keynote / Google Slides insert SVG natively and
keep it crisp at any zoom). Regenerate after edits:

```bash
python3 docs/engine_walkthrough/make_figs.py
```

The one-line thesis for the whole talk: **the engine reads a cell it has never
seen, blind to node naming, and recovers its real circuit and its memory
structure -- so it can reason about timing for a team that does not know the
cell internals.** The rename-invariance gate
(`tests/engine/test_rename_invariance.py`) is the proof that "blind to naming"
is real and not an accident.
