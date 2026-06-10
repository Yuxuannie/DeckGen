# Showcase GUI -- Phase 1 (Shell + Topology + Audit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Core-face showcase to the single `gui.py` tool: an interactive transistor/CCC **Topology** tab (the centerpiece) and an **Audit** tab (the `--verify` headline), backed by a new testable data layer, with a deliberate vanilla design system. No simulator, fully demo-ready on its own.

**Architecture:** New data-layer module `core/engine_present.py` (calls the v2 engine + verify sidecar, returns JSON + ready-to-embed SVG, never raises). New presentation module `gui_engine_views.py` (design-system CSS + tab markup + vanilla JS; no engine imports). `gui.py` gains thin `/api/engine/*` routes and assembles the new fragments into its existing `HTML_PAGE`. A bounded `engine/draw.py` change adds interactivity hooks to the SVG without altering its appearance.

**Tech Stack:** Python 3.12 stdlib (`http.server`, `json`, `xml.dom.minidom` for tests); self-contained vanilla HTML/CSS/JS (no CDN/framework). Spec: `docs/superpowers/specs/2026-06-10-gui-all-features-showcase-design.md`.

**Conventions for every task:** run from repo root `/Users/nieyuxuan/Downloads/Work/4-MCQC/DeckGen`; tests with `python3.12 -m pytest tests/` (never bare `pytest` -- it recurses into an untracked nested copy); zero non-ASCII bytes in shipped files (verify `grep -rPn '[\x80-\xff]' <files>` empty; use `--`/`->` not unicode); never weaken a test assertion; if `git commit` hits a signing error run `git config --local commit.gpgsign false` and retry (do NOT push); end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

**File structure (Phase 1):**
- Create `core/engine_present.py` -- data layer: `topology_view`, `audit_arcs`, `audit_csv`.
- Create `gui_engine_views.py` -- `CSS_TOKENS`, `CSS_COMPONENTS`, `topology_tab_html`, `audit_tab_html`, `engine_js`.
- Modify `engine/draw.py` -- add `data-net` / edge `class` hooks to `render_svg`.
- Modify `gui.py` -- new routes + assemble fragments + Core/Engine face toggle.
- Create `tests/test_engine_present.py`; extend `tests/test_gui_api.py`.

---

### Task 1: SVG interactivity hooks in `engine/draw.py`

**Files:**
- Modify: `engine/draw.py` (the `render_svg` node + edge emission)
- Test: `tests/engine/test_draw.py` (extend)

- [ ] **Step 1: Read the current renderer**

Read `engine/draw.py` fully, especially `render_svg` (around lines 127-200) and how it emits net nodes and the sensitized edges (`_edge_color`, `_classify`). Identify where a net node `<...>` and an edge `<line/path>` are written.

- [ ] **Step 2: Write the failing test** (append to `tests/engine/test_draw.py`)

```python
def test_render_svg_has_interactivity_hooks():
    import os
    from engine.config import ENGINE_DIR
    from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
    from engine.types import Arc
    from engine.draw import render_svg
    with open(os.path.join(ENGINE_DIR, "fixtures",
                           "SDFX_LPE_PLACEHOLDER.subckt"), encoding="ascii") as fh:
        g = stage0_parse.parse(fh.read(), "SDFX_LPE_PLACEHOLDER")
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell="SDFX_LPE_PLACEHOLDER", arc_type="hold", rel_pin="CP",
              rel_dir="rise", constr_pin="D", constr_dir="fall",
              when="notSE_SI", measurement="")
    sens = stage2_sensitize.derive(g, arc, ccc)
    svg = render_svg(g, ccc, sens, arc)
    # still valid SVG
    import xml.dom.minidom as m; m.parseString(svg)
    # interactivity hooks present
    assert 'data-net="' in svg
    # sensitized edges classed for front-end styling
    assert 'class="edge' in svg
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3.12 -m pytest tests/engine/test_draw.py::test_render_svg_has_interactivity_hooks -v`
Expected: FAIL (no `data-net=` in output).

- [ ] **Step 4: Add the hooks**

In `render_svg`, where each named net node is emitted, add `data-net="<net>" class="net"` to the node's group/shape element. Where the sensitized/clock/masked edges are emitted, add `class="edge edge-data"` (measured data path), `class="edge edge-masked"` (masked scan), or `class="edge edge-clock"` (clock) according to the same condition the existing `_edge_color` uses to pick green/red-dashed/blue. Do not change coordinates, colors, or any other attribute -- only append `data-net`/`class`. Keep all existing element attributes.

- [ ] **Step 5: Run the draw tests**

Run: `python3.12 -m pytest tests/engine/test_draw.py -v`
Expected: the new test PASSES and all pre-existing draw tests still pass (the picture is unchanged; only attributes were added).

- [ ] **Step 6: Commit**

```bash
grep -rPn '[\x80-\xff]' engine/draw.py tests/engine/test_draw.py
git add engine/draw.py tests/engine/test_draw.py
git commit -m "feat(engine/draw): add data-net + edge class hooks to render_svg (visual unchanged)"
```

---

### Task 2: `core/engine_present.topology_view`

**Files:**
- Create: `core/engine_present.py`
- Test: `tests/test_engine_present.py`

- [ ] **Step 1: Write the failing tests** (`tests/test_engine_present.py`)

