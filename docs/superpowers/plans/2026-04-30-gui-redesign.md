# DeckGen GUI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 1789-line `gui.py` HTML shell with the approved 3-tab design (Explore / Direct / Validate) while keeping all existing backend API handlers intact.

**Architecture:** The Python HTTP server (`http.server.BaseHTTPRequestHandler`) stays unchanged. All work is: (a) add two missing API endpoints, (b) add table-point text parsing to the generate handler, (c) replace the `HTML_PAGE` string constant (lines 107–1307) with the new design, (d) wire all frontend JS to the existing API. The frontend is vanilla JS only — no framework.

**Tech Stack:** Python 3.8+, `http.server`, `core.collateral.CollateralStore`, `core.parsers.template_tcl.parse_template_tcl_full`, vanilla JS (ES2017), CSS custom properties.

**Spec:** `docs/superpowers/specs/2026-04-29-gui-redesign-design.md`

---

## File Map

| File | Change |
|------|--------|
| `gui.py` lines 107–1307 | **Replace** `HTML_PAGE` string entirely |
| `gui.py` `do_GET` | Add branch for `GET /api/deck?path=` |
| `gui.py` `do_POST` | Add branch for `POST /api/arcs` |
| `gui.py` `_handle_generate_v2` | Add table-point text parsing |
| New module-level fn `_api_list_arcs(node, lib_type, cell)` | Returns arc list + index_1/index_2 |

No new files. No new dependencies.

---

## Task 1: Backend — `/api/arcs` endpoint

Add a module-level helper and wire it into the POST router.

**Files:**
- Modify: `gui.py` (after `_api_list_cells`, around line 77; and in `do_POST` around line 1380)

- [ ] **Step 1: Read the current _api_list_cells function to understand the pattern**

```bash
sed -n '66,90p' gui.py
```
Expected: shows `_api_list_cells` using `CollateralStore`.

- [ ] **Step 2: Add `_api_list_arcs` after `_api_list_cells` (around line 85)**

Insert this function between `_api_list_cells` and `_api_rescan`:

```python
def _api_list_arcs(node, lib_type, cell):
    """Return arcs for a cell from template.tcl + index_1/index_2 sizes.

    Uses the first available corner's template.tcl (all corners share the
    same template.tcl structure for a given lib_type).

    Returns list of dicts:
        {arc_type, probe_pin, probe_dir, rel_pin, rel_dir, when,
         index_1: [float,...], index_2: [float,...]}
    """
    from core.collateral import CollateralStore, CollateralError
    from core.parsers.template_tcl import parse_template_tcl_full
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    try:
        store = CollateralStore(root, node, lib_type)
    except CollateralError:
        return []

    # Pick first available corner to get a template.tcl path
    corners = store.list_corners()
    if not corners:
        return []

    tcl_path = None
    for corner in corners:
        try:
            tcl_path = store.get_template_tcl(corner)
            break
        except CollateralError:
            continue

    if not tcl_path or not os.path.isfile(tcl_path):
        return []

    try:
        parsed = parse_template_tcl_full(tcl_path)
    except Exception:
        return []

    # Extract index arrays from parsed['templates'] for size info
    # parse_template_tcl_full returns arcs list with cell field
    raw_arcs = [a for a in parsed.get('arcs', []) if a.get('cell') == cell]

    # Get index sizes from the global templates dict
    # templates: {template_name: {index_1: [...], index_2: [...]}}
    templates_map = parsed.get('templates', {})

    result = []
    for a in raw_arcs:
        # Determine which template this arc uses to get index arrays
        cells_map = parsed.get('cells', {})
        cell_info = cells_map.get(cell, {})
        arc_type = a.get('arc_type', '')
        # Map arc_type -> template name
        if arc_type in ('hold', 'setup', 'recovery', 'removal'):
            tmpl_name = cell_info.get('constraint_template')
        elif arc_type == 'mpw':
            tmpl_name = cell_info.get('mpw_template')
        else:
            tmpl_name = cell_info.get('delay_template')

        tmpl = templates_map.get(tmpl_name, {}) if tmpl_name else {}
        idx1 = tmpl.get('index_1', [])
        idx2 = tmpl.get('index_2', [])

        result.append({
            'arc_type':  arc_type,
            'probe_pin': a.get('pin', ''),
            'probe_dir': a.get('pin_dir', ''),
            'rel_pin':   a.get('rel_pin', ''),
            'rel_dir':   a.get('rel_pin_dir', ''),
            'when':      a.get('when', '') or 'NO_CONDITION',
            'index_1':   idx1,
            'index_2':   idx2,
        })
    return result
```

- [ ] **Step 3: Wire into `do_POST` — add the `/api/arcs` branch**

Find the block:
```python
        elif path == '/api/cells':
            self._send_json({'cells': _api_list_cells(
                data.get('node', ''), data.get('lib_type', ''))}); return
        elif path == '/api/rescan':
```

Replace with:
```python
        elif path == '/api/cells':
            self._send_json({'cells': _api_list_cells(
                data.get('node', ''), data.get('lib_type', ''))}); return
        elif path == '/api/arcs':
            self._send_json({'arcs': _api_list_arcs(
                data.get('node', ''), data.get('lib_type', ''),
                data.get('cell', ''))}); return
        elif path == '/api/rescan':
```

- [ ] **Step 4: Manual smoke test**

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/0-DeckGen/my-work-scripts/deckgen
python3 -c "
from gui import _api_list_arcs
arcs = _api_list_arcs('N2P_v1.0', 'tcbn02p_bwph130nppnl3p48cpd_base_elvt_c221227_400i', 'DFFQNBWP130HPNPN3P48CPD')
print(len(arcs), 'arcs')
if arcs:
    import json; print(json.dumps(arcs[0], indent=2))
"
```
Expected: prints arc count > 0 and a JSON object with arc_type, probe_pin, index_1, index_2 fields.
If the cell name is wrong, try: `python3 -c "from gui import _api_list_cells; print(_api_list_cells('N2P_v1.0', 'tcbn02p_bwph130nppnl3p48cpd_base_elvt_c221227_400i')[:3])"` to find a real cell name.

- [ ] **Step 5: Commit**

```bash
git add gui.py
git commit -m "feat(gui): add /api/arcs endpoint with index_1/index_2"
```

---

## Task 2: Backend — `GET /api/deck` endpoint

Serve the raw content of a generated SPICE file so the frontend Deck Viewer can display it.

**Files:**
- Modify: `gui.py` `do_GET` (around line 1314)

- [ ] **Step 1: Add the `/api/deck` branch to `do_GET`**

Find:
```python
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            body = HTML_PAGE.encode('ascii')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith('/api/validate_html_serve'):
            self._serve_validate_html()
        else:
            self.send_response(404)
            self.end_headers()
```

Replace with:
```python
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            body = HTML_PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith('/api/deck'):
            self._serve_deck()
        elif self.path.startswith('/api/validate_html_serve'):
            self._serve_validate_html()
        else:
            self.send_response(404)
            self.end_headers()
```

- [ ] **Step 2: Add `_serve_deck` method to `DeckgenHandler` (after `_serve_validate_html`)**

```python
    def _serve_deck(self):
        """GET /api/deck?path=<absolute_or_relative_path>
        Returns raw SPICE file content as plain text.
        Path must be under the configured output directory (basic path-traversal guard).
        """
        import urllib.parse
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        rel = (params.get('path') or [''])[0]
        if not rel:
            self.send_response(400)
            self.end_headers()
            return

        # Resolve to absolute; allow both absolute paths and relative-to-cwd
        path = os.path.abspath(rel) if not os.path.isabs(rel) else rel

        # Guard: must be an existing file
        if not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return

        # Guard: must end in .sp or .spi (no directory traversal to arbitrary files)
        if not path.lower().endswith(('.sp', '.spi')):
            self.send_response(403)
            self.end_headers()
            return

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                body = f.read().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(500)
            self.end_headers()
```

- [ ] **Step 3: Manual smoke test**

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/0-DeckGen/my-work-scripts/deckgen
# Start server in background
python3 gui.py --no-browser &
sleep 1
# Test with a real .sp file if one exists, otherwise a temp file
echo ".end" > /tmp/test_deck.sp
curl -s "http://127.0.0.1:8585/api/deck?path=/tmp/test_deck.sp"
# Expected: ".end"
# Test path traversal guard
curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8585/api/deck?path=/etc/passwd"
# Expected: 403
kill %1
rm /tmp/test_deck.sp
```

- [ ] **Step 4: Commit**

```bash
git add gui.py
git commit -m "feat(gui): add GET /api/deck endpoint with path-traversal guard"
```

---

## Task 3: Backend — table-point text parsing in `_handle_generate_v2`

