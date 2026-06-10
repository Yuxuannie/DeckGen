# DeckGen Showcase GUI: All Features, Visualized (Design)

**Status:** draft -- awaiting user review before writing-plans
**Branch:** feat/phase-2b-engine
**Goal:** one launchable browser tool (`python3.12 gui.py`) that presents EVERY
capability of the flow with a visualized output, polished to demo grade, with the
transistor topology engine as the centerpiece.

**Fixed decisions (from brainstorming):**
- Approach C: extend the single `gui.py` tool; put new logic in focused new modules
  (`core/engine_present.py`, `gui_engine_views.py`); do not bloat `gui.py`; do not
  rebuild the working collateral/cell pickers or the v1 tabs.
- Execution model: HYBRID. No-simulator features (topology, P1, force-bias, --verify
  static checks) run LIVE on any selected cell; simulator-dependent visuals (P2/P3
  transients) are served from a pre-captured cache so they never stall/fail on stage.
- Audience: BOTH, cleanly separated. A top-level face toggle: "Core" (external/SCLD-
  safe) and "Engine" (internal/Florin). The force-bias failure demo and raw verdicts
  live only on the Engine face.
- Zero runtime dependencies: self-contained vanilla HTML/CSS/JS. No CDN, no framework
  (the GUI already removed the Monaco CDN for a built-in viewer). Must work air-gapped.
- Zero non-ASCII bytes in all shipped files (CLAUDE.md).

---

## 1. Architecture

```
gui.py  (launcher; thin additions only)
  |  serves HTML_PAGE (existing) + fragments from gui_engine_views
  |  new routes: /api/engine/topology, /api/engine/audit, /api/engine/wave
  v
core/engine_present.py        (NEW -- data layer, no HTTP/HTML, unit-testable)
  topology_view(...)   -> dict {svg, status, p1, stage_log, ccc, biases, arc_check}
  audit_arcs(...)      -> dict {rows:[...], summary:{...}}
  wave_view(...)       -> dict {svg, markers, source}
      |  reuses:
      |    engine.pipeline.run_pipeline_src      (S0-S5)
      |    engine.draw.render_svg                (topology SVG)
      |    engine.stages.stage5_verify.p3_property
      |    engine.wave.parse_csdf + render_svg   (transients)
      |    core.verify_sidecar                   (audit verdict)
      |    core.resolver / core.collateral       (resolve LPE netlist + arcs)
      v
gui_engine_views.py           (NEW -- presentation fragments + render helpers)
  CSS_TOKENS, CSS_COMPONENTS   (the design system, one place)
  tab_topology_html(), tab_audit_html(), tab_lab_html(), tab_wave_html()
  js_engine()                  (vanilla JS: fetch, render, pan/zoom, interactions)
```

**Module responsibilities (clear boundaries):**
- `core/engine_present.py`: turns a (cell, arc, corner, options) request into
  display-ready data. Knows the engine; knows nothing about HTTP or HTML. Every
  function returns a JSON-serializable dict and never raises to the caller (engine
  failures become `status: "ERROR"` payloads -- same discipline as the sidecar).
- `gui_engine_views.py`: owns all new markup, the design-system CSS, and the
  client JS. No engine imports. Pure string fragments `gui.py` concatenates.
- `gui.py`: routing + assembly only. Existing v1 endpoints and tabs are unchanged;
  the byte output of v1 deck generation is unaffected.

**Minimal, bounded engine change:** `engine/draw.py:render_svg` gains stable hooks
for interactivity -- each net-bearing `<g>`/node carries `class="net"
data-net="<logical_net>"`, and sensitized-path edges carry
`class="edge edge-data|edge-masked|edge-clock"`. This adds attributes only; the
rendered picture is visually identical (existing engine tests still pass). The
front-end uses these hooks for hover/highlight. No other engine change.

---

## 2. Information architecture

**Shell (persistent across tabs):**
- **Top bar:** product mark "DeckGen" + build/version (`engine.__version__`) on the
  left; a **face segmented control** (Core | Engine) center; tab nav right.