```python
"""core/engine_present.py -- GUI data layer over the v2 engine.
Spec: docs/superpowers/specs/2026-06-10-gui-all-features-showcase-design.md
"""
import os
import xml.dom.minidom as minidom

from core.engine_present import topology_view

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDFX = os.path.join(REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")


class TestTopologyView:
    def test_ok_on_engine_fixture(self):
        r = topology_view(SDFX, "SDFX_LPE_PLACEHOLDER", when="notSE_SI")
        assert r["status"] == "OK"
        minidom.parseString(r["svg"])              # valid SVG
        assert 'data-net="' in r["svg"]            # hooks present
        assert r["p1"]["status"] == "PASS"
        assert any("bias" in d.lower() or "=" in d for d in r["p1"]["detail"])
        assert len(r["stage_log"]) >= 5            # S0..S5 lines
        assert "master" in r["ccc"]["roles"] or "slave" in r["ccc"]["roles"]

    def test_force_bias_fails_and_names_si(self):
        r = topology_view(SDFX, "SDFX_LPE_PLACEHOLDER", when="notSE_SI",
                          force_bias={"SE": 1})
        assert r["status"] == "OK"                 # engine ran fine
        assert r["p1"]["status"] == "FAIL"
        assert "SI" in " ".join(r["p1"]["detail"]) or "SI" in r.get("obligation", "")

    def test_error_path_does_not_raise(self, tmp_path):
        bad = tmp_path / "bad.spi"
        bad.write_text(".subckt BAD a b\n.ends\n", encoding="ascii")
        r = topology_view(str(bad), "BAD")
        assert r["status"] in ("ERROR", "NA")
        assert "error" in r or "p1" in r           # structured, not an exception
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3.12 -m pytest tests/test_engine_present.py -v`
Expected: ImportError (module missing).

- [ ] **Step 3: Implement `core/engine_present.py`**

```python
"""engine_present.py -- data layer that turns a (cell, arc, options) request into
display-ready data for the showcase GUI (spec 2026-06-10).

Calls the v2 engine and the verify sidecar; returns JSON-serializable dicts plus
ready-to-embed SVG. NEVER raises to the caller: any engine/topology failure is
returned as {"status": "ERROR", ...} so the GUI renders a card, not a 500.
"""

import traceback

from engine.pipeline import run_pipeline_src
from engine.draw import render_svg


def _stage_log(result):
    return list(getattr(result, "stage_log", []) or [])


def _ccc_summary(result):
    roles = {}
    for sn in result.ccc.state_nodes:
        roles.setdefault(sn.role, []).append(sn.net)
    return {"components": len(result.ccc.components), "roles": roles}


def topology_view(netlist_path, cell, corner=None, arc_type="hold",
                  rel_pin="CP", rel_dir="rise", constr_pin="D",
                  constr_dir="fall", when=None, force_bias=None):
    """Run S0-S2 on a real LPE netlist and return topology SVG + P1 verdict.

    when/force_bias are optional. Returns a dict that always has 'status'.
    """
    try:
        with open(netlist_path, "r") as fh:
            src = fh.read()
    except OSError as e:
        return {"status": "ERROR",
                "error": "cannot read netlist: %s" % e}

    record = {
        "cell": cell, "arc_type": arc_type,
        "rel_pin": rel_pin, "rel_dir": rel_dir,
        "constr_pin": constr_pin, "constr_dir": constr_dir,
        "when": (when or ""), "measurement": "",
    }
    if force_bias:
        record["force_bias"] = {k: int(v) for k, v in force_bias.items()}

    try:
        result = run_pipeline_src(record, src, "", "", "gui-topology")
    except Exception as e:
        tb = traceback.format_exc().splitlines()[-3:]
        return {"status": "ERROR", "error": str(e), "traceback_tail": tb}

    sens = result.sens
    # No sequential storage -> sensitization not applicable (not a failure).
    if not result.ccc.state_nodes:
        status, p1_status = "NA", "NA"
    else:
        status, p1_status = "OK", ("PASS" if sens.proven else "FAIL")

    try:
        svg = render_svg(result.graph, result.ccc, sens, result.arc)
    except Exception as e:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60">'
               '<text x="10" y="30">topology render error: %s</text></svg>'
               % str(e).replace("<", "").replace(">", ""))

    p1_detail = (
        ["obligation : %s" % sens.p1_obligation]
        + ["bias %s = %s <= %s" % (pin, d.value, d.reason)
           for pin, d in sens.side_biases.items()]
        + ["arc-check  : %s" % sens.arc_check]
    )
    return {
        "status": status,
        "svg": svg,
        "p1": {"status": p1_status, "detail": p1_detail},
        "obligation": sens.p1_obligation,
        "stage_log": _stage_log(result),
        "ccc": _ccc_summary(result),
        "biases": {pin: {"value": d.value, "reason": d.reason}
                   for pin, d in sens.side_biases.items()},
        "arc_check": sens.arc_check,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3.12 -m pytest tests/test_engine_present.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' core/engine_present.py tests/test_engine_present.py
git add core/engine_present.py tests/test_engine_present.py
git commit -m "feat(gui): engine_present.topology_view -- topology SVG + P1 verdict, never raises"
```

---

### Task 3: `audit_arcs` + `audit_csv`

**Files:**
- Modify: `core/engine_present.py`
- Test: `tests/test_engine_present.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_engine_present.py`)