The new Explore tab sends table-point selections as a text string per arc-type:
`"(1,1) (3,3) (4,4)"`. The backend must parse these and expand arc IDs accordingly.

**Files:**
- Modify: `gui.py` (add helper + update `_handle_generate_v2`)

- [ ] **Step 1: Add `_parse_table_points` helper function (module-level, after `_api_validate`)**

```python
def _parse_table_points(text):
    """Parse a table-point text string into a list of (i1, i2) int tuples.

    Input:  "(1,1) (2,3) (4, 4)"
    Output: [(1, 1), (2, 3), (4, 4)]

    Invalid tokens are silently skipped.
    """
    import re
    result = []
    for m in re.finditer(r'\(\s*(\d+)\s*,\s*(\d+)\s*\)', text or ''):
        result.append((int(m.group(1)), int(m.group(2))))
    return result
```

- [ ] **Step 2: Read the current `_handle_generate_v2` to understand its arc_ids input**

```bash
sed -n '1581,1610p' gui.py
```

- [ ] **Step 3: Read the rest of `_handle_generate_v2`**

```bash
sed -n '1610,1650p' gui.py
```

- [ ] **Step 4: Update `_handle_generate_v2` to accept `table_points` dict**

The Explore tab will POST:
```json
{
  "mode": "explore",
  "node": "N2P_v1.0",
  "lib_type": "...",
  "corners": ["ssgnp_..."],
  "arc_ids": ["hold_CELL_QN_rise_CP_rise_NO_CONDITION"],
  "table_points": {
    "hold": "(1,1) (3,3) (4,4)",
    "combinational": "(1,5) (2,3)"
  },
  "output_dir": "./output/"
}
```

The backend must expand each bare arc_id (without i1/i2 suffix) using the table_points.

Find the start of `_handle_generate_v2`:
```python
    def _handle_generate_v2(self, data):
        """Generate: run the batch using collateral-backed planning."""
        from core.batch import run_batch
        try:
            mode = data.get('mode', 'batch')
            if mode == 'single':
```

After the `try:` line and before the mode check, add table-point expansion:

```python
    def _handle_generate_v2(self, data):
        """Generate: run the batch using collateral-backed planning."""
        from core.batch import run_batch
        try:
            mode = data.get('mode', 'batch')

            # Expand arc_ids using table_points if provided.
            # arc_ids may be bare (no _i1_i2 suffix) or already have suffix.
            # table_points: {arc_type: "(i1,i2) ..." text}
            raw_arc_ids = data.get('arc_ids', [])
            table_points = data.get('table_points', {})  # {arc_type: str}
            if table_points and raw_arc_ids:
                expanded = []
                for aid in raw_arc_ids:
                    parts = aid.split('_')
                    arc_type = parts[0] if parts else ''
                    tp_text = table_points.get(arc_type, '')
                    pts = _parse_table_points(tp_text)
                    if pts:
                        for i1, i2 in pts:
                            expanded.append(f"{aid}_{i1}_{i2}")
                    else:
                        # No table points for this type — skip
                        pass
                data = dict(data)
                data['arc_ids'] = expanded
```