- **Left rail (context selector, collapsible):** Node -> Library type -> Corner ->
  Cell -> Arc, reusing the existing `/api/nodes|lib_types|corners|cells|arcs`
  endpoints. One selection drives every tab, so switching tabs keeps context.
- **Main region:** the active view.
- **Right rail (contextual detail):** verdict / stage-trace / legend panel; hidden on
  tabs that do not need it (Generate, Validate).

**Tabs by face:**

Core face (external/SCLD-safe):
1. **Generate** -- existing v1 deck generation (single + batch), restyled to the new
   design system. Output: syntax-highlighted SPICE deck + batch results table.
2. **Topology** -- the centerpiece (Section 4). Output: interactive transistor/CCC
   SVG + P1 verdict + stage trace.
3. **Audit** -- `--verify` across selected arcs (Section 5). Output: audit table +
   summary strip + per-row verdict cards.
4. **Validate** -- existing byte-equal regression vs golden. Output: diff/pass table.

Engine face (internal):
5. **Sensitization Lab** -- Topology + force-bias control (Section 6). Output:
   correct vs forced-wrong side by side, P1 verdicts beneath.
6. **Waveforms** -- cached P2/P3 transients (Section 7). Output: transient SVGs with
   capture-edge/settle markers.

Switching face shows/hides the Engine-only tabs; the Core tabs are always present.
Default face on load: **Core**.

---

## 3. Design system (the "production-level, no-slop" layer)

All tokens live once in `gui_engine_views.CSS_TOKENS`; every component references them.
Aesthetic target: a precise, quiet engineering tool (think a well-made EDA/devtool),
NOT a generic dashboard. Deliberately avoided slop signals: no purple/blue gradients,
no drop-shadow stacks, no emoji in chrome, no full-width hero, no rounded-everything.

**Color tokens (light theme, single accent):**
```
--bg:        #f6f7f9    surface-0 (app background)
--surface:   #ffffff    cards, rails
--surface-2: #f0f2f5    insets, table header, code blocks
--border:    #d8dee4    hairlines (1px)
--text:      #1c2128    primary
--text-mut:  #59636e    secondary/labels
--accent:    #0a4ea3    brand/clock (matches engine clock blue)
--accent-wk: #e7eef7    accent tint (selection, active tab underline)
```
Semantic status (GitHub-grade, colorblind-distinct + always paired with a label):
```
PASS  text #1a7f37 on #dafbe1     FAIL  text #cf222e on #ffebe9
STUB  text #9a6700 on #fff8c5     ERROR text #57606a on #eaeef2
```
Topology path semantics (consistent with `engine/draw.py`):
```
data path   = PASS green     masked scan = FAIL red, dashed     clock = accent blue
```

**Typography:**
```
--font-ui:   -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
--font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace
scale: 12 (meta) / 13 (body) / 14 (control) / 16 (section) / 20 (tab title) px
line-height 1.5 body, 1.3 headings; mono used for nets, SPICE, verdict detail lines.
```

**Spacing & radius:** 4px base scale (4/8/12/16/24/32); radius 6px cards, 4px chips,
0 on the topology canvas; 1px hairline borders, never shadows for structure (one
subtle `0 1px 2px rgba(0,0,0,.04)` allowed on the floating right-rail only).

**Core components (all vanilla):**
- **StatusChip** -- `[PASS]` colored pill, text label inside (never color alone).
- **VerdictCard** -- titled card (P1/P2/P3), status chip, mono detail lines rendered
  `value <= reason` exactly as the engine emits them.
- **StatTile** -- big number + label (for the Audit summary strip).
- **DataTable** -- zebra-free, hairline rows, sticky header, monospace cells for
  identifiers, status chips inline; row click expands a detail drawer.
- **Segmented control** -- the face toggle and small mode switches.
- **Legend** -- topology color/role key, always visible on the Topology canvas.
- **Toast** -- transient non-blocking errors.
- **CodeBlock** -- mono, `--surface-2`, line numbers optional; reuses the existing
  built-in source viewer styling where possible.

**Motion:** 140ms ease-out on tab/panel show-hide and path-highlight opacity; the
topology pan/zoom is direct (no inertia); no bounce, no spinners longer than a thin
top progress bar. Respect `prefers-reduced-motion`.