```python
import shutil
from core.engine_present import audit_arcs, audit_csv

FIXTURE_COLLATERAL = os.path.join(REPO, "tests", "fixtures", "collateral")
_NODE, _LIB = "N2P_v1.0", "test_lib"
_CORNER = "ssgnp_0p450v_m40c_cworst_CCworst_T"


def _collateral_root(tmp_path):
    dest = tmp_path / "collateral"
    shutil.copytree(os.path.join(FIXTURE_COLLATERAL, _NODE, _LIB),
                    str(dest / _NODE / _LIB))
    from tools.scan_collateral import build_manifest
    build_manifest(str(dest), _NODE, _LIB)
    return str(dest)


class TestAudit:
    def test_rows_and_summary(self, tmp_path):
        croot = _collateral_root(tmp_path)
        out = audit_arcs(node=_NODE, lib_type=_LIB, corner=_CORNER,
                         arc_ids=["hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1"],
                         collateral_root=croot)
        assert out["rows"], "expected at least one row"
        row = out["rows"][0]
        for k in ("cell", "arc", "corner", "P1", "P2", "P3",
                  "bias_match", "arc_check", "notes"):
            assert k in row
        assert row["cell"] == "DFFQ1"
        s = out["summary"]
        assert s["total"] == len(out["rows"])

    def test_csv_columns_exact_order(self, tmp_path):
        croot = _collateral_root(tmp_path)
        out = audit_arcs(node=_NODE, lib_type=_LIB, corner=_CORNER,
                         arc_ids=["hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1"],
                         collateral_root=croot)
        csv = audit_csv(out["rows"])
        header = csv.splitlines()[0]
        assert header == "cell,arc,corner,P1,P2,P3,bias_match,arc_check,notes"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3.12 -m pytest tests/test_engine_present.py -k Audit -v`
Expected: ImportError (`audit_arcs` not defined).

- [ ] **Step 3: Implement** (append to `core/engine_present.py`)

```python
import csv as _csv
import io
import os

CSV_COLUMNS = ["cell", "arc", "corner", "P1", "P2", "P3",
               "bias_match", "arc_check", "notes"]


def _arc_check_class(line):
    s = (line or "").upper()
    if "DISAGREE" in s:
        return "DISAGREE"
    if "AGREE" in s:
        return "AGREE"
    return "INDEPENDENT"


def audit_arcs(node, lib_type, corner, arc_ids, collateral_root="collateral"):
    """Resolve each arc through v1 and verify it (P1 real, P2 STUB, P3 static).
    Returns {"rows": [...], "summary": {...}}. Never raises per arc.
    """
    from core.parsers.arc import parse_arc_identifier
    from core.resolver import resolve_all_from_collateral
    from core.deck_builder import build_deck
    from core.verify_sidecar import (build_record, extract_meas_block,
                                     build_meas_context, derive_golden_biases,
                                     classify_bias_match)
    from engine.pipeline import run_pipeline_src
    from engine.stages.stage5_verify import p3_property

    rows = []
    for arc_id in arc_ids:
        parsed = parse_arc_identifier(arc_id)
        if parsed is None:
            rows.append({"cell": "?", "arc": arc_id, "corner": corner,
                         "P1": "ERROR", "P2": "ERROR", "P3": "ERROR",
                         "bias_match": "N/A", "arc_check": "INDEPENDENT",
                         "notes": "unparseable arc id"})
            continue
        try:
            info = resolve_all_from_collateral(
                cell_name=parsed["cell_name"], arc_type=parsed["arc_type"],
                rel_pin=parsed["rel_pin"], rel_dir=parsed["rel_dir"],
                constr_pin=parsed["rel_pin"], constr_dir=parsed["rel_dir"],
                probe_pin=parsed["probe_pin"], node=node, lib_type=lib_type,
                corner_name=corner, collateral_root=collateral_root)
            info = info[0] if isinstance(info, list) else info
            info.setdefault("CONSTR_PIN", info.get("REL_PIN", ""))
            lines = build_deck(info, slew=(info.get("INDEX_1_VALUE") or "0",
                                           info.get("INDEX_1_VALUE") or "0"),
                               load=info.get("OUTPUT_LOAD") or "0",
                               when=info.get("WHEN", "NO_CONDITION"),
                               max_slew=info.get("MAX_SLEW") or "0") \
                if info.get("TEMPLATE_DECK_PATH") else []
            record = build_record(info, {"arc_id": arc_id, "corner": corner})
            meas, _mnote = extract_meas_block(lines)
            record["measurement"] = meas
            res = run_pipeline_src(record, open(info["NETLIST_PATH"]).read()
                                   if info.get("NETLIST_PATH") else "",
                                   meas, "", "gui-audit")
            ctx = build_meas_context(lines, info) if lines else None
            res.verdict.p3 = p3_property(ctx, res.init, res.arc, sim_data=None)
            golden = derive_golden_biases(info)
            derived = {p: d.value for p, d in res.sens.side_biases.items()}
            rows.append({
                "cell": parsed["cell_name"], "arc": arc_id, "corner": corner,
                "P1": res.verdict.p1.status.value,
                "P2": res.verdict.p2.status.value,
                "P3": res.verdict.p3.status.value,
                "bias_match": classify_bias_match(
                    derived, res.sens.set_pins, res.sens.masked_pins, golden),
                "arc_check": _arc_check_class(res.sens.arc_check),
                "notes": "",
            })
        except Exception as e:
            rows.append({"cell": parsed.get("cell_name", "?"), "arc": arc_id,
                         "corner": corner, "P1": "ERROR", "P2": "ERROR",
                         "P3": "ERROR", "bias_match": "N/A",
                         "arc_check": "INDEPENDENT", "notes": str(e)[:120]})

    def _count(key):
        c = {}
        for r in rows:
            c[r[key]] = c.get(r[key], 0) + 1
        return c

    agree = sum(1 for r in rows if r["arc_check"] == "AGREE")
    summary = {
        "total": len(rows),
        "P1": _count("P1"), "P2": _count("P2"), "P3": _count("P3"),
        "bias_match": _count("bias_match"),
        "arc_check_agree_rate": round(100.0 * agree / len(rows), 1) if rows else 0.0,
    }
    return {"rows": rows, "summary": summary}


def audit_csv(rows):
    """Serialize rows to CSV with exactly CSV_COLUMNS in order."""
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in CSV_COLUMNS})
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3.12 -m pytest tests/test_engine_present.py -v`
Expected: all pass (TopologyView + Audit). Note: on the fixture netlist (bodyless `DFFQ1_c.spi`) P1 may be ERROR/FAIL -- the test asserts row shape and CSV header, not verdict values.

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' core/engine_present.py tests/test_engine_present.py
git add core/engine_present.py tests/test_engine_present.py
git commit -m "feat(gui): engine_present.audit_arcs + audit_csv (9-column schema, per-arc safe)"
```

---

### Task 4: Design-system CSS in `gui_engine_views.py`

**Files:**
- Create: `gui_engine_views.py`
- Test: `tests/test_gui_api.py` (extend with a fragment smoke)

- [ ] **Step 1: Write the failing test** (append to `tests/test_gui_api.py`)

```python
def test_engine_views_css_tokens_present():
    import gui_engine_views as v
    css = v.CSS_TOKENS + v.CSS_COMPONENTS
    # design tokens defined
    for tok in ("--bg", "--surface", "--accent", "--border", "--text"):
        assert tok in css
    # semantic status classes exist
    for cls in (".chip-pass", ".chip-fail", ".chip-stub", ".chip-error"):
        assert cls in css
    # ascii only
    css.encode("ascii")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3.12 -m pytest tests/test_gui_api.py::test_engine_views_css_tokens_present -v`
Expected: ImportError.

- [ ] **Step 3: Implement the CSS** (`gui_engine_views.py`)

```python
"""gui_engine_views.py -- presentation fragments for the showcase GUI (spec
2026-06-10). Pure strings: design-system CSS, tab markup, vanilla JS. No engine
imports. gui.py concatenates these into HTML_PAGE.
"""