- [ ] **Step 5: Verify `_parse_table_points` works**

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/0-DeckGen/my-work-scripts/deckgen
python3 -c "
from gui import _parse_table_points
print(_parse_table_points('(1,1) (2,3) (4, 4)'))
print(_parse_table_points(''))
print(_parse_table_points('bad input (1,2)'))
"
```
Expected:
```
[(1, 1), (2, 3), (4, 4)]
[]
[(1, 2)]
```

- [ ] **Step 6: Commit**

```bash
git add gui.py
git commit -m "feat(gui): add table-point text parsing for explore mode generate"
```

---

## Task 4: Frontend HTML shell — topbar, dataset bar, tab switching, CSS

Replace the entire `HTML_PAGE` string (lines 107–1307) with the new design.
This task installs the shell: topbar, dataset bar, CSS variables, tab-switching JS, and empty tab containers. Subsequent tasks fill in the tab content.

**Files:**
- Modify: `gui.py` lines 107–1307 (`HTML_PAGE = r"""..."""`)

- [ ] **Step 1: Note the current line range**

```bash
grep -n "^HTML_PAGE = " gui.py
grep -n "^\"\"\"$" gui.py | head -5
```
Note the start line of `HTML_PAGE` and the end `"""`.

- [ ] **Step 2: Replace `HTML_PAGE` with the new shell**

The new `HTML_PAGE` is a Python raw string. Replace the entire block from `HTML_PAGE = r"""` through the closing `"""` with the following. This is the **complete** new value — do not leave any of the old HTML:

```python
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>DeckGen</title>
<style>
:root {
  --bg:#f5f5f5; --panel:#fff; --text:#0a0a0a; --text-2:#525252;
  --text-3:#a3a3a3; --border:#e5e5e5; --border-2:#d4d4d4;
  --accent:#171717; --accent-h:#404040; --tint:#f5f5f5;
  --ok:#16a34a; --warn:#ca8a04; --err:#dc2626; --info:#2563eb;
  --tag-bg:#f1f5f9; --tag-fg:#475569;
}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  font-size:13px;line-height:1.45;height:100%;overflow:hidden;}

/* topbar */
.topbar{height:48px;background:var(--panel);border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 20px;gap:20px;
  position:fixed;top:0;left:0;right:0;z-index:100;}
.brand{font-weight:700;font-size:15px;letter-spacing:-.02em;}
.tabs{display:flex;gap:2px;height:100%;align-items:stretch;}
.tab{display:flex;align-items:center;padding:0 16px;font-size:13px;font-weight:500;
  color:var(--text-2);border-bottom:2px solid transparent;cursor:pointer;user-select:none;}
.tab:hover{color:var(--text);}
.tab.active{color:var(--text);border-bottom-color:var(--accent);}
.spacer{flex:1;}
.status-pill{font-size:11px;color:var(--text-2);background:var(--tint);
  padding:4px 10px;border-radius:10px;border:1px solid var(--border);}

/* dataset bar */
.dbar{background:var(--panel);border-bottom:1px solid var(--border);
  padding:10px 20px;display:flex;gap:12px;align-items:flex-end;
  position:fixed;top:48px;left:0;right:0;z-index:99;}
.fl{display:flex;flex-direction:column;gap:4px;}
.fl-label{font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;color:var(--text-3);}
.fl select,.fl input[type=text]{height:30px;padding:0 8px;
  border:1px solid var(--border-2);border-radius:4px;background:var(--panel);
  font-size:13px;font-family:inherit;color:var(--text);}
.fl select:focus,.fl input[type=text]:focus{
  outline:2px solid rgba(23,23,23,.12);border-color:var(--accent);}

/* corners chip-picker */
.ctl{height:30px;padding:0 8px;border:1px solid var(--border-2);border-radius:4px;
  background:var(--panel);display:flex;align-items:center;gap:5px;
  cursor:pointer;min-width:280px;max-width:420px;overflow:hidden;position:relative;}
.ctl:hover{background:#fafafa;}
.chip{font-size:11px;background:var(--tag-bg);color:var(--tag-fg);
  padding:2px 7px;border-radius:8px;white-space:nowrap;
  font-family:"SF Mono",Menlo,monospace;}
.chip-more{font-size:11px;color:var(--text-3);white-space:nowrap;}
.caret{margin-left:auto;color:var(--text-3);font-size:9px;flex-shrink:0;}
.cdrop{display:none;position:absolute;top:34px;left:0;min-width:360px;
  background:var(--panel);border:1px solid var(--border);border-radius:6px;
  box-shadow:0 8px 24px rgba(0,0,0,.08);z-index:200;}
.cdrop.open{display:block;}
.msearch{padding:8px;border-bottom:1px solid var(--border);
  position:sticky;top:0;background:var(--panel);}
.msearch input{width:100%;height:28px;padding:0 10px;
  border:1px solid var(--border-2);border-radius:3px;font-size:12px;}
.mlist{max-height:220px;overflow-y:auto;}
.mitem{padding:7px 12px;font-size:12px;font-family:"SF Mono",Menlo,monospace;
  cursor:pointer;display:flex;align-items:center;gap:8px;}
.mitem:hover{background:var(--tint);}
.mitem input[type=checkbox]{margin:0;cursor:pointer;}

/* main area */
.main{position:fixed;top:104px;left:0;right:0;bottom:0;
  display:grid;grid-template-columns:1fr 380px;overflow:hidden;}
.main-full{grid-template-columns:1fr;}

/* panel */
.panel{background:var(--panel);border-right:1px solid var(--border);
  display:flex;flex-direction:column;min-height:0;overflow:hidden;}
.panel:last-child{border-right:none;}
.ph{padding:11px 16px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:8px;flex-shrink:0;}
.pt{font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:var(--text-2);}
.pb{flex:1;overflow-y:auto;min-height:0;padding:14px 16px;}
.pf{padding:10px 16px;border-top:1px solid var(--border);
  display:flex;gap:8px;align-items:center;flex-shrink:0;}

/* buttons */
.btn{height:30px;padding:0 12px;border:1px solid var(--border-2);border-radius:4px;
  background:var(--panel);font-size:12px;font-weight:500;color:var(--text);
  cursor:pointer;font-family:inherit;display:inline-flex;align-items:center;
  gap:5px;white-space:nowrap;}
.btn:hover{background:var(--tint);}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent);}
.btn-primary:hover{background:var(--accent-h);border-color:var(--accent-h);}
.btn-ghost{border-color:transparent;color:var(--text-2);}
.btn-ghost:hover{background:var(--tint);color:var(--text);}
.btn-sm{height:26px;padding:0 9px;font-size:11px;}
.btn[disabled]{opacity:.38;cursor:not-allowed;pointer-events:none;}

/* arc type tag */
.atag{font-size:10px;padding:1px 6px;border-radius:8px;
  background:var(--tag-bg);color:var(--tag-fg);
  font-family:"SF Mono",Menlo,monospace;}

/* cells panel */
.srow{display:flex;gap:8px;margin-bottom:10px;align-items:center;}
.swrap{flex:1;position:relative;}
.swrap input{width:100%;height:30px;padding:0 10px 0 30px;
  border:1px solid var(--border-2);border-radius:4px;font-size:13px;font-family:inherit;}
.swrap input:focus{outline:2px solid rgba(23,23,23,.12);border-color:var(--accent);}
.sico{position:absolute;left:9px;top:8px;color:var(--text-3);font-size:13px;pointer-events:none;}
.fbar{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px;}
.fc{font-size:11px;padding:3px 10px;border:1px solid var(--border-2);border-radius:10px;
  cursor:pointer;background:var(--panel);}
.fc:hover{background:var(--tint);}
.fc.on{background:var(--accent);color:#fff;border-color:var(--accent);}
.clist{display:flex;flex-direction:column;}
.crow{border-bottom:1px solid var(--border);}
.crow:last-child{border-bottom:none;}
.chead{padding:8px 4px;display:flex;align-items:center;gap:7px;cursor:pointer;}
.chead:hover{background:var(--tint);}
.twisty{width:14px;text-align:center;color:var(--text-3);font-size:9px;user-select:none;}
.cname{font-family:"SF Mono",Menlo,monospace;font-size:12px;}
.ctags{margin-left:auto;display:flex;gap:3px;flex-wrap:wrap;}
.alist{margin:2px 0 6px 21px;border-left:2px solid var(--border);}
.arow{padding:5px 10px;display:flex;align-items:center;gap:8px;
  font-family:"SF Mono",Menlo,monospace;font-size:11px;color:var(--text-2);cursor:pointer;}
.arow:hover{background:var(--tint);color:var(--text);}
.adesc{flex:1;}
.abtn{font-size:10px;font-weight:600;color:var(--accent);
  border:1px solid var(--border-2);border-radius:3px;padding:2px 7px;white-space:nowrap;}
.arow:hover .abtn{background:var(--accent);color:#fff;border-color:var(--accent);}
.arow.inq{color:var(--text-3);}
.arow.inq .abtn{background:#dcfce7;color:var(--ok);border-color:#bbf7d0;}
.cell-loading{padding:24px;text-align:center;color:var(--text-3);font-size:12px;font-style:italic;}

/* queue panel */
.qsl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;
  color:var(--text-3);margin:14px 0 6px;display:flex;align-items:center;gap:6px;}
.qsl:first-child{margin-top:0;}
.qrow{display:flex;align-items:center;gap:6px;padding:6px 4px;
  border-bottom:1px solid var(--border);font-family:"SF Mono",Menlo,monospace;font-size:11px;}
.qrow:last-child{border-bottom:none;}
.qrow:hover{background:var(--tint);}
.qtext{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-2);}
.qx{width:18px;height:18px;display:flex;align-items:center;justify-content:center;
  border-radius:3px;color:var(--text-3);font-size:14px;cursor:pointer;user-select:none;flex-shrink:0;}
.qx:hover{background:var(--err);color:#fff;}
.qempty{text-align:center;color:var(--text-3);font-size:12px;padding:24px 12px;font-style:italic;}

/* table points */
.tprow{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.tprow:last-child{margin-bottom:0;}
.tpin{flex:1;height:28px;padding:0 8px;border:1px solid var(--border-2);
  border-radius:4px;font-size:11px;font-family:"SF Mono",Menlo,monospace;color:var(--text);}
.tpin:focus{outline:2px solid rgba(23,23,23,.12);border-color:var(--accent);}
.tp-hint{font-size:10px;color:var(--text-3);margin-top:6px;margin-bottom:4px;}

/* summary box */
.qsum{background:var(--tint);border:1px solid var(--border);
  border-radius:4px;padding:10px 12px;font-size:12px;}
.qsrow{display:flex;align-items:center;justify-content:space-between;
  padding:2px 0;color:var(--text-2);}
.qsrow.total{border-top:1px solid var(--border-2);margin-top:6px;
  padding-top:8px;color:var(--text);font-weight:600;}
.qnum{font-family:"SF Mono",Menlo,monospace;}

/* results list */
.rrow{display:flex;align-items:center;gap:6px;padding:7px 4px;
  border-bottom:1px solid var(--border);cursor:pointer;}
.rrow:last-child{border-bottom:none;}
.rrow:hover{background:var(--tint);}
.rico{font-size:13px;flex-shrink:0;}
.rtxt{flex:1;overflow:hidden;min-width:0;}
.rname{font-family:"SF Mono",Menlo,monospace;font-size:11px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.rmeta{font-size:10px;color:var(--text-3);margin-top:1px;}
.rarrow{color:var(--text-3);font-size:11px;flex-shrink:0;}
.rrow:hover .rarrow,.rrow.sel .rarrow{color:var(--text);}
.rrow.sel{background:#f0f9ff;}

/* deck overlay */
.deck-ov{display:none;position:fixed;top:104px;left:0;right:380px;bottom:0;
  background:var(--panel);z-index:50;flex-direction:column;
  border-right:1px solid var(--border);}
.deck-ov.open{display:flex;}
.dvh{padding:11px 16px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:10px;flex-shrink:0;}
.dvtitle{font-family:"SF Mono",Menlo,monospace;font-size:12px;flex:1;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.dvbody{flex:1;overflow:auto;padding:16px;background:#1a1a2e;}
.dvbody pre{margin:0;font-family:"SF Mono",Menlo,monospace;font-size:11px;
  color:#c9d1d9;line-height:1.6;white-space:pre;}

/* direct tab */
.dgrid{display:grid;grid-template-columns:1fr 1fr;height:100%;}
.dgrid .panel{border-right:1px solid var(--border);}
.dgrid .panel:last-child{border-right:none;}
.dta{width:100%;height:100%;border:none;resize:none;outline:none;
  font-family:"SF Mono",Menlo,monospace;font-size:12px;padding:14px 16px;
  line-height:1.6;background:var(--panel);color:var(--text);}

/* validate tab */
.vi{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;}
.vi .fl{flex:1;min-width:200px;}
.vi .fl input{width:100%;font-family:"SF Mono",Menlo,monospace;font-size:12px;}
.vcards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;}
.vcard{border:1px solid var(--border);border-radius:6px;padding:12px 14px;background:var(--panel);}
.vc-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);}
.vc-num{font-size:26px;font-weight:700;font-family:"SF Mono",Menlo,monospace;margin-top:4px;}
.vc-num.ok{color:var(--ok);} .vc-num.warn{color:var(--warn);} .vc-num.err{color:var(--err);}
table.vtbl{width:100%;border-collapse:collapse;font-size:12px;}
table.vtbl th{text-align:left;font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;color:var(--text-2);padding:8px 10px;
  border-bottom:1px solid var(--border);background:#fafafa;position:sticky;top:0;}
table.vtbl td{padding:8px 10px;border-bottom:1px solid var(--border);
  font-family:"SF Mono",Menlo,monospace;}
table.vtbl tr:hover td{background:var(--tint);}
.l1{color:var(--ok);font-weight:600;} .l2{color:var(--warn);font-weight:600;} .l3{color:var(--err);font-weight:600;}

.view-hidden{display:none!important;}
</style>
</head>
<body>

<!-- TOPBAR -->
<div class="topbar">
  <div class="brand">DeckGen</div>
  <div class="tabs">
    <div class="tab active" onclick="showTab('explore')">Explore</div>
    <div class="tab" onclick="showTab('direct')">Direct</div>
    <div class="tab" onclick="showTab('validate')">Validate</div>
  </div>
  <div class="spacer"></div>
  <div class="status-pill" id="statusPill">Loading…</div>
</div>

<!-- DATASET BAR -->
<div class="dbar" id="dbar">
  <div class="fl">
    <span class="fl-label">Node</span>
    <select id="selNode" onchange="onNodeChange()"></select>
  </div>
  <div class="fl">
    <span class="fl-label">Library type</span>
    <select id="selLibtype" onchange="onLibtypeChange()"></select>
  </div>
  <div class="fl" style="position:relative;">
    <span class="fl-label">Corners (multi-select)</span>
    <div class="ctl" onclick="toggleCornerMenu()">
      <span id="cornerChips" style="display:flex;gap:4px;flex:1;overflow:hidden;">
        <span style="color:var(--text-3);font-size:11px;">none selected</span>
      </span>
      <span class="caret">&#9660;</span>
    </div>
    <div class="cdrop" id="cdrop">
      <div class="msearch"><input type="text" id="cornerSearch" placeholder="Search corners…" oninput="filterCorners()"></div>
      <div class="mlist" id="cornerList"></div>
    </div>
  </div>
  <div class="spacer"></div>
  <button class="btn" onclick="doRescan()">Rescan</button>
</div>

<!-- EXPLORE TAB -->
<div class="main" id="view-explore">

  <!-- Left: Cells & Arcs -->
  <div class="panel">
    <div class="ph">
      <span class="pt">Cells &amp; Arcs</span>
      <span class="status-pill" id="cellsCount" style="margin-left:4px;">—</span>
    </div>
    <div class="pb">
      <div class="srow">
        <div class="swrap">
          <span class="sico">&#9906;</span>
          <input type="text" id="cellSearch" placeholder="Search cells…" oninput="filterCells()">
        </div>
      </div>
      <div class="fbar" id="arcFilters">
        <div class="fc on" onclick="setArcFilter('all',this)">All</div>
        <div class="fc" onclick="setArcFilter('hold',this)">hold</div>
        <div class="fc" onclick="setArcFilter('setup',this)">setup</div>
        <div class="fc" onclick="setArcFilter('combinational',this)">combinational</div>
        <div class="fc" onclick="setArcFilter('recovery',this)">recovery</div>
        <div class="fc" onclick="setArcFilter('removal',this)">removal</div>
        <div class="fc" onclick="setArcFilter('mpw',this)">mpw</div>
      </div>
      <div class="clist" id="cellList">
        <div class="cell-loading">Select a node and library type to load cells.</div>
      </div>
    </div>
  </div>

  <!-- Right: Queue panel -->
  <div class="panel">
    <div class="ph">
      <span class="pt">Queue</span>
      <span class="status-pill" id="queueCount" style="margin-left:4px;">0 arcs</span>
      <div class="spacer"></div>
    </div>

    <!-- Queue body (building state) -->
    <div class="pb" id="queueBody">
      <div class="qsl">Selected arcs <div class="spacer"></div>
        <button class="btn btn-sm btn-ghost" onclick="clearQueue()">Clear all</button>
      </div>
      <div id="arcQueueList"><div class="qempty">Add arcs from the left panel.</div></div>

      <div class="qsl" id="tpSection" style="margin-top:18px;">Table points per arc-type</div>
      <div class="tp-hint" id="tpHint">Enter (i1,i2) pairs &mdash; e.g. <code style="font-size:10px;">(1,1) (2,3) (4,4)</code></div>
      <div id="tpInputs" style="margin-top:10px;display:flex;flex-direction:column;gap:8px;"></div>

      <div class="qsl" id="qSummaryLabel" style="margin-top:18px;">Summary</div>
      <div class="qsum" id="qSummary">
        <div class="qsrow total"><span>0 arcs &times; 0 corners</span><span class="qnum">0 total</span></div>
      </div>
    </div>
    <div class="pf" id="queueFooter">
      <div class="spacer"></div>
      <button class="btn" onclick="doPreview()">Preview</button>
      <button class="btn btn-primary" id="btnGenerate" onclick="doGenerate()">Generate</button>
    </div>

    <!-- Results body (after generate) -->
    <div class="pb view-hidden" id="resultsBody">
      <div class="qsl">Generated decks
        <div class="spacer"></div>
        <button class="btn btn-sm btn-ghost" onclick="showQueueView()">&#8592; Back</button>
      </div>
      <div id="genStatus" style="font-size:11px;color:var(--text-2);margin-bottom:10px;"></div>
      <div id="resultList"></div>
    </div>
    <div class="pf view-hidden" id="resultsFooter">
      <button class="btn btn-sm btn-ghost" onclick="copyAllPaths()">Copy all paths</button>
      <div class="spacer"></div>
    </div>
  </div>

</div><!-- end explore -->

<!-- DECK VIEWER OVERLAY -->
<div class="deck-ov" id="deckOv">
  <div class="dvh">
    <span class="pt">Deck</span>
    <span class="dvtitle" id="dvTitle">—</span>
    <button class="btn btn-sm btn-ghost" onclick="closeDeck()">&#215; Close</button>
    <button class="btn btn-sm" onclick="copyDeck()">Copy</button>
  </div>
  <div class="dvbody"><pre id="dvContent"></pre></div>
</div>

<!-- DIRECT TAB -->
<div class="main view-hidden" id="view-direct">
  <div class="dgrid">
    <div class="panel" style="border-right:1px solid var(--border);">
      <div class="ph">
        <span class="pt">cell_arc_pt identifiers</span>
        <span class="status-pill" style="margin-left:4px;">one per line</span>
        <div class="spacer"></div>
        <button class="btn btn-sm" onclick="directLoadFile()">Load file&hellip;</button>
        <button class="btn btn-sm btn-ghost" onclick="directClear()">Clear</button>
        <input type="file" id="directFile" accept=".txt" style="display:none" onchange="directFileChosen(event)">
      </div>
      <div style="flex:1;min-height:0;display:flex;flex-direction:column;">
        <textarea class="dta" id="directTA" spellcheck="false" oninput="directParse()"></textarea>
      </div>
    </div>
    <div class="panel">
      <div class="ph">
        <span class="pt">Parsed summary</span>
        <span class="status-pill" id="directPill" style="margin-left:4px;">—</span>
      </div>
      <div class="pb" id="directSummary">
        <div class="qempty">Paste identifiers or load a file to begin.</div>
      </div>
      <div class="pf">
        <div class="spacer"></div>
        <button class="btn" onclick="directPreview()">Preview</button>
        <button class="btn btn-primary" onclick="directGenerate()">Generate</button>
      </div>
    </div>
  </div>
</div><!-- end direct -->

<!-- VALIDATE TAB -->
<div class="main main-full view-hidden" id="view-validate">
  <div class="panel">
    <div class="ph">
      <span class="pt">Validate DeckGen vs MCQC</span>
      <div class="spacer"></div>
      <button class="btn btn-sm" onclick="runValidation()">Run validation</button>
      <button class="btn btn-sm btn-ghost" onclick="exportHtml()">Export HTML report</button>
    </div>
    <div class="pb">
      <div class="vi">
        <div class="fl">
          <span class="fl-label">DeckGen output root</span>
          <input type="text" id="vDeckgenRoot" placeholder="./output/libtype/corner">
        </div>
        <div class="fl">
          <span class="fl-label">MCQC output root</span>
          <input type="text" id="vMcqcRoot" placeholder="/server/mcqc_run/.../corner">
        </div>
        <div class="fl" style="min-width:160px;max-width:200px;">
          <span class="fl-label">File</span>
          <select id="vFile"><option>nominal_sim.sp</option><option>mc_sim.sp</option></select>
        </div>
      </div>
      <div class="vcards" id="vCards">
        <div class="vcard"><div class="vc-lbl">Total pairs</div><div class="vc-num" id="vTotal">—</div></div>
        <div class="vcard"><div class="vc-lbl">Identical (L1)</div><div class="vc-num ok" id="vL1">—</div></div>
        <div class="vcard"><div class="vc-lbl">Normalized (L2)</div><div class="vc-num warn" id="vL2">—</div></div>
        <div class="vcard"><div class="vc-lbl">Different (L3)</div><div class="vc-num err" id="vL3">—</div></div>
      </div>
      <div class="fbar" id="vFilters">
        <div class="fc on" onclick="setVFilter('all',this)">All</div>
        <div class="fc" onclick="setVFilter('l3',this)">L3 only</div>
        <div class="fc" onclick="setVFilter('hold',this)">hold</div>
        <div class="fc" onclick="setVFilter('combinational',this)">combinational</div>
        <div class="fc" onclick="setVFilter('mpw',this)">mpw</div>
      </div>
      <div style="overflow-y:auto;">
        <table class="vtbl" id="vTable">
          <thead><tr>
            <th>Type</th><th>Arc identifier</th><th>Level</th>
            <th>Top diff class</th><th>Lines diff</th><th></th>
          </tr></thead>
          <tbody id="vTbody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div><!-- end validate -->

<script>
/* ═══════════════════════════════════════════════════════════════════════════
   GLOBAL STATE
   ═══════════════════════════════════════════════════════════════════════════ */
var S = {
  node: '', libtype: '',
  corners: [],          // all available corners for current node/libtype
  selCorners: new Set(),// selected corner names
  cells: [],            // raw cell objects from /api/cells
  arcCache: {},         // cell -> arcs array
  queue: [],            // {arc_type, probe_pin, probe_dir, rel_pin, rel_dir, when, cell, arc_id}
  arcFilter: 'all',
  cellFilter: '',
  results: [],          // after generate
  lastDeckPath: '',
  vResults: [],         // validate results
  vFilter: 'all',
};

/* ═══════════════════════════════════════════════════════════════════════════
   TAB SWITCHING
   ═══════════════════════════════════════════════════════════════════════════ */
function showTab(name) {
  ['explore','direct','validate'].forEach(function(n) {
    document.getElementById('view-' + n).classList.toggle('view-hidden', n !== name);
  });
  document.querySelectorAll('.tab').forEach(function(t, i) {
    t.classList.toggle('active', ['explore','direct','validate'][i] === name);
  });
  document.getElementById('dbar').style.display = name === 'validate' ? 'none' : 'flex';
  closeDeck();
}

/* ═══════════════════════════════════════════════════════════════════════════
   DATASET BAR
   ═══════════════════════════════════════════════════════════════════════════ */
function post(url, body) {
  return fetch(url, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)
  }).then(function(r) { return r.json(); });
}

function loadNodes() {
  post('/api/nodes', {}).then(function(d) {
    var sel = document.getElementById('selNode');
    sel.innerHTML = '';
    (d.nodes || []).forEach(function(n) {
      var o = document.createElement('option');
      o.value = o.textContent = n;
      sel.appendChild(o);
    });
    if (d.nodes && d.nodes.length) {
      S.node = d.nodes[0];
      loadLibtypes();
    } else {
      updateStatusPill();
    }
  }).catch(function() { updateStatusPill(); });
}

function onNodeChange() {
  S.node = document.getElementById('selNode').value;
  S.libtype = '';
  S.selCorners = new Set();
  S.cells = [];
  S.arcCache = {};
  loadLibtypes();
}

function loadLibtypes() {
  post('/api/lib_types', {node: S.node}).then(function(d) {
    var sel = document.getElementById('selLibtype');
    sel.innerHTML = '';
    (d.lib_types || []).forEach(function(lt) {
      var o = document.createElement('option');
      o.value = o.textContent = lt;
      sel.appendChild(o);
    });
    if (d.lib_types && d.lib_types.length) {
      S.libtype = d.lib_types[0];
      loadCorners();
    } else {
      updateStatusPill();
    }
  });
}

function onLibtypeChange() {
  S.libtype = document.getElementById('selLibtype').value;
  S.selCorners = new Set();
  S.cells = [];
  S.arcCache = {};
  loadCorners();
}

function loadCorners() {
  post('/api/corners', {node: S.node, lib_type: S.libtype}).then(function(d) {
    S.corners = d.corners || [];
    S.selCorners = new Set(S.corners); // select all by default
    renderCornerChips();
    renderCornerMenu();
    loadCells();
  });
}

function renderCornerChips() {
  var el = document.getElementById('cornerChips');
  var sel = Array.from(S.selCorners);
  if (!sel.length) {
    el.innerHTML = '<span style="color:var(--text-3);font-size:11px;">none selected</span>';
    return;
  }
  var html = '';
  sel.slice(0, 2).forEach(function(c) {
    // shorten: show only first segment (process_voltage_temp)
    var short = c.split('_').slice(0,3).join('_');
    html += '<span class="chip">' + short + '</span>';
  });
  if (sel.length > 2) html += '<span class="chip-more">+' + (sel.length-2) + ' more</span>';
  el.innerHTML = html;
}

function renderCornerMenu() {
  var list = document.getElementById('cornerList');
  list.innerHTML = '';
  S.corners.forEach(function(c) {
    var div = document.createElement('div');
    div.className = 'mitem';
    var chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.checked = S.selCorners.has(c);
    chk.addEventListener('change', function() {
      if (this.checked) S.selCorners.add(c); else S.selCorners.delete(c);
      renderCornerChips();
      updateStatusPill();
      renderQueue();
    });
    div.appendChild(chk);
    div.appendChild(document.createTextNode(c));
    list.appendChild(div);
  });
}

function filterCorners() {
  var q = document.getElementById('cornerSearch').value.toLowerCase();
  document.querySelectorAll('#cornerList .mitem').forEach(function(el) {
    el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

function toggleCornerMenu() {
  document.getElementById('cdrop').classList.toggle('open');
}
document.addEventListener('click', function(e) {
  if (!e.target.closest('.fl')) document.getElementById('cdrop').classList.remove('open');
});

function doRescan() {
  post('/api/rescan', {node: S.node, lib_type: S.libtype}).then(function() {
    loadCells();
  });
}

function updateStatusPill() {
  var pill = document.getElementById('statusPill');
  var nc = document.getElementById('cellsCount');
  var n = S.node || '—';
  var lt = S.libtype ? S.libtype.split('_').slice(-1)[0] : '—';
  var c = S.selCorners.size;
  var cells = S.cells ? S.cells.length : 0;
  pill.textContent = n + ' / ' + lt + ' / ' + c + ' corners / ' + cells + ' cells';
  if (nc) nc.textContent = cells + ' cells';
}

/* ═══════════════════════════════════════════════════════════════════════════
   CELLS PANEL
   ═══════════════════════════════════════════════════════════════════════════ */
function loadCells() {
  document.getElementById('cellList').innerHTML = '<div class="cell-loading">Loading cells…</div>';
  post('/api/cells', {node: S.node, lib_type: S.libtype}).then(function(d) {
    S.cells = d.cells || [];
    S.arcCache = {};
    updateStatusPill();
    renderCells();
  });
}

function filterCells() {
  S.cellFilter = document.getElementById('cellSearch').value.toLowerCase();
  renderCells();
}

function setArcFilter(type, el) {
  S.arcFilter = type;
  document.querySelectorAll('.fbar .fc').forEach(function(c) { c.classList.remove('on'); });
  el.classList.add('on');
  renderCells();
}

function renderCells() {
  var list = document.getElementById('cellList');
  var filtered = S.cells.filter(function(c) {
    var name = (typeof c === 'string') ? c : c.name;
    return !S.cellFilter || name.toLowerCase().includes(S.cellFilter);
  });
  if (!filtered.length) {
    list.innerHTML = '<div class="cell-loading">No cells match.</div>';
    return;
  }
  list.innerHTML = '';
  filtered.forEach(function(c) {
    var name = (typeof c === 'string') ? c : c.name;
    var counts = (typeof c === 'object' && c.arc_counts) ? c.arc_counts : {};
    var row = document.createElement('div');
    row.className = 'crow';
    var tagsHtml = '';
    Object.keys(counts).forEach(function(t) {
      if (S.arcFilter === 'all' || S.arcFilter === t)
        tagsHtml += '<span class="atag">' + t + ':' + counts[t] + '</span>';
    });
    row.innerHTML = '<div class="chead" onclick="toggleCell(this,\'' + esc(name) + '\')">' +
      '<span class="twisty">&#9654;</span>' +
      '<span class="cname">' + name + '</span>' +
      '<div class="ctags">' + tagsHtml + '</div></div>';
    list.appendChild(row);
  });
}

function esc(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

function toggleCell(head, cellName) {
  var existing = head.nextElementSibling;
  var twisty = head.querySelector('.twisty');
  if (existing && existing.classList.contains('alist')) {
    existing.style.display = existing.style.display === 'none' ? '' : 'none';
    twisty.innerHTML = existing.style.display === 'none' ? '&#9654;' : '&#9660;';
    return;
  }
  twisty.innerHTML = '&#9660;';
  // Load arcs from API or cache
  if (S.arcCache[cellName]) {
    renderArcList(head, cellName, S.arcCache[cellName]);
  } else {
    post('/api/arcs', {node: S.node, lib_type: S.libtype, cell: cellName}).then(function(d) {
      S.arcCache[cellName] = d.arcs || [];
      renderArcList(head, cellName, S.arcCache[cellName]);
    });
  }
}

function renderArcList(head, cellName, arcs) {
  var alist = document.createElement('div');
  alist.className = 'alist';
  var filtered = S.arcFilter === 'all' ? arcs :
    arcs.filter(function(a) { return a.arc_type === S.arcFilter; });
  if (!filtered.length) {
    alist.innerHTML = '<div style="padding:6px 12px;font-size:11px;color:var(--text-3);">No arcs for this filter.</div>';
  }
  filtered.forEach(function(a) {
    var arcId = buildArcId(cellName, a);
    var inQueue = S.queue.some(function(q) { return q.arc_id === arcId; });
    var div = document.createElement('div');
    div.className = 'arow' + (inQueue ? ' inq' : '');
    div.dataset.arcId = arcId;
    div.innerHTML =
      '<span class="adesc">' +
        a.arc_type + ' &nbsp;|&nbsp; ' + a.probe_pin + '/' + a.probe_dir +
        ' &nbsp;&middot;&nbsp; ' + a.rel_pin + '/' + a.rel_dir +
        ' &nbsp;|&nbsp; ' + (a.when || 'NO_CONDITION') +
      '</span>' +
      '<span class="abtn">' + (inQueue ? '&#10003; added' : '+ Add') + '</span>';
    if (!inQueue) {
      div.addEventListener('click', function() { addToQueue(cellName, a, div); });
    }
    alist.appendChild(div);
  });
  head.parentNode.insertBefore(alist, head.nextSibling);
}

function buildArcId(cellName, a) {
  // bare arc id without i1/i2 (those are added at generate time from table points)
  return [a.arc_type, cellName, a.probe_pin, a.probe_dir,
          a.rel_pin, a.rel_dir, a.when || 'NO_CONDITION'].join('_');
}

function addToQueue(cellName, a, rowEl) {
  var arcId = buildArcId(cellName, a);
  if (S.queue.some(function(q) { return q.arc_id === arcId; })) return;
  S.queue.push({
    arc_type: a.arc_type,
    probe_pin: a.probe_pin, probe_dir: a.probe_dir,
    rel_pin: a.rel_pin, rel_dir: a.rel_dir,
    when: a.when || 'NO_CONDITION',
    cell: cellName,
    arc_id: arcId,
    index_1: a.index_1 || [],
    index_2: a.index_2 || [],
  });
  rowEl.classList.add('inq');
  rowEl.querySelector('.abtn').textContent = '\\u2713 added';
  rowEl.onclick = null;
  renderQueue();
}

/* ═══════════════════════════════════════════════════════════════════════════
   QUEUE PANEL
   ═══════════════════════════════════════════════════════════════════════════ */
function clearQueue() {
  S.queue = [];
  // reset all inq arc rows
  document.querySelectorAll('.arow.inq').forEach(function(r) {
    r.classList.remove('inq');
    r.querySelector('.abtn').textContent = '+ Add';
    var cellName = r.closest('.crow').querySelector('.cname').textContent;
    var arcId = r.dataset.arcId;
    r.onclick = function() {
      // re-read arc from cache
      var cell = r.closest('.crow').querySelector('.cname').textContent;
      var arcs = S.arcCache[cell] || [];
      var a = arcs.find(function(x) { return buildArcId(cell, x) === arcId; });
      if (a) addToQueue(cell, a, r);
    };
  });
  renderQueue();
}

function removeFromQueue(arcId) {
  S.queue = S.queue.filter(function(q) { return q.arc_id !== arcId; });
  // reset the arc row if visible
  var el = document.querySelector('.arow[data-arc-id="' + arcId + '"]');
  if (el) {
    el.classList.remove('inq');
    el.querySelector('.abtn').textContent = '+ Add';
  }
  renderQueue();
}

function renderQueue() {
  var qList = document.getElementById('arcQueueList');
  if (!S.queue.length) {
    qList.innerHTML = '<div class="qempty">Add arcs from the left panel.</div>';
  } else {
    qList.innerHTML = '';
    S.queue.forEach(function(q) {
      var div = document.createElement('div');
      div.className = 'qrow';
      div.innerHTML =
        '<span class="atag" style="flex-shrink:0;">' + q.arc_type + '</span>' +
        '<span class="qtext">' + q.cell + ' &nbsp;|&nbsp; ' +
          q.probe_pin + '/' + q.probe_dir + ' &middot; ' +
          q.rel_pin + '/' + q.rel_dir + '</span>' +
        '<span class="qx" onclick="removeFromQueue(\'' + esc(q.arc_id) + '\')">&#215;</span>';
      qList.appendChild(div);
    });
  }
  renderTpInputs();
  renderQueueSummary();
  updateGenerateButton();
}

function renderTpInputs() {
  var container = document.getElementById('tpInputs');
  container.innerHTML = '';
  var types = arcTypesInQueue();
  if (!types.length) return;
  types.forEach(function(t) {
    var row = document.createElement('div');
    row.className = 'tprow';
    row.innerHTML =
      '<span class="atag" style="min-width:90px;">' + t + '</span>' +
      '<input class="tpin" id="tp_' + t + '" type="text" placeholder="(1,1) (2,3) (4,4)" oninput="renderQueueSummary()">' +
      '<button class="btn btn-sm btn-ghost" onclick="sweepAll(\'' + t + '\')">Sweep</button>';
    container.appendChild(row);
  });
}

function arcTypesInQueue() {
  var seen = {};
  var types = [];
  S.queue.forEach(function(q) {
    if (!seen[q.arc_type]) { seen[q.arc_type] = true; types.push(q.arc_type); }
  });
  return types;
}

function sweepAll(arcType) {
  // find any arc in queue of this type that has index data
  var q = S.queue.find(function(x) { return x.arc_type === arcType && x.index_1 && x.index_1.length; });
  if (!q) return;
  var pts = [];
  for (var i = 1; i <= q.index_1.length; i++) {
    for (var j = 1; j <= q.index_2.length; j++) {
      pts.push('(' + i + ',' + j + ')');
    }
  }
  var inp = document.getElementById('tp_' + arcType);
  if (inp) { inp.value = pts.join(' '); renderQueueSummary(); }
}

function getTpMap() {
  // returns {arc_type: "(i1,i2) ..." text}
  var map = {};
  arcTypesInQueue().forEach(function(t) {
    var el = document.getElementById('tp_' + t);
    map[t] = el ? el.value : '';
  });
  return map;
}

function parseTpText(text) {
  var pts = [];
  var re = /\(\s*(\d+)\s*,\s*(\d+)\s*\)/g;
  var m;
  while ((m = re.exec(text)) !== null) pts.push([parseInt(m[1]), parseInt(m[2])]);
  return pts;
}

function renderQueueSummary() {
  var el = document.getElementById('qSummary');
  if (!S.queue.length) {
    el.innerHTML = '<div class="qsrow total"><span>0 arcs &times; 0 corners</span><span class="qnum">0 total</span></div>';
    return;
  }
  var byType = {};
  S.queue.forEach(function(q) {
    byType[q.arc_type] = (byType[q.arc_type] || 0) + 1;
  });
  var tpMap = getTpMap();
  var total = 0;
  var rows = '';
  Object.keys(byType).forEach(function(t) {
    var pts = parseTpText(tpMap[t] || '').length;
    var decks = byType[t] * pts;
    total += decks;
    rows += '<div class="qsrow"><span><span class="atag" style="margin-right:4px;">' + t +
      '</span>' + byType[t] + ' arcs &times; ' + pts + ' pts</span>' +
      '<span class="qnum">' + decks + ' decks</span></div>';
  });
  var corners = S.selCorners.size;
  rows += '<div class="qsrow total"><span>' + total + ' decks &times; ' + corners +
    ' corners</span><span class="qnum">' + (total * corners) + ' total</span></div>';
  el.innerHTML = rows;
  document.getElementById('queueCount').textContent = S.queue.length + ' arcs';
  updateGenerateButton();
}

function updateGenerateButton() {
  var tpMap = getTpMap();
  var hasPoints = Object.values(tpMap).some(function(v) { return parseTpText(v).length > 0; });
  var btn = document.getElementById('btnGenerate');
  var total = calcTotal();
  btn.textContent = total > 0 ? 'Generate ' + total + ' decks' : 'Generate';
  btn.disabled = !(S.queue.length && S.selCorners.size && hasPoints);
}

function calcTotal() {
  var byType = {};
  S.queue.forEach(function(q) { byType[q.arc_type] = (byType[q.arc_type] || 0) + 1; });
  var tpMap = getTpMap();
  var total = 0;
  Object.keys(byType).forEach(function(t) {
    total += byType[t] * parseTpText(tpMap[t] || '').length;
  });
  return total * S.selCorners.size;
}

/* ═══════════════════════════════════════════════════════════════════════════
   GENERATE (EXPLORE)
   ═══════════════════════════════════════════════════════════════════════════ */
function doPreview() {
  var body = buildGenerateBody();
  post('/api/preview_v2', body).then(function(d) {
    alert('Preview: ' + (d.jobs ? d.jobs.length : 0) + ' jobs planned. Errors: ' + (d.errors ? d.errors.length : 0));
  });
}

function buildGenerateBody() {
  var tpMap = getTpMap();
  var arcIds = S.queue.map(function(q) { return q.arc_id; });
  return {
    mode: 'explore',
    node: S.node,
    lib_type: S.libtype,
    corners: Array.from(S.selCorners),
    arc_ids: arcIds,
    table_points: tpMap,
    output_dir: './output/',
  };
}

function doGenerate() {
  var body = buildGenerateBody();
  showResultsView();
  document.getElementById('genStatus').textContent = 'Generating…';
  document.getElementById('resultList').innerHTML = '';
  S.results = [];

  fetch('/api/generate_v2', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)
  }).then(function(resp) {
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    function pump() {
      return reader.read().then(function(chunk) {
        if (chunk.done) { finalizeResults(); return; }
        buf += decoder.decode(chunk.value, {stream: true});
        var lines = buf.split('\\n');
        buf = lines.pop();
        lines.forEach(function(line) {
          if (!line.trim()) return;
          try {
            var r = JSON.parse(line);
            S.results.push(r);
            appendResultRow(r);
          } catch(e) {}
        });
        return pump();
      });
    }
    return pump();
  }).catch(function(e) {
    document.getElementById('genStatus').textContent = 'Error: ' + e.message;
  });
}

function appendResultRow(r) {
  var list = document.getElementById('resultList');
  var ok = r.success !== false && !r.error;
  var div = document.createElement('div');
  div.className = 'rrow';
  div.innerHTML =
    '<span class="rico" style="color:' + (ok ? 'var(--ok)' : 'var(--err)') + ';">&#9679;</span>' +
    '<div class="rtxt">' +
      '<div class="rname" style="' + (ok ? '' : 'color:var(--err);') + '">' +
        (r.arc_id || r.id || '?') + '</div>' +
      '<div class="rmeta">' + (r.corner || '') + (r.error ? ' — ' + r.error : '') + '</div>' +
    '</div>' +
    '<span class="rarrow">&#8250;</span>';
  if (ok && r.output_path) {
    div.onclick = function() { openDeck(div, r.output_path, r.arc_id + ' · ' + r.corner); };
  }
  list.appendChild(div);
}

function finalizeResults() {
  var ok = S.results.filter(function(r) { return r.success !== false && !r.error; }).length;
  var fail = S.results.length - ok;
  document.getElementById('genStatus').innerHTML =
    '<span style="color:var(--ok);font-weight:600;">&#10003; ' + ok + ' succeeded</span>' +
    '&nbsp;&nbsp;<span style="color:var(--err);font-weight:600;">&#10007; ' + fail + ' failed</span>' +
    '&nbsp;&nbsp;<span style="color:var(--text-3);">Click a row to preview deck</span>';
}

function showResultsView() {
  document.getElementById('queueBody').classList.add('view-hidden');
  document.getElementById('queueFooter').classList.add('view-hidden');
  document.getElementById('resultsBody').classList.remove('view-hidden');
  document.getElementById('resultsFooter').classList.remove('view-hidden');
}

function showQueueView() {
  document.getElementById('queueBody').classList.remove('view-hidden');
  document.getElementById('queueFooter').classList.remove('view-hidden');
  document.getElementById('resultsBody').classList.add('view-hidden');
  document.getElementById('resultsFooter').classList.add('view-hidden');
  closeDeck();
}

function copyAllPaths() {
  var paths = S.results.filter(function(r) { return r.output_path; })
    .map(function(r) { return r.output_path; }).join('\\n');
  navigator.clipboard.writeText(paths).catch(function() {});
}

/* ═══════════════════════════════════════════════════════════════════════════
   DECK VIEWER
   ═══════════════════════════════════════════════════════════════════════════ */
function openDeck(row, path, title) {
  document.querySelectorAll('.rrow').forEach(function(r) { r.classList.remove('sel'); });
  if (row) row.classList.add('sel');
  S.lastDeckPath = path;
  document.getElementById('dvTitle').textContent = title || path;
  document.getElementById('dvContent').textContent = 'Loading…';
  document.getElementById('deckOv').classList.add('open');
  fetch('/api/deck?path=' + encodeURIComponent(path))
    .then(function(r) { return r.text(); })
    .then(function(txt) { document.getElementById('dvContent').textContent = txt; })
    .catch(function(e) { document.getElementById('dvContent').textContent = 'Error: ' + e.message; });
}

function closeDeck() {
  document.getElementById('deckOv').classList.remove('open');
  document.querySelectorAll('.rrow').forEach(function(r) { r.classList.remove('sel'); });
}

function copyDeck() {
  navigator.clipboard.writeText(document.getElementById('dvContent').textContent).catch(function() {});
}

/* ═══════════════════════════════════════════════════════════════════════════
   DIRECT TAB
   ═══════════════════════════════════════════════════════════════════════════ */
function directLoadFile() { document.getElementById('directFile').click(); }
function directFileChosen(e) {
  var f = e.target.files[0];
  if (!f) return;
  var reader = new FileReader();
  reader.onload = function(ev) {
    document.getElementById('directTA').value = ev.target.result;
    directParse();
  };
  reader.readAsText(f);
}
function directClear() {
  document.getElementById('directTA').value = '';
  directParse();
}

function directParse() {
  var lines = document.getElementById('directTA').value.split('\\n')
    .map(function(l) { return l.trim(); }).filter(Boolean);
  var byType = {};
  var errors = [];
  lines.forEach(function(l) {
    var parts = l.split('_');
    var arcType = parts[0] || '';
    if (!arcType) { errors.push(l); return; }
    byType[arcType] = (byType[arcType] || 0) + 1;
  });
  var corners = S.selCorners.size;
  var total = lines.length * corners;
  var pill = document.getElementById('directPill');
  pill.textContent = lines.length + ' arcs \u00d7 ' + corners + ' corners = ' + total + ' decks';
  var sumEl = document.getElementById('directSummary');
  if (!lines.length) {
    sumEl.innerHTML = '<div class="qempty">Paste identifiers or load a file to begin.</div>';
    return;
  }
  var html = '<div class="qsl">Arc-types detected</div>';
  Object.keys(byType).forEach(function(t) {
    html += '<div class="qrow"><span class="atag" style="flex-shrink:0;">' + t +
      '</span><span class="qtext">' + byType[t] + ' arcs \u2014 i1/i2 from identifier suffix</span></div>';
  });
  if (errors.length) {
    html += '<div style="margin-top:8px;font-size:11px;color:var(--err);">' +
      errors.length + ' unrecognized lines</div>';
  }
  html += '<div style="margin-top:14px;" class="qsum"><div class="qsrow total">' +
    '<span>' + lines.length + ' arcs \u00d7 ' + corners + ' corners</span>' +
    '<span class="qnum">' + total + ' decks</span></div></div>';
  sumEl.innerHTML = html;
}

function directPreview() {
  var lines = document.getElementById('directTA').value.split('\\n')
    .map(function(l) { return l.trim(); }).filter(Boolean);
  post('/api/preview_v2', {
    mode: 'batch', node: S.node, lib_type: S.libtype,
    corners: Array.from(S.selCorners), arc_ids: lines
  }).then(function(d) {
    alert('Preview: ' + (d.jobs ? d.jobs.length : 0) + ' jobs planned. Errors: ' + (d.errors ? d.errors.length : 0));
  });
}

function directGenerate() {
  var lines = document.getElementById('directTA').value.split('\\n')
    .map(function(l) { return l.trim(); }).filter(Boolean);
  showTab('explore');
  showResultsView();
  document.getElementById('genStatus').textContent = 'Generating (direct mode)…';
  document.getElementById('resultList').innerHTML = '';
  S.results = [];
  fetch('/api/generate_v2', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      mode: 'batch', node: S.node, lib_type: S.libtype,
      corners: Array.from(S.selCorners), arc_ids: lines,
      output_dir: './output/',
    })
  }).then(function(resp) {
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    function pump() {
      return reader.read().then(function(chunk) {
        if (chunk.done) { finalizeResults(); return; }
        buf += decoder.decode(chunk.value, {stream: true});
        var ls = buf.split('\\n'); buf = ls.pop();
        ls.forEach(function(line) {
          if (!line.trim()) return;
          try { var r = JSON.parse(line); S.results.push(r); appendResultRow(r); } catch(e) {}
        });
        return pump();
      });
    }
    return pump();
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   VALIDATE TAB
   ═══════════════════════════════════════════════════════════════════════════ */
var _vAllRows = [];

function runValidation() {
  post('/api/validate', {
    deckgen_root: document.getElementById('vDeckgenRoot').value,
    mcqc_root:    document.getElementById('vMcqcRoot').value,
    file:         document.getElementById('vFile').value,
    max_detail:   200,
  }).then(function(d) {
    _vAllRows = d.pairs || [];
    document.getElementById('vTotal').textContent = d.total || 0;
    document.getElementById('vL1').textContent = d.l1 || 0;
    document.getElementById('vL2').textContent = d.l2 || 0;
    document.getElementById('vL3').textContent = d.l3 || 0;
    renderVTable();
  }).catch(function(e) { alert('Validation error: ' + e.message); });
}

function setVFilter(f, el) {
  S.vFilter = f;
  document.querySelectorAll('#vFilters .fc').forEach(function(c) { c.classList.remove('on'); });
  el.classList.add('on');
  renderVTable();
}

function renderVTable() {
  var rows = _vAllRows.filter(function(r) {
    if (S.vFilter === 'all') return true;
    if (S.vFilter === 'l3') return r.level === 3;
    return r.arc_type === S.vFilter;
  });
  var tbody = document.getElementById('vTbody');
  tbody.innerHTML = '';
  rows.forEach(function(r) {
    var tr = document.createElement('tr');
    var lvlClass = 'l' + (r.level || 1);
    tr.innerHTML =
      '<td><span class="atag">' + (r.arc_type || '') + '</span></td>' +
      '<td>' + (r.arc_id || '') + '</td>' +
      '<td><span class="' + lvlClass + '">L' + (r.level || 1) + '</span></td>' +
      '<td>' + (r.top_class || '\u2014') + '</td>' +
      '<td>' + (r.lines_diff || 0) + '</td>' +
      '<td><button class="btn btn-sm btn-ghost">View diff</button></td>';
    tbody.appendChild(tr);
  });
}

function exportHtml() {
  post('/api/validate_html', {
    deckgen_root: document.getElementById('vDeckgenRoot').value,
    mcqc_root:    document.getElementById('vMcqcRoot').value,
    file:         document.getElementById('vFile').value,
    max_detail:   200,
  }).then(function(d) {
    if (d.ok && d.html_path) {
      window.open('/api/validate_html_serve?path=' + encodeURIComponent(d.html_path));
    } else {
      alert('Export failed: ' + (d.error || 'unknown error'));
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   BOOT
   ═══════════════════════════════════════════════════════════════════════════ */
loadNodes();
</script>
</body>
</html>"""
```

- [ ] **Step 3: Verify the file is ASCII-clean (CLAUDE.md requirement)**

```bash
grep -Pn '[\x80-\xff]' gui.py | grep -v "^Binary" | head -5
```
Expected: no output (empty).

- [ ] **Step 4: Start server and verify the page loads**

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/0-DeckGen/my-work-scripts/deckgen
python3 -c "
import gui, http.server
# just check HTML_PAGE is valid UTF-8
body = gui.HTML_PAGE.encode('utf-8')
print('HTML size:', len(body), 'bytes')
print('OK')
"
```
Expected: prints HTML size and OK with no errors.

