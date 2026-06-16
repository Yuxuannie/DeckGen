# Engine Walkthrough (presentation material)

Plain-language, slide-ready explanation of how the DeckGen v2 engine derives a
sync cell's structure from a raw layout-extracted netlist -- one stage per page,
each with a figure you can drop straight into a deck.

Running example: `SDFSYNC4RPQSXGMZD1BWP130HPNPN3P48CPD` (scan-DFF, 4-stage
synchronizer; pins CD/CP/D/SE/SI/Q), corner `ssgnp_0p450v_m40c_cworst_CCworst_T`.
The numbers in these pages are the engine's ACTUAL output on that cell.

| Stage | Page | Process figure (HOW) | Result/companion |
|-------|------|----------------------|------------------|
| S0 -- recover the logical schematic | [s0_parse.md](s0_parse.md) | `figs/s0_rmerge.svg` | `figs/union_find.svg` (how nodes merge) |
| S1 -- find the storage latches | [s1_ccc.md](s1_ccc.md) | `figs/ccc.svg` (what a CCC is) + `figs/s1_process.svg` (SCC algorithm) | `figs/s1_storage.svg` (the 8-latch chain) |
| S2 -- sensitization | [s2_sensitize.md](s2_sensitize.md) | `figs/s2_booldiff.svg` (Boolean-difference derivation) | `figs/s2_sensitize.svg` (read vs define_arc) |

The `*_process` figures show HOW the algorithm computes each result on a worked
micro-example; the companions show the result / interpretation.

## Pitch slides (after S2): charge resolve + LPE roadmap

Three purple-themed 16:9 slides for the SCLD/MingJing pitch, generated from the
real engine (`engine/charge.py`) -- no hand-entered numbers:

| Slide | Figure | Built by |
|-------|--------|----------|
| Charge resolve -- the method | `figs/pitch_a1_charge_method.svg` | `pitch_slides.py` |
| Charge resolve -- engine output (canonical cases) | `figs/pitch_a2_charge_cases.svg` | `engine/charge_svg.py` (cards) driven by `resolve_checked` |
| From the LPE netlist: capabilities -> applications -> ask | `figs/pitch_b_lpe_roadmap.svg` | `pitch_slides.py` |

```bash
python3 docs/engine_walkthrough/pitch_slides.py   # refresh the 3 pitch SVGs
python3 docs/engine_walkthrough/build_pptx.py     # also writes pitch.pptx (3 slides)
```

`engine/charge_svg.py:render_svg(result, Cg, Cc, entry_V, fixed_V, title)` draws
one charge-resolve case in `engine/draw.py` house style; every voltage is read
from a `ChargeResolve`, so `tests/engine/test_charge_svg.py` can assert the figure
equals `resolve_checked(...).voltages`. Slide B's status tags (BUILT/NEXT/
ROADMAP/HYPOTHESIS/DIRECTION) match the repo: charge resolve is BUILT; the
aggressor/victim impact layer is NEXT; the cell-from-LPE fingerprint is ROADMAP
(today's is template-level); worst-case init / AIQC / reverse-eng are
forward-looking.

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