CSS_TOKENS = """
:root{
  --bg:#f6f7f9; --surface:#ffffff; --surface-2:#f0f2f5; --border:#d8dee4;
  --text:#1c2128; --text-mut:#59636e; --accent:#0a4ea3; --accent-wk:#e7eef7;
  --pass-fg:#1a7f37; --pass-bg:#dafbe1; --fail-fg:#cf222e; --fail-bg:#ffebe9;
  --stub-fg:#9a6700; --stub-bg:#fff8c5; --err-fg:#57606a; --err-bg:#eaeef2;
  --path-data:#1a7f37; --path-masked:#cf222e; --path-clock:#0a4ea3;
  --font-ui:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  --font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --r-card:6px; --r-chip:4px; --sp:4px;
}
"""

CSS_COMPONENTS = """
.eng-chip{display:inline-block;padding:1px 8px;border-radius:var(--r-chip);
  font:600 12px/1.6 var(--font-mono);}
.chip-pass{color:var(--pass-fg);background:var(--pass-bg);}
.chip-fail{color:var(--fail-fg);background:var(--fail-bg);}
.chip-stub{color:var(--stub-fg);background:var(--stub-bg);}
.chip-error{color:var(--err-fg);background:var(--err-bg);}
.chip-na{color:var(--err-fg);background:var(--err-bg);}
.eng-card{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-card);padding:12px 14px;margin:0 0 12px;}
.eng-card h4{margin:0 0 8px;font:600 14px var(--font-ui);color:var(--text);}
.eng-detail{font:12px/1.6 var(--font-mono);color:var(--text-mut);
  white-space:pre-wrap;}
.eng-stat{display:inline-block;min-width:84px;padding:8px 12px;margin:0 8px 8px 0;
  border:1px solid var(--border);border-radius:var(--r-card);background:var(--surface);}
.eng-stat .n{font:600 20px var(--font-ui);color:var(--text);}
.eng-stat .l{font:11px var(--font-ui);color:var(--text-mut);text-transform:uppercase;
  letter-spacing:.04em;}
.eng-shell{display:grid;grid-template-columns:1fr 360px;gap:16px;}
.eng-canvas{border:1px solid var(--border);border-radius:var(--r-card);
  background:var(--surface);overflow:hidden;position:relative;min-height:520px;}
.eng-canvas svg{width:100%;height:100%;display:block;cursor:grab;}
.eng-legend{position:absolute;left:10px;bottom:10px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r-card);padding:8px 10px;
  font:11px var(--font-ui);color:var(--text-mut);}
.eng-legend i{display:inline-block;width:14px;height:0;border-top-width:3px;
  border-top-style:solid;margin-right:6px;vertical-align:middle;}
.eng-table{width:100%;border-collapse:collapse;font:13px var(--font-ui);}
.eng-table th{position:sticky;top:0;background:var(--surface-2);text-align:left;
  padding:6px 10px;border-bottom:1px solid var(--border);font-weight:600;}
.eng-table td{padding:6px 10px;border-bottom:1px solid var(--border);
  font-family:var(--font-mono);font-size:12px;}
.eng-row-bad{border-left:3px solid var(--fail-fg);}
.eng-tab-title{font:600 20px var(--font-ui);color:var(--text);margin:0 0 12px;}
.eng-progress{height:2px;background:var(--accent);width:0;transition:width .2s;}
"""
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3.12 -m pytest tests/test_gui_api.py::test_engine_views_css_tokens_present -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' gui_engine_views.py
git add gui_engine_views.py tests/test_gui_api.py
git commit -m "feat(gui): design-system CSS tokens + components for showcase views"
```

---

### Task 5: Topology tab markup + JS (pan/zoom/render)

**Files:**
- Modify: `gui_engine_views.py` (`topology_tab_html`, `engine_js`)
- Test: `tests/test_gui_api.py` (extend)

- [ ] **Step 1: Write the failing test** (append to `tests/test_gui_api.py`)

```python
def test_topology_tab_fragment_structure():
    import gui_engine_views as v
    html = v.topology_tab_html()
    for hook in ('id="eng-topo-canvas"', 'id="eng-topo-verdict"',
                 'id="eng-topo-trace"', "eng-legend"):
        assert hook in html
    js = v.engine_js()
    for fn in ("engTopology", "engPanZoom", "engRenderVerdict"):
        assert fn in js
    (html + js).encode("ascii")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3.12 -m pytest tests/test_gui_api.py::test_topology_tab_fragment_structure -v`
Expected: AttributeError (`topology_tab_html` missing).

- [ ] **Step 3: Implement** (append to `gui_engine_views.py`)

```python
def topology_tab_html():
    return """
<div id="tab-topology" class="eng-pane" style="display:none">
  <div class="eng-tab-title">Topology -- name-blind transistor analysis</div>
  <div class="eng-shell">
    <div class="eng-canvas" id="eng-topo-canvas">
      <div class="eng-legend">
        <div><i style="border-color:var(--path-data)"></i>measured data path</div>
        <div><i style="border-color:var(--path-masked);border-top-style:dashed"></i>masked scan input</div>
        <div><i style="border-color:var(--path-clock)"></i>clock</div>
      </div>
    </div>
    <div>
      <div class="eng-card"><h4>P1 -- Sensitization <span id="eng-topo-p1chip"></span></h4>
        <div class="eng-detail" id="eng-topo-verdict"></div></div>
      <div class="eng-card"><h4>Stage trace</h4>
        <div class="eng-detail" id="eng-topo-trace"></div></div>
      <div class="eng-card"><h4>CCC</h4>
        <div class="eng-detail" id="eng-topo-ccc"></div></div>
    </div>
  </div>
</div>
"""