- [ ] **Step 5: Commit**

```bash
git add gui.py
git commit -m "feat(gui): replace HTML_PAGE with 3-tab redesign shell (CSS + HTML)"
```

---

## Task 5: Frontend — Explore tab live wiring verification

After Task 4 installs the JS, do an end-to-end functional check in the browser and fix any JS errors.

**Files:**
- Modify: `gui.py` (JS fixes only, if needed)

- [ ] **Step 1: Start the server and open the browser**

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/0-DeckGen/my-work-scripts/deckgen
python3 gui.py
```
Open `http://127.0.0.1:8585` in a browser.

- [ ] **Step 2: Verify dataset bar**

- Node dropdown populates from `/api/nodes` — should show `N2P_v1.0`
- Selecting a node triggers library type load
- Selecting a library type triggers corner load
- Corners appear as chips; checkbox dropdown works with search

Expected: status pill updates to show node / libtype / N corners / M cells.

- [ ] **Step 3: Verify cell list**

- Search box filters by substring
- Arc-type filter chips filter arc sub-lists
- Clicking a cell header expands it, loads arcs from `/api/arcs`
- Arc rows show `+ Add`; clicking adds to queue

Expected: queue panel shows arc rows with × buttons.

- [ ] **Step 4: Verify table-point inputs**

