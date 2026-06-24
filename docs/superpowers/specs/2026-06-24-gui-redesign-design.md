# GUI Redesign: audit-first divergence-triage workspace (Design)

**Status:** DRAFT -- awaiting Yuxuan review. Brainstormed 2026-06-24.
**Branch:** `claude/lucid-noether-cat8lr`.
**Motivation.** The first real-library run produced **1833 cells / 5088 arcs /
79 DIVERGENCE / 5009 MATCH**. The value is the 79 flagged arcs; the current GUI
cannot triage them or make them communicable. This redesign turns the GUI into a
**divergence-triage workspace** whose unit of work is "look at one flagged arc,
decide kit-error vs engine-error, screenshot it to Yuxuan."

**Driving constraints (from ARCHITECTURE.md):** engine derives from `.subckt`
only (Red Line A); each flagged arc's full story fits **one screen** so a single
screenshot carries it (SS6); stdlib-only, ASCII (SS4).

---

## 1. Information architecture

Top-nav reduced to two entries; current default lands on Audit.

- **Audit** (hero, default) -- the divergence-triage workspace (SS2).
- **Decks** (secondary) -- the existing Explore / Direct / Generate deck-gen flow,
  moved behind one entry. Functionality unchanged; just demoted.

**Removed:** the **Validate** tab (confuses; not needed) and the **old sequential
"Audit" tab** (P1/P2/P3 over a manual queue -- duplicates "Library Audit"; the
sequential path is the research lane, not this tool).

**Topology is no longer a separate tab.** It is embedded in each arc's detail
(SS2.3), which resolves both "topology page" and "blank right pane" at once.

The old `engine_present.topology_view` (sequential SVG) and the old `audit_arcs`
endpoint remain in the codebase (research/Decks use) but are not in the audit nav.

## 2. The Audit workspace (master-detail)

```
+- Audit ----------------------------------------------------------------+
| node[v]  lib_type[v]  corner[v]   [Run audit]                          |
| cells 1833 . arcs 5088 . *FLAGGED 79 . DIVERGENCE 79 . MATCH 5009      |
+--------------+--------------------------------------------------------+
| FLAGGED (79) |  <selected arc detail -- ONE SCREEN, 4 elements>       |
|  AIOI21 B>ZN |                                                         |
|  AOI22 A1>ZN |   (SS2.2 header) (SS2.3 topology) (SS2.4 region table)  |
|  ...sorted   |   (SS2.5 truth table + boolean fn) (SS2.6 kit raw)      |
| TRUST 5009 > |                                                         |
+--------------+--------------------------------------------------------+
        ^ resizable divider (fixes "panes can't resize / right blank")
```

### 2.1 Controls + cohort list (left)
- node / lib_type / corner selectors + **Run audit** (calls `/api/engine/comb_audit`).
- Summary stat chips (cells, arcs, flagged, divergence, unsupported, error, match).
- **FLAGGED list**: 79 rows, importance-sorted (already done by `library_audit`):
  DIVERGENCE > UNSUPPORTED > ERROR, then by count of differing states. Each row:
  `cell . rel_pin>output` + verdict chip. Click selects -> right detail.
- **TRUST (MATCH)**: collapsed `<details>`; clickable to inspect any MATCH arc too
  (same detail view -- topology works for non-flagged arcs as well).
- Left/right divider is **drag-resizable** (pointer-driven; persists in the page).

### 2.2 Detail header
`cell` . `rel_pin -> output` . verdict chip . **derived boolean function**
(e.g. `ZN = B*!(A1*A2)`), recovered from the truth table the engine evaluates.

### 2.3 Topology -- PUN/PDN network with per-state conduction highlight (NEW)
The hard new component. From the cell `.subckt` `DeviceGraph`:
- Partition transistors into **PUN** (PMOS, pull toward VDD/VPP) and **PDN**
  (NMOS, pull toward VSS/VBB), per driven net. Multi-stage cells (AIOI21 inverter
  + AOI21 core; AOAI 3 levels) render **one PUN/PDN block per driven net**
  (internal nodes + the output), so the path across stages is visible.
- Infer **series/parallel** structure from shared source/drain nets (series =
  devices chained drain->source between a rail and the driven net; parallel =
  devices sharing both endpoints). Reuse the CCC/SIG machinery
  (`engine.switchlevel`, `stage1_ccc`) -- SIG already is the conducting-device set.