def engine_js():
    return r"""
function engChip(status){
  var m={PASS:'chip-pass',FAIL:'chip-fail',STUB:'chip-stub',
         ERROR:'chip-error',NA:'chip-na'};
  return '<span class="eng-chip '+(m[status]||'chip-error')+'">'+status+'</span>';
}
function engRenderVerdict(p1){
  document.getElementById('eng-topo-p1chip').innerHTML=engChip(p1.status);
  document.getElementById('eng-topo-verdict').textContent=p1.detail.join('\n');
}
function engPanZoom(canvas){
  var svg=canvas.querySelector('svg'); if(!svg) return;
  var vb=svg.viewBox.baseVal, pan=false, sx=0, sy=0;
  if(!vb || !vb.width){ var bb=svg.getBBox();
    svg.setAttribute('viewBox','0 0 '+bb.width+' '+bb.height); vb=svg.viewBox.baseVal; }
  svg.addEventListener('mousedown',function(e){pan=true;sx=e.clientX;sy=e.clientY;
    svg.style.cursor='grabbing';});
  window.addEventListener('mouseup',function(){pan=false;svg.style.cursor='grab';});
  svg.addEventListener('mousemove',function(e){ if(!pan) return;
    var k=vb.width/svg.clientWidth;
    vb.x-=(e.clientX-sx)*k; vb.y-=(e.clientY-sy)*k; sx=e.clientX; sy=e.clientY; });
  svg.addEventListener('wheel',function(e){e.preventDefault();
    var f=e.deltaY<0?0.9:1.1; vb.x+=vb.width*(1-f)/2; vb.y+=vb.height*(1-f)/2;
    vb.width*=f; vb.height*=f;},{passive:false});
  svg.querySelectorAll('.net').forEach(function(n){
    n.addEventListener('mouseenter',function(){
      svg.querySelectorAll('.net,.edge').forEach(function(x){x.style.opacity='.35';});
      n.style.opacity='1';});
    n.addEventListener('mouseleave',function(){
      svg.querySelectorAll('.net,.edge').forEach(function(x){x.style.opacity='1';});});
  });
}
function engTopology(){
  var b={node:S.node,lib_type:S.libtype,cell:S.cell,corner:S.corner};
  post('/api/engine/topology',b).then(function(d){
    var c=document.getElementById('eng-topo-canvas');
    // keep the legend, replace any prior svg
    var old=c.querySelector('svg'); if(old) old.remove();
    if(d.status==='ERROR'){ c.insertAdjacentHTML('afterbegin',
      '<div class="eng-card chip-error" style="margin:16px">'+
      (d.error||'engine error')+'</div>'); return; }
    c.insertAdjacentHTML('afterbegin',d.svg);
    engPanZoom(c);
    engRenderVerdict(d.p1);
    document.getElementById('eng-topo-trace').textContent=(d.stage_log||[]).join('\n');
    document.getElementById('eng-topo-ccc').textContent=
      'components: '+d.ccc.components+'\nroles: '+JSON.stringify(d.ccc.roles);
  });
}
"""
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3.12 -m pytest tests/test_gui_api.py::test_topology_tab_fragment_structure -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' gui_engine_views.py
git add gui_engine_views.py tests/test_gui_api.py
git commit -m "feat(gui): topology tab markup + vanilla pan/zoom/hover + verdict render"
```

---

### Task 6: Audit tab markup + JS

**Files:**
- Modify: `gui_engine_views.py` (`audit_tab_html`, extend `engine_js`)
- Test: `tests/test_gui_api.py` (extend)

- [ ] **Step 1: Write the failing test** (append)

```python
def test_audit_tab_fragment_structure():
    import gui_engine_views as v
    html = v.audit_tab_html()
    for hook in ('id="eng-audit-summary"', 'id="eng-audit-rows"',
                 'id="eng-audit-csv"'):
        assert hook in html
    assert "engAudit" in v.engine_js()
    (html + v.engine_js()).encode("ascii")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3.12 -m pytest tests/test_gui_api.py::test_audit_tab_fragment_structure -v`
Expected: AttributeError.

- [ ] **Step 3: Implement** (append `audit_tab_html` + add `engAudit` to the `engine_js` return string)

```python
def audit_tab_html():
    return """
<div id="tab-audit" class="eng-pane" style="display:none">
  <div class="eng-tab-title">Audit -- v2 re-derives and checks every arc</div>
  <div id="eng-audit-summary" style="margin-bottom:12px"></div>
  <button id="eng-audit-csv" class="btn">Download audit.csv</button>
  <table class="eng-table"><thead><tr>
    <th>Cell</th><th>Arc</th><th>P1</th><th>P2</th><th>P3</th>
    <th>bias_match</th><th>arc_check</th><th>notes</th></tr></thead>
    <tbody id="eng-audit-rows"></tbody></table>
</div>
"""
```

Add this function body inside the `engine_js()` return string (append before its closing `"""`):

```javascript
function engAudit(){
  var arcs=(S.auditArcs||[]); if(!arcs.length){ arcs=S.queue||[]; }
  post('/api/engine/audit',{node:S.node,lib_type:S.libtype,corner:S.corner,
    arcs:arcs}).then(function(d){
    var tb=document.getElementById('eng-audit-rows'); tb.innerHTML='';
    (d.rows||[]).forEach(function(r){
      var bad=(r.P1==='FAIL'||r.P1==='ERROR'||/^MISMATCH/.test(r.bias_match));
      tb.insertAdjacentHTML('beforeend','<tr'+(bad?' class="eng-row-bad"':'')+'>'+
        '<td>'+r.cell+'</td><td>'+r.arc+'</td>'+
        '<td>'+engChip(r.P1)+'</td><td>'+engChip(r.P2)+'</td><td>'+engChip(r.P3)+'</td>'+
        '<td>'+r.bias_match+'</td><td>'+r.arc_check+'</td><td>'+(r.notes||'')+'</td></tr>');
    });
    var s=d.summary||{}, h='';
    h+='<span class="eng-stat"><span class="n">'+(s.total||0)+'</span><span class="l">arcs</span></span>';
    h+='<span class="eng-stat"><span class="n">'+(s.arc_check_agree_rate||0)+'%</span><span class="l">arc agree</span></span>';
    document.getElementById('eng-audit-summary').innerHTML=h;
  });
  document.getElementById('eng-audit-csv').onclick=function(){
    window.location='/api/engine/audit_csv?node='+encodeURIComponent(S.node)+
      '&lib_type='+encodeURIComponent(S.libtype)+'&corner='+encodeURIComponent(S.corner)+
      '&arcs='+encodeURIComponent((S.auditArcs||S.queue||[]).join(','));
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3.12 -m pytest tests/test_gui_api.py::test_audit_tab_fragment_structure -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' gui_engine_views.py
git add gui_engine_views.py tests/test_gui_api.py
git commit -m "feat(gui): audit tab markup + table/summary render + CSV download"
```

---

### Task 7: Wire `/api/engine/*` routes in `gui.py`

**Files:**
- Modify: `gui.py` (the `do_POST` / `do_GET` dispatch + handler methods)
- Test: `tests/test_gui_api.py` (extend)

- [ ] **Step 1: Read the current routing**

Read `gui.py` `do_POST` (around line 1736+) and `do_GET` (1587+) and how an existing handler reads the JSON body and writes a JSON response (reuse that exact helper/pattern; do not invent a new response mechanism).

- [ ] **Step 2: Write the failing test** (append to `tests/test_gui_api.py`; follow the existing test style in that file for how it invokes handlers -- if the file uses a live `http.client` against a started server, match it; if it calls handler methods directly, match that)

```python
def test_engine_topology_endpoint_ok(tmp_path, monkeypatch):
    # the endpoint must return status + svg + p1 for a real netlist
    import core.engine_present as ep
    res = ep.topology_view(
        __import__("os").path.join(
            __import__("os").path.dirname(__file__), "..",
            "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt"),
        "SDFX_LPE_PLACEHOLDER", when="notSE_SI")
    assert res["status"] == "OK" and "svg" in res and res["p1"]["status"] == "PASS"
```

(Endpoint-level HTTP smoke: add it in the same shape the existing `test_gui_api.py` uses for other `/api/*` routes; assert HTTP 200 and that the JSON body has keys `status`, `svg`, `p1`. If `test_gui_api.py` has no live-server harness, this data-layer assertion plus the fragment tests are sufficient and the HTTP wiring is verified by the Task 9 manual smoke.)

- [ ] **Step 3: Add the routes**

In `do_POST`, add branches mirroring the existing ones:

```python
        elif path == '/api/engine/topology':
            self._engine_topology(body)
        elif path == '/api/engine/audit':
            self._engine_audit(body)
```

In `do_GET`, add (for the CSV download):

```python
        elif self.path.startswith('/api/engine/audit_csv'):
            self._engine_audit_csv()
```

Add the handler methods to the request-handler class, using the SAME json-response
helper the existing handlers use (shown here as `self._json(obj)` -- substitute the
real helper name you found in Step 1):

```python
    def _engine_topology(self, body):
        from core.engine_present import topology_view
        from core.collateral import CollateralStore
        try:
            store = CollateralStore(body.get('collateral_root', _COLLATERAL_ROOT),
                                    body['node'], body['lib_type'],
                                    skip_autoscan=True)
            corner = store.get_corner(body['corner'])
            ndir = corner.get('netlist_dir')
            from core.resolver import NetlistResolver
            npath, _ = NetlistResolver(ndir).resolve(body['cell'])
        except Exception as e:
            self._json({'status': 'ERROR', 'error': 'resolve: %s' % e}); return
        r = topology_view(npath, body['cell'], corner=body.get('corner'),
                          when=body.get('when'),
                          force_bias=body.get('force_bias'))
        self._json(r)

    def _engine_audit(self, body):
        from core.engine_present import audit_arcs
        r = audit_arcs(node=body['node'], lib_type=body['lib_type'],
                       corner=body['corner'], arc_ids=body.get('arcs', []),
                       collateral_root=body.get('collateral_root', _COLLATERAL_ROOT))
        self._json(r)

    def _engine_audit_csv(self):
        import urllib.parse
        from core.engine_present import audit_arcs, audit_csv
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        arcs = [a for a in (q.get('arcs', [''])[0].split(',')) if a]
        r = audit_arcs(node=q['node'][0], lib_type=q['lib_type'][0],
                       corner=q['corner'][0], arc_ids=arcs,
                       collateral_root=_COLLATERAL_ROOT)
        csv = audit_csv(r['rows'])
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv')
        self.send_header('Content-Disposition', 'attachment; filename=audit.csv')
        self.end_headers()
        self.wfile.write(csv.encode('ascii'))
```

If `_COLLATERAL_ROOT` is not already a module constant in `gui.py`, define it near the
other path constants as `os.path.join(script_dir, 'collateral')` consistent with how
`gui.py` locates collateral today (check Step 1). Reuse the existing exception-to-JSON
behavior so a bad request yields `{'status':'ERROR',...}` not a 500.

- [ ] **Step 4: Run to verify**

Run: `python3.12 -m pytest tests/test_gui_api.py -v`
Expected: all pass (new + existing).

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' gui.py
git add gui.py tests/test_gui_api.py
git commit -m "feat(gui): /api/engine/topology|audit|audit_csv routes"
```

---

### Task 8: Assemble face toggle + tabs into `HTML_PAGE`

**Files:**
- Modify: `gui.py` (the `HTML_PAGE` assembly + the tab-switch JS + `<head>` CSS include)
- Test: `tests/test_gui_api.py` (extend)

- [ ] **Step 1: Write the failing test** (append)

```python
def test_index_includes_engine_tabs_and_face_toggle():
    import gui
    page = gui.HTML_PAGE if isinstance(gui.HTML_PAGE, str) else gui.build_page()
    for marker in ('tab-topology', 'tab-audit', 'data-face="engine"',
                   'eng-topo-canvas'):
        assert marker in page
    page.encode('ascii')
```

(If `gui.py` builds the page via a function rather than a module constant, call that
function; match what Step-1 reading of Task 7 found. If it is a constant string, the
fragments must be concatenated into it at import time.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3.12 -m pytest tests/test_gui_api.py::test_index_includes_engine_tabs_and_face_toggle -v`
Expected: FAIL (markers absent).

- [ ] **Step 3: Implement**

In `gui.py`, near the top after imports:

```python
import gui_engine_views as _ev
```

Where `HTML_PAGE` is defined: inject the CSS into `<head>` and the tab fragments into
the tab-content area, and add the face toggle + two nav buttons. Concretely:
- In the `<style>` block (or a new one in `<head>`): insert `_ev.CSS_TOKENS + _ev.CSS_COMPONENTS`.
- In the tab-bar markup (next to the existing Explore/Direct/Validate buttons): add
  `<button class="tab" data-tab="topology" data-face="core">Topology</button>` and
  `<button class="tab" data-tab="audit" data-face="core">Audit</button>`, plus a face
  segmented control: `<span class="face-toggle"><button data-face="core" class="on">Core</button><button data-face="engine">Engine</button></span>`.
- In the panes area: insert `_ev.topology_tab_html() + _ev.audit_tab_html()`.
- Before `</body>`: insert `<script>` + `_ev.engine_js()` + the tab/face switch glue:

```javascript
function engShowTab(name){
  document.querySelectorAll('.eng-pane').forEach(function(p){p.style.display='none';});
  var pane=document.getElementById('tab-'+name); if(pane) pane.style.display='block';
  if(name==='topology') engTopology();
  if(name==='audit') engAudit();
}
function engSetFace(face){
  document.querySelectorAll('[data-face]').forEach(function(el){
    if(el.tagName==='BUTTON'&&el.parentElement.className==='face-toggle'){
      el.classList.toggle('on', el.getAttribute('data-face')===face); return; }
    if(el.classList.contains('tab')){
      el.style.display=(el.getAttribute('data-face')==='engine'&&face==='core')
        ?'none':''; }});
}
```

Wire the new `.tab` buttons to call `engShowTab(data-tab)` and the face buttons to
`engSetFace(data-face)`; default `engSetFace('core')` on load. If `gui.py` already has
a tab-switch function, hook into it rather than duplicating; the engine panes just need
their `engShowTab` trigger. Keep the existing Explore/Direct/Validate behavior intact.

If the page is a single constant string, switch it to an f-string/`.format` or a
`build_page()` that concatenates the fragments at import; expose `HTML_PAGE` (or
`build_page()`) so the test can read it. Do not change the existing v1 tab markup
beyond adding the new buttons.

- [ ] **Step 4: Run to verify it passes**

Run: `python3.12 -m pytest tests/test_gui_api.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' gui.py
git add gui.py tests/test_gui_api.py
git commit -m "feat(gui): mount Topology + Audit tabs and Core/Engine face toggle"
```

---

### Task 9: Manual browser verification + full sweep

**Files:** none new (verification + screenshots)

- [ ] **Step 1: Full suite under python3.12**

Run: `python3.12 -m pytest tests/ -q`
Expected: all pass (pre-existing + new). If anything fails, fix the implementation (never the assertion).

- [ ] **Step 2: Launch and verify in a browser**

```bash
python3.12 gui.py --port 8585
```
Use the `browse` tool (or open `http://127.0.0.1:8585`): select Node -> Lib -> Corner ->
Cell; click **Topology**; confirm the topology SVG renders, pan (drag) and zoom (wheel)
work, hovering a net dims the rest, and the P1 verdict + stage trace + CCC panels
populate. Click **Audit**; confirm the summary stats + table render and "Download
audit.csv" downloads a 9-column CSV. Toggle **Engine**/**Core** and confirm engine-only
tabs (none in Phase 1 beyond what is Core) show/hide as designed (Topology/Audit are
Core; the toggle is wired for Phase 2). Take before/after screenshots of the Topology
money shot for the record.

- [ ] **Step 3: Verify v1 is untouched**

In the same session, confirm Explore/Direct/Validate still generate decks exactly as
before (byte output unchanged -- the new code is additive and the v1 endpoints were not
modified).

- [ ] **Step 4: Non-ASCII gate (shipped files)**

Run: `grep -rPn '[\x80-\xff]' core/engine_present.py gui_engine_views.py gui.py engine/draw.py tests/test_engine_present.py tests/test_gui_api.py`
Expected: empty.

- [ ] **Step 5: Commit any verification fixes; do NOT push** (per CLAUDE.md, check with Yuxuan before pushing).

---

## Self-Review Notes (applied)

- **Spec coverage:** Section 1 architecture -> Tasks 2-8; Section 3 design system ->
  Task 4; Section 4 Topology -> Tasks 1,2,5,7; Section 5 Audit + CSV -> Tasks 3,6,7;
  Section 8 endpoints -> Task 7; Section 11 testing -> every task + Task 9. Spec
  Sections 6 (Sensitization Lab), 7 (Waveforms), 12 Phases 2-3 are intentionally
  DEFERRED to follow-up plans (this is the Phase 1 plan; noted in the goal).
- **Type consistency:** `topology_view(...)->{status,svg,p1{status,detail},stage_log,
  ccc{components,roles},biases,arc_check,obligation}` is produced in Task 2 and consumed
  by `engTopology`/`engRenderVerdict` (Task 5) and the route (Task 7). `audit_arcs(...)
  ->{rows[<9 keys>],summary{total,P1,P2,P3,bias_match,arc_check_agree_rate}}` is produced
  in Task 3 and consumed by `engAudit` (Task 6) and the route (Task 7). `CSV_COLUMNS`
  order is asserted identically in Task 3 and used by `audit_csv`.
- **Known fixture caveat:** the collateral fixture `DFFQ1_c.spi` is bodyless, so audit
  rows over it may show P1=ERROR/FAIL; Task 3 tests assert row/CSV SHAPE, not verdicts.
  The engine-green topology path is proven on the `SDFX_LPE_PLACEHOLDER` fixture (Task 2).
- **JS/CSS testing honesty:** the data layer is TDD'd hard; the vanilla JS/CSS is
  verified by fragment-structure assertions (Tasks 4-6,8) plus the mandatory manual
  browser verification (Task 9), since headless unit-testing of canvas pan/zoom is not
  worth the harness in a stdlib-only tool.

---

## Follow-up plans (not this plan)
- **Phase 2:** Sensitization Lab (force-bias side-by-side, reusing `topology_view`'s
  `force_bias`), Waveforms tab + `showcase_cache/` + `tools/capture_showcase.py`.
- **Phase 3:** restyle Generate/Validate into the design system; presenter polish
  (full-canvas `f`, keyboard zoom, reduced-motion).