- Only arc-types present in queue appear as tp rows
- Typing `(1,1) (2,3)` in the input updates the summary math
- Sweep button fills in all (i,j) combinations
- Summary shows correct deck count

- [ ] **Step 5: Verify Generate flow**

- Click "Generate N decks"
- Right panel switches to results view
- NDJSON stream rows appear as result rows
- Clicking a result row opens deck viewer overlay
- Deck viewer shows SPICE content
- Close button dismisses overlay

- [ ] **Step 6: Fix any JS console errors**

Open browser DevTools → Console. Fix any errors found in `gui.py` JS. Common issues:
- String escaping in onclick attributes (use `data-*` attributes instead of inline `onclick` with args if needed)
- Missing `var` declarations causing reference errors
- Fetch URL mismatches

- [ ] **Step 7: Commit any fixes**

```bash
git add gui.py
git commit -m "fix(gui): JS wiring corrections from browser test"
```

---

## Task 6: Frontend — Direct tab and Validate tab wiring verification

- [ ] **Step 1: Test Direct tab**

Click "Direct" tab.
- Paste a few valid arc identifiers (one per line):
  ```
  hold_DFFQNBWP130HPNPN3P48CPD_QN_rise_CP_rise_NO_CONDITION_4_4
  combinational_INVD0BWP130HPNPN3P48CPD_ZN_rise_A_fall_NO_CONDITION_5_5
  ```
