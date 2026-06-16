# Engine Walkthrough (presentation material)

Plain-language, slide-ready explanation of how the DeckGen v2 engine derives a
sync cell's structure from a raw layout-extracted netlist -- one stage per page,
each with a figure you can drop straight into a deck.

Running example: `SDFSYNC4RPQSXGMZD1BWP130HPNPN3P48CPD` (scan-DFF, 4-stage
synchronizer; pins CD/CP/D/SE/SI/Q), corner `ssgnp_0p450v_m40c_cworst_CCworst_T`.
The numbers in these pages are the engine's ACTUAL output on that cell.

| Stage | Page | Process figure (HOW) | Result/companion |
|-------|------|----------------------|------------------|
| S0 -- recover the logical schematic | [s0_parse.md](s0_parse.md) | `figs/s0_rmerge.svg` | -- |
| S1 -- find the storage latches | [s1_ccc.md](s1_ccc.md) | `figs/s1_process.svg` (CCC + SCC algorithm) | `figs/s1_storage.svg` (the 8-latch chain) |
| S2 -- sensitization | [s2_sensitize.md](s2_sensitize.md) | `figs/s2_booldiff.svg` (Boolean-difference derivation) | `figs/s2_sensitize.svg` (read vs define_arc) |

The `*_process` figures show HOW the algorithm computes each result on a worked
micro-example; the companions show the result / interpretation.

## Build the slides

Figures are SVG. Regenerate them, then assemble the editable PowerPoint deck:

```bash
python3 docs/engine_walkthrough/make_figs.py     # refresh the SVGs
python3 docs/engine_walkthrough/build_pptx.py    # -> engine_walkthrough.pptx (16:9)
```

`build_pptx.py` rasterizes each SVG (svglib + reportlab, pure Python -- no native
renderer needed) and places it on a 16:9 slide with an editable title box. Deps:
`pip install python-pptx svglib reportlab pillow`. The `.pptx` and the `_png/`
rasters are generated artifacts (git-ignored); the SVGs are the source of truth.
You can also insert any SVG straight into an existing deck
(Insert > Pictures > select the .svg).

The one-line thesis for the whole talk: **the engine reads a cell it has never
seen, blind to node naming, and recovers its real circuit and its memory
structure -- so it can reason about timing for a team that does not know the
cell internals.** The rename-invariance gate
(`tests/engine/test_rename_invariance.py`) is the proof that "blind to naming"
is real and not an accident.
