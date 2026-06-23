# Production Handoff: Universal FMC Deck Generation + Report + Engine Viz (Design)

**Status:** DRAFT -- awaiting review. Spec first, then implement (the repo's
superpowers workflow). One logical step per turn after approval.
**Branch:** child of `feat/phase-2c-charge-resolve` (`claude/lucid-noether-cat8lr`).
**Purpose:** hand the team a deck-generation flow they can run end-to-end and
validate against MCQC: any LPE netlist package -> FMC decks for any cell/arc
(even unseen), a detailed interactive summary report, and (separately) the
engine's analysis parameters, visualized.
**Validation baseline (theirs):** run the original MCQC flow in parallel and
diff the decks; cells are NAME-OBFUSCATED (random names) so nothing can key off
the cell-name pattern.

**Constraints (FIXED):**
- MCQC parity: generated FMC decks must match MCQC's structure for the common
  path (verified against real N2P reference decks: OAI2220 / MUX4 / BUFFND).
- Name-invariance: deck output depends only on structure (template.tcl +
  netlist), never the cell-name pattern. (Already proven --
  `tests/test_rename_invariance_deck.py`.)
- TWO independent GUIs (owner decision): deck-gen (production) and engine
  (analysis) are separate apps; clear boundary; may share a launcher + pickers.
- Report delivered BOTH ways (owner decision): a standalone self-contained HTML
  file AND an embedded view in the deck-gen GUI.
- Repo rules: code/config/templates/SPICE ASCII; never weaken a test assertion
  (Yuxuan-approval gate); never silently drop an arc; gpg-signed commits.
- GUI logic must be testable: pure functions (the `core/engine_present.py`
  pattern) with a thin HTTP layer; tests in the `tests/test_gui_api.py` style.

---

## 1. Scope -- three deliverables

D1. **Universal FMC deck generation** -- any/unseen combinational cell+arc, CLI +
    GUI, MCQC-parity, name-invariant.
D2. **Detailed interactive summary report** -- toggle/expand, importance-ranked;
    standalone HTML + GUI-embedded.
D3. **Engine analysis parameters, visualized** -- surfaced in the engine GUI.

Out of scope (state plainly): byte-exact parity for the ~13 per-cell HACK cells
(the obfuscation method routes everything through the common template anyway);
running HSPICE (no simulator here -- the team runs the decks).

## 2. Architecture -- two independent GUIs

Today `gui.py` (2369 lines) mixes deck-gen tabs (Explore/Direct/Validate) with
engine tabs (Topology/Audit) injected via `<!--ENGINE_TABS-->` +
`gui_engine_views.py` + `core/engine_present.py`. Split into two apps:

- **`gui.py` (deck-gen, production)** -- Explore / Direct / Validate + the new
  Report view. No engine tabs. Default port 8585. This is what the team tests.
- **`gui_engine.py` (engine, analysis)** -- Topology / Audit + the new analysis
  visualizations. Separate entry, separate port (e.g. 8586).
- **Shared, not duplicated:** the collateral pickers (node/lib/corner/cell/arc
  APIs) and CSS tokens move to a small shared module
  (`core/gui_common.py` or reuse existing `_api_*` functions) imported by both.
- **Bridge (loose, not merged):** the engine GUI can deep-link "analyze this
  cell" given a cell/corner; the deck GUI does not embed analysis.

Rationale: the two concerns have different inputs, outputs, validation, and
maturity; separation lets the deck tool be hardened/handed-off cleanly and keeps
the research engine from implying it is part of the validated production flow.

## 3. D1 -- universal FMC deck generation

Current state (built + verified):
- Combinational arcs select the generic delay template
  `templates/N2P_v1.0/delay/template_common_inpin_{rise,fall}_delay_{rise,fall}.sp`
  and produce an MCQC-parity FMC deck (`.tran 1p 5000n sweep monte=1`, simple
  `.options`, side pins on `vss_value`/`vdd_value`, `C<pin>` load,
  `meas_delay`/`half_tt_out`/`meas_tt_out`). Tests:
  `tests/test_combinational_deck.py`, `tests/test_rename_invariance_deck.py`.
- Name-invariance proven.

Remaining for "any cell, even unseen":
1. **HACK-template fallback robustness.** `get_delay_template` can return a
   `delay/hack/...sp` or `delay/./template__BUFTD...sp` path that does not exist
   in-repo; today the resolver then falls through to the registry and can
   mis-select an MPW template. Fix: when the returned delay template file does
   not exist, fall back to `_try_common_delay(...)` (the common template) rather
   than the registry. This makes ANY combinational cell generate via the common
   path (and matches the obfuscation method, which bypasses hacks). Tested with a
   cell whose name would match a hack.
2. **Batch over a whole cell / package.** `core/batch.py` already plans N arcs x
   M corners. Add: given a cell (or all cells in a manifest) at a corner,
   enumerate its combinational arcs from `template.tcl` and generate every deck;
   collect per-arc outcomes for the report. CLI: `--arcs_file` / cell list;
   GUI: batch mode already exists.
3. **CLI + GUI parity check.** Confirm both entry points drive the same resolver
   + deck_builder and produce identical decks (one test).