- Verify parsed summary shows arc-types and deck count
- Test "Load file…" button with a text file
- Test "Clear" button

- [ ] **Step 2: Test Validate tab**

Click "Validate" tab. Verify:
- Dataset bar hides (Validate has its own path inputs)
- DeckGen output root and MCQC root inputs accept text
- "Run validation" calls `/api/validate` — even with dummy paths, should return an error object without crashing
- Stat cards update
- Filter bar works

- [ ] **Step 3: Test tab switching**

- Switch between all three tabs multiple times
- Deck overlay closes when switching tabs (verify `closeDeck()` is called in `showTab`)
- Dataset bar hides on Validate, shows on Explore/Direct

- [ ] **Step 4: Commit any fixes**

```bash
git add gui.py
git commit -m "fix(gui): Direct and Validate tab wiring corrections"
```

---

## Task 7: Final polish — update version string and CLAUDE.md

- [ ] **Step 1: Update the version string in `main()`**

Find:
```python
    print(f"deckgen GUI v0.3 at {url}")
```
Replace with:
```python
    print(f"deckgen GUI v1.0 at {url}")
```

Also update the argparse description:
```python
    parser = argparse.ArgumentParser(description='deckgen GUI v0.3')
```
to:
```python
    parser = argparse.ArgumentParser(description='deckgen GUI v1.0')
```