**Layout:** desktop-first (it is a presentation tool), min width 1100px comfortable;
CSS grid shell: `top bar / [left rail | main | right rail]`. Rails collapsible to
maximize the canvas for projector use. A "presenter" affordance: `f` toggles
full-canvas (hide both rails) for the topology money shot.

---

## 4. Topology view (centerpiece)

**Purpose:** make the name-blind topology engine legible at a glance -- "from a raw
LPE netlist, with no name hints, it found the storage, the clock, and proved which
input the arc actually measures."

**Layout:** full-bleed canvas (main) + right rail (verdict + trace + legend).

**Canvas:**
- Renders `engine/draw.py:render_svg(graph, ccc, sens, arc)` inline (self-contained
  SVG, no `<img>` -- inline so JS can style/interact).
- **Pan/zoom** via `viewBox` manipulation in vanilla JS (drag = pan, wheel = zoom to
  cursor, buttons for +/-/fit). No library.
- **Coloring:** CCC components get distinct fills from the engine palette; storage
  nodes carry a master/slave badge; the sensitized path is emphasized -- data path
  solid green, masked scan red dashed, clock blue (the `data-*`/`class` hooks from
  Section 1).
- **Interactions:** hover a net -> that net + its influence edges raise opacity, the
  rest dim to 35%; click a net -> pin it in the right rail (role, CCC id, raw extracted
  nodes it merged from). Toggle "show series nodes" maps to the engine's
  `--topo-full` (anonymous tristate-stack internals on/off).
- **Empty/ERROR states:** if the engine returns `status:"ERROR"` (unsupported
  topology) the canvas shows a centered ERROR card (gray) with the one-line reason and
  the stage trace up to the failure -- never a blank canvas, never a stack trace dump.

**Right rail:**
- **P1 VerdictCard:** status chip (PASS/FAIL), obligation line, each side-pin bias as
  `pin = value <= reason`, and the `arc_check` line (AGREE / DISAGREE / derived
  independently) rendered as its own chip.
- **Stage trace:** the six `S0..S5` one-liners (mono), so the audience sees R-merge ->
  CCC -> sensitize -> init -> deck -> verify in one column.
- **CCC summary:** components count + storage roles (`master: [...]; slave: [...]`).
- **Legend:** the color/role key.

**Data flow:** `POST /api/engine/topology {node,lib,cell,corner,arc?,when?}` ->
`engine_present.topology_view` resolves the LPE netlist via the collateral store, runs
`run_pipeline_src`, returns `{svg, status, p1, stage_log, ccc, biases, arc_check}`.
Live, sub-second on real cells.

---

## 5. Audit view

**Purpose:** the audit-table headline -- "v2 independently re-derived and checked
every arc v1 produced."

**Layout:** summary strip (top) + audit DataTable (main); row click -> verdict drawer.

- **Summary strip (StatTiles):** total arcs; P1 PASS/FAIL/ERROR counts; P3
  PASS/STUB/FAIL; bias_match MATCH/MISMATCH/NON_CRITICAL; arc_check agree-rate %.
  These are the demo's headline numbers -- computed, not decorative.
- **Table columns:** Cell | Arc | P1 | P2 | P3 | bias_match | arc_check | notes.
  Status cells are chips; identifiers monospace; a MISMATCH or FAIL row gets a subtle
  left red border so problems are scannable.
- **Row drawer:** the three VerdictCards (P1/P2/P3) + derived-vs-golden bias table for
  that arc.
- **Data flow:** `POST /api/engine/audit {node,lib,corner,arcs[]}` ->
  `engine_present.audit_arcs` runs the v1 resolve + `verify_arc` per arc (no hspice;
  P1 real, P2 STUB, P3 static) and returns rows + summary. For a large arc list the
  endpoint streams NDJSON progress (reusing the existing generate-progress pattern in
  `gui.py`) so the table fills incrementally with a thin progress bar.
- **Export:** a "Download audit.csv" button emits exactly the spec's CSV columns
  (cell, arc, corner, P1, P2, P3, bias_match, arc_check, notes) -- the same schema the
  standalone batch runner will use, so the GUI and the runner agree.