- **State stepper** (`<` `>`): walks the side-pin states relevant to the arc
  (the differing states first). For the selected state, run `switchlevel.evaluate`
  and **highlight conducting transistors** + the live path that makes (or fails to
  make) `output` depend on `rel_pin`. This visually answers "why does this state
  sensitize / why is it blocked."
- SVG, rails as horizontal bars (VDD top, VSS bottom), driven nets in between,
  devices as labelled boxes (PMOS/NMOS color-coded), ON devices highlighted, the
  toggling `rel_pin` and `output` emphasized.
- **Fidelity bar:** readable schematic, not production schematic. If series/parallel
  inference is ambiguous for a deep cell, fall back to a net x device bipartite
  layout with the same per-state highlight (never fail to render).

### 2.4 Region comparison table (engine vs kit, per state)
Enumerate the side-pin state space `{0,1}^n` (n = |side pins|). One row per state:
`side-pin values | engine (SENS / BLOCKED + out-dir) | kit (covered? from -when) |
diff`. Diff cells highlighted gold: **MISS** (engine SENS, kit omits) / **EXTRA**
(kit covers, engine BLOCKED). This is the region-equivalence verdict made visual.

### 2.5 Truth table + boolean function
`output` value over all input combinations (engine `switchlevel.evaluate`), and the
recovered boolean expression -- for human cross-check ("does this match the cell I
think it is").

### 2.6 kit raw
The cell's `define_arc` lines from `template.tcl` for this `(rel_pin, output)`:
`-when` + `-vector`, verbatim -- the audited object, for direct comparison.

## 3. Aesthetic (frontend-design)
Purple `#5b2a86` (engine / flagged primary), gold `#b8860b` (diff / needs-attention
highlight), light surfaces, monospace for technical data. Consistent with the
existing engine CSS tokens and ARCHITECTURE SS9. The one-screen detail is the
screenshot unit -- dense but scannable, no wasted whitespace.

## 4. Backend
- Reuse `core/library_audit.py` (cohort report) and `core/engine_present.py`.
- **New per-arc detail endpoint** `/api/engine/arc_detail` {node, lib_type, corner,
  cell, rel_pin, output} -> JSON: region table rows, truth table, boolean function,
  kit raw arc lines, and the topology model (PUN/PDN structure + per-state ON sets).
- **New module** `core/topo_pundn.py` (engine-side, stdlib): PUN/PDN extraction +
  series/parallel inference + per-state conduction; and an SVG renderer (in
  `engine/` or `gui_engine_views`-adjacent) that consumes it. Pure functions,
  unit-testable against the synthetic anchors (AIOI21/AOI22/OAI22/AOAI/HA) whose
  structure is known.
- All engine-side derivation depends on `.subckt` only; `template.tcl` is read only
  for the kit-raw panel and the region cross-check (Red Line A preserved).

## 5. Delivery
Both phases delivered together (Yuxuan's call):
1. IA cleanup (remove Validate + old Audit; Decks demotion; Audit default) +
   master-detail resizable layout + region table + truth table + kit raw.
2. PUN/PDN topology renderer + per-state conduction highlight + state stepper.

## 6. Testing / scope / honesty
- Test-first: `core/topo_pundn.py` unit-tested against the 5 synthetic anchors
  (known PUN/PDN structure; e.g. AIOI21 B has parallel PMOS at `!A1&!A2`, single
  elsewhere). Region-table + boolean-function builders unit-tested. GUI wiring
  smoke-tested (page assembles; endpoint returns shape) like the existing GUI tests.
- Never weaken a test; keep all existing tests green; ASCII; stdlib-only.
- Out of scope: sequential cells (research lane); deck byte-parity (de-emphasized
  by Yuxuan); production-grade schematic auto-layout; in-GUI marking/export (the
  one-screen screenshot is the communication channel for now).
- Honesty: the topology renderer is a readable approximation, not a SPICE
  schematic; its job is to make a human triage decision fast, not to be a layout
  tool.

## 7. Open items for the reviewer
1. PUN/PDN fidelity: agree "readable, with bipartite fallback" is enough for v1?
2. Region table for cells with many side pins (n large -> 2^n rows): cap the table
   at the differing + boundary states with a "show all 2^n" toggle? (Proposed: yes,
   show differing states + a toggle; never render thousands of rows by default.)
3. Decks demotion: one "Decks" nav entry containing the existing Explore/Direct
   sub-views -- agree, vs a separate launch?