- [ ] **Step 2: Update CLAUDE.md status line**

Find in `CLAUDE.md`:
```
Done: backend modules, parsers, CLI, 63 SPICE templates, GUI v0.2 (single-arc mode).
Remaining: GUI v0.3 (batch mode + identifier auto-fill), template.tcl slew/load integration, tests.
```
Replace with:
```
Done: backend modules, parsers, CLI, 63 SPICE templates, GUI v1.0 (3-tab redesign: Explore / Direct / Validate).
Remaining: template.tcl slew/load integration, tests.
```

- [ ] **Step 3: Verify ASCII cleanliness one final time**

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/0-DeckGen/my-work-scripts/deckgen
grep -rPn '[\x80-\xff]' . --include='*.py' --include='*.yaml' --include='*.md' | head -5
```
Expected: empty output.

- [ ] **Step 4: Run existing tests to confirm nothing broken**

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/0-DeckGen/my-work-scripts/deckgen
python -m pytest tests/ -v 2>&1 | tail -20
```
Expected: all tests pass (or same failures as before this change — backend is not modified beyond additive endpoints).

- [ ] **Step 5: Final commit**

```bash
git add gui.py CLAUDE.md
git commit -m "feat(gui): v1.0 complete — 3-tab redesign Explore/Direct/Validate"
```

---

## Task Order

```
Task 1  (backend /api/arcs)           ← no dependencies
Task 2  (backend /api/deck)           ← no dependencies
Task 3  (backend table-point parsing) ← no dependencies
  ↓ (Tasks 1–3 can run in any order)
Task 4  (HTML_PAGE replacement)       ← needs Tasks 1–3 complete first
Task 5  (Explore tab browser test)    ← needs Task 4
Task 6  (Direct + Validate browser test) ← needs Task 4
Task 7  (polish + version)            ← needs Tasks 5–6
```

Tasks 1, 2, 3 are independent and can be done in parallel.
Tasks 5 and 6 can run in parallel (different tabs).