---

## 6. Sensitization Lab (Engine face)

**Purpose:** the "auditor catches a wrong bias" demo, kept off the Core face.

**Layout:** two topology canvases side by side -- LEFT "derived" (correct), RIGHT
"forced". A force-bias control above the right canvas: a dropdown of the cell's side
pins + a 0/1 toggle (repeatable for multiple pins), and a "Apply" button.

- LEFT is the normal `topology_view` (P1 PASS, correct bias).
- RIGHT calls `topology_view(..., force_bias={PIN:VAL})`; when the forced value
  breaks sensitization, P1 flips to **FAIL** and the canvas highlights the now-live
  competing path (e.g., SI) in the masked-red treatment turned "live" -- visually the
  red path lights up. Each canvas has its P1 VerdictCard beneath it, so the audience
  reads PASS vs FAIL with the obligation text naming the competing path.
- Reuses `topology_view`'s `force_bias` parameter end to end (already implemented in
  Stage 2 via `arc.raw["force_bias"]`).

---

## 7. Waveforms (Engine face, sim-backed via cache)

**Purpose:** show the real silicon evidence (P2 differential, P3 settled-state)
without depending on hspice at demo time.

**Sim cache layout:**
```
showcase_cache/
  manifest.json                         # {(cell,corner,arc) -> {p2_svg, p3_note, captured_at}}
  <cell>/<corner>/<arc>/
    p2_wave.tr0          # raw CSDF (provenance)
    p2_wave.svg          # rendered transient (engine.wave.render_svg)
    verdict.json         # the P2/P3 verdict captured at the same time
```
- **Capture tool** `tools/capture_showcase.py` (run ONCE on the server with hspice):
  for each showcase (cell,corner,arc) it runs the engine `--wave` + `--sim` path,
  renders the transient SVG, and writes the cache + manifest. Documented; not run at
  demo time.
- **GUI:** `POST /api/engine/wave {node,lib,cell,corner,arc}` ->
  `engine_present.wave_view` reads the cache. Returns `{svg, markers, source}` where
  `source` is `"cached"` (served) or `"missing"`. On `missing`, the view shows a clean
  empty state: "No captured simulation for this arc -- run tools/capture_showcase.py on
  the server." Never a broken image.
- **View:** the transient SVG (CP/D/state-node traces) with the capture-edge and
  settle markers, the P2 differential verdict (master tracks-D, slave holds-prior,
  complementary), and the P3 settled-state result, each as a VerdictCard. A
  "captured on server <date>" provenance line.

---

## 8. API endpoints (new, all POST JSON unless noted)

```
/api/engine/topology  {node,lib,cell,corner,arc?,when?,force_bias?}
    -> {status, svg, p1:{status,detail[]}, stage_log[], ccc:{components,roles},
        biases:{pin:{value,reason}}, arc_check}
/api/engine/audit     {node,lib,corner,arcs[]}        (NDJSON progress + final summary)
    -> stream of {row} then {summary:{...}}
/api/engine/audit_csv {node,lib,corner,arcs[]}        -> text/csv (the 9 columns)
/api/engine/wave      {node,lib,cell,corner,arc}
    -> {source, svg, markers[], p2:{...}, p3:{...}}
```
Existing endpoints (`/api/nodes|lib_types|corners|cells|arcs|preview_v2|generate_v2|
validate|...`) are unchanged and reused. Every new endpoint catches all exceptions and
returns `{status:"ERROR", error:{summary}}` with HTTP 200 so the UI renders an error
card rather than a dead fetch.

---

## 9. Error, empty, and loading states (designed, not afterthoughts)

- **Loading:** a 2px top progress bar (accent), never a full-screen spinner. Topology/
  audit requests show it; sub-second so it mostly flashes.
- **Engine ERROR:** gray ERROR card with the one-line reason + available stage trace.
- **Unsupported cell (no storage / combinational):** Topology still renders the graph;
  P1 card explains "no sequential storage -- sensitization N/A" rather than FAIL-looking
  red. (engine_present maps this to a distinct `status:"N/A"` so it is not mis-shown as
  failure.)