4. **`CONSTR_PIN` semantics for combinational** (latent): resolver sets
   `CONSTR_PIN` = rel pin for combinational; the template already uses
   `$PROBE_PIN_1` for the output, so output is correct, but tidy the field so the
   header/`arc_check` read right. Low risk; verify no regression.

## 4. D2 -- detailed interactive summary report

A batch run (cell/package x corner) produces a structured result; render it two
ways from ONE builder so they never diverge.

- **`core/report.py:build_report(batch_results, context) -> dict`** -- pure
  function. Per-arc rows: cell, arc_type, rel/constr/probe + dirs, when, PT
  (corner), template selected, generated (OK / FAIL / SKIP), reason-if-not,
  index point, output deck path, and (on expand) the substitution values + the
  deck text. Plus aggregates: totals, by-arc-type, by-cell, unmatched-template
  list, warnings, environment/provenance (node, lib, corner, collateral root).
- **`core/report.py:render_html(report) -> str`** -- pure function returning a
  self-contained HTML string (inline CSS + tiny vanilla JS for toggle/expand; no
  external deps; ASCII). Importance-ranked, top -> bottom:
  1. headline verdict + coverage summary (always visible);
  2. FAILURES / unmatched-template / errors (expanded by default);
  3. warnings;
  4. per-cell / per-arc table (collapsed; expand a row -> substitutions + deck);
  5. environment / provenance.
  Every group is collapsible; "expand all / collapse all" control.
- **Delivery:** CLI writes `report.html` next to the output decks; the deck-gen
  GUI serves the SAME `render_html` output in a Report view (and offers
  download). One renderer, two surfaces.
- **Testable:** `build_report` and `render_html` are pure -> unit tests assert
  the dict shape, the importance ordering, that failures surface, and that the
  HTML contains the expected toggles/rows (`tests/test_report.py`).

## 5. D3 -- engine analysis parameters, visualized

Surface what the engine already computes, reusing existing SVG renderers, in the
engine GUI:
- **Topology / CCC** -- `engine/draw.py:render_svg(graph, ccc, sens, arc)`
  (already wired by `engine_present.topology_view`); colors the sensitized path.
- **Charge resolve** -- `engine/charge_svg.py:render_svg` / `circuit_case` (the
  capacitor schematics; numbers from `resolve_checked`).
- **Sensitization (P1)** -- bias / masked-pin cards (exist in `engine_present`).
- **Storage staging** -- the master/stage/slave mapping (CCC) as a table + the
  SVG.
Add an **analysis params panel** (`core/engine_present.py:analysis_params(...)`)
that returns a JSON-serializable summary (CCC count, storage roles, P1 bias,
charge voltages with X-flags, verify P1/P2/P3 status) for the engine GUI to
render as cards + the SVGs. "As visual as possible" = SVG-first, tables second.
Honest tags preserved (model-prediction / UNVERIFIED / STUB) per prior specs.

## 6. GUI testing + UX

- Both GUIs keep request handling thin; all logic in pure functions
  (`_api_*`, `engine_present.*`, `report.*`). Tests call those directly
  (`tests/test_gui_api.py` pattern) -- no live HTTP needed.
- UX/efficiency: shared cell/corner pickers with persisted selection; batch
  preview before generate; live progress (already present); the Report view
  links each row to its deck; "expand all" for power users. Keep the deck GUI
  lean (production), put richness in the engine GUI (analysis).

## 7. Module plan

New:
- `gui_engine.py` (engine GUI entry, port 8586) -- moves Topology/Audit out of
  `gui.py`; adds the analysis viz panel.
- `core/report.py` -- `build_report` + `render_html`.
- `core/engine_present.py:analysis_params(...)` -- the analysis summary.
- tests: `test_report.py`, `test_cli_gui_parity.py`, extend
  `test_combinational_deck.py` (hack-fallback), `test_gui_api.py` (split).

Changed:
- `gui.py` -- remove engine tabs; add Report view; import shared pickers.
- `core/resolver.py` -- hack-template fallback to common.
- `core/batch.py` -- whole-cell arc enumeration + per-arc outcomes for the report.

## 8. Phasing (after approval; one step per turn)

1. Hack-template fallback to common + test (unblocks "any cell").
2. Batch whole-cell enumeration + per-arc outcomes.
3. `core/report.py` (build_report + render_html) + tests; CLI writes report.html.
4. Split GUIs: extract `gui_engine.py`; deck GUI gets the Report view; shared
   pickers; `test_gui_api.py` updated.
5. Engine GUI analysis-params panel + SVG viz.
6. CLI/GUI parity test; docs/runbook.

## 9. Tests (each step, test-first where it fits)

Deck parity + name-invariance (have); hack-fallback selects common; batch
enumerates all combinational arcs of a cell; report dict shape + HTML
toggles/ordering + failures surfaced; CLI vs GUI identical deck; engine
analysis_params shape. Existing 477 pass unchanged. ASCII clean. Signed commits.

## 10. Open items / risks

- Per-cell HACK parity: deferred (obfuscation routes to common); if a specific
  non-obfuscated cell must match a hack, import that hack template later.
- A real combinational cell fixture: repo has only DFFQ1; add an AOI/OAI fixture
  once the team pastes one cell's `.subckt` + `define_cell`/`define_arc` (text).
- Port/launcher for two GUIs: pick 8585 (deck) / 8586 (engine); a `--engine`
  flag or a tiny launcher page is optional.