- **Missing sim cache:** the Waveforms empty state above.
- **No collateral selected:** each tab shows a quiet "Select a cell to begin" hint.

---

## 10. Accessibility & performance

- Status never conveyed by color alone (always a text label in the chip).
- Keyboard: tab nav, arrow-move table selection, `f` full-canvas, `+/-/0` zoom.
- Contrast: all text/background pairs meet WCAG AA (the token pairs above are chosen
  for it).
- Performance: topology SVG is generated server-side once per selection and cached in
  memory keyed by (cell, when, force_bias); pan/zoom is pure client viewBox math
  (60fps, no re-fetch). Audit streams so the table is responsive on large arc sets.

---

## 11. Testing

New file `tests/test_engine_present.py` (data layer -- the important one):
- `topology_view` on the engine fixture (`SDFX_LPE_PLACEHOLDER`) returns
  `status:"OK"`, an SVG that `xml.dom.minidom.parseString` accepts, a P1 dict with
  `status=="PASS"`, and `data-net` hooks present in the SVG.
- `topology_view(force_bias={"SE":1})` returns P1 `status=="FAIL"` with "SI" in the
  obligation.
- `topology_view` on a bodyless/garbage netlist returns `status:"ERROR"` (no raise).
- `audit_arcs` over the DFFQ1 collateral fixture returns one row per arc with the 9
  CSV fields populated and a summary dict whose counts sum to the row count.
- `audit_csv` output has exactly the 9 columns in the fixed order.
- `wave_view` with no cache returns `source:"missing"` (no raise, no file needed).

Endpoint smokes in `tests/test_gui_api.py` (extend existing): each `/api/engine/*`
returns 200 with the documented top-level keys on the fixtures; a forced engine
exception yields `status:"ERROR"`, not a 500.

Regression: the existing v1 GUI endpoints and `tests/test_gui_api.py` cases pass
unchanged; `engine/` test suite passes unchanged (the `draw.py` attribute additions do
not alter existing assertions). Non-ASCII gate empty across all new files. Run with
`python3.12 -m pytest tests/`.

---

## 12. Build phasing (for the implementation plan)

The spec is one cohesive feature but sequences cleanly so each phase is demo-able:
- **Phase 1 -- shell + design system + Topology + Audit (live, no sim).** This alone
  covers the centerpiece and the audit headline; fully external-demo-ready.
- **Phase 2 -- Sensitization Lab + Waveforms cache + capture tool.** The Engine-face
  additions and the sim-backed visuals.
- **Phase 3 -- restyle Generate/Validate into the design system + presenter polish**
  (full-canvas mode, keyboard, CSV export).

Phase 1 is the minimum that satisfies "every feature visualized" for the Core face;
Phases 2-3 complete the Engine face and the polish.

---

## 13. Non-goals

- No new engine algorithms; no v2 deck generation (the engine audits, it does not emit
  decks here).
- No live hspice at demo time (sim is cache-served; live sim is out of scope for the
  GUI).
- No change to v1 deck bytes or the existing v1 endpoints' behavior.
- No external JS/CSS dependencies, no build step, no bundler.
- Not mobile/responsive beyond graceful degradation; it is a desktop presentation tool.

---

## 14. Acceptance criteria

1. `python3.12 gui.py` launches one tool exposing all six tabs across the Core/Engine
   faces; v1 Generate/Validate still work and v1 deck output is byte-unchanged.
2. Topology tab renders the interactive, pan/zoom, color-coded topology SVG for a
   selected real cell, with the P1 verdict + stage trace, live and sub-second.
3. Force-bias demo (Engine face) shows correct-vs-forced side by side with P1 flipping
   to FAIL and the competing path highlighted.
4. Audit tab produces the summary strip + table + CSV export with the 9 fixed columns.
5. Waveforms tab serves cached transients with markers, and degrades to a clean empty
   state when the cache is absent.
6. Every new endpoint returns an ERROR payload (HTTP 200) instead of crashing on bad
   input or unsupported topology.
7. Full test suite green under python3.12; zero non-ASCII bytes in shipped files;
   no external runtime dependency introduced.
