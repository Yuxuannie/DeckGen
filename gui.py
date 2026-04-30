#!/usr/bin/env python3
"""
gui.py - Browser-based GUI for deckgen v0.3.

Two-column layout: left = inputs (targets, corners, files, overrides),
right = job table, log, SPICE preview.

Usage:
    python gui.py [--port 8585] [--no-browser]
"""

import argparse
import http.server
import json
import os
import re
import sys
import threading
import webbrowser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from core.resolver import ResolutionError, TemplateResolver
from core.deck_builder import build_deck
from core.parsers.arc import parse_arc_identifier, parse_arc_list
from core.parsers.corner import parse_corner_name, parse_corner_list
from core.batch import plan_jobs, execute_jobs, _job_to_arc_info


# ---------------------------------------------------------------------------
# Collateral helpers (module-level so tests can import directly)
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_COLLATERAL_ROOT = os.path.join(_SCRIPT_DIR, 'collateral')


def _api_list_nodes():
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))


def _api_list_lib_types(node):
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    nd = os.path.join(root, node)
    if not os.path.isdir(nd):
        return []
    return sorted(d for d in os.listdir(nd)
                  if os.path.isdir(os.path.join(nd, d)))


def _api_list_corners(node, lib_type):
    from core.collateral import CollateralStore, CollateralError
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    try:
        return CollateralStore(root, node, lib_type).list_corners()
    except CollateralError:
        return []
    except Exception:
        return []


def _api_list_cells(node, lib_type):
    from core.collateral import CollateralStore, CollateralError
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    try:
        return CollateralStore(root, node, lib_type).list_cells()
    except CollateralError:
        return []
    except Exception:
        return []


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

    raw_arcs = [a for a in parsed.get('arcs', []) if a.get('cell') == cell]
    templates_map = parsed.get('templates', {})
    cells_map = parsed.get('cells', {})
    cell_info = cells_map.get(cell, {})

    result = []
    for a in raw_arcs:
        arc_type = a.get('arc_type', '')
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


def _api_rescan(node, lib_type):
    from tools.scan_collateral import build_manifest
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    try:
        build_manifest(root, node, lib_type)
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _api_validate(deckgen_root, mcqc_root, filename, arc_types, max_detail):
    from tools.validate_decks import validate
    try:
        at = arc_types if arc_types else None
        report = validate(
            deckgen_root=deckgen_root,
            mcqc_root=mcqc_root,
            filename=filename or 'nominal_sim.sp',
            arc_types=at,
            max_detail=max_detail or 100,
        )
        return {'ok': True, 'report': report}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


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


# ---------------------------------------------------------------------------
# HTML page (ASCII-only: no em-dashes, no smart quotes, no emojis)
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>deckgen v0.3 - SPICE Deck Generator</title>
<style>
:root {
  --bg:       #fafafa;
  --panel:    #ffffff;
  --text:     #0a0a0a;
  --text-2:   #525252;
  --muted:    #a3a3a3;
  --border:   #e5e5e5;
  --border-2: #d4d4d4;
  --accent:   #171717;
  --accent-h: #404040;
  --green:    #16a34a;
  --yellow:   #ca8a04;
  --red:      #dc2626;
  --blue:     #2563eb;
  --mono: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ---- Topbar ---- */
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 24px;
  height: 48px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 0 rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.topbar-brand {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.topbar-brand h1 {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text);
}
.topbar .ver {
  font-size: 11px;
  color: var(--muted);
  font-weight: 400;
}
.topbar .desc {
  font-size: 12px;
  color: var(--muted);
}
.spacer { flex: 1; }

/* ---- Buttons ---- */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 3px;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--sans);
  cursor: pointer;
  transition: background 0.1s, border-color 0.1s;
  white-space: nowrap;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary {
  background: var(--accent);
  color: #ffffff;
  border: none;
}
.btn-primary:hover:not(:disabled) { background: var(--accent-h); }
.btn-secondary {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border-2);
}
.btn-secondary:hover:not(:disabled) { background: var(--bg); border-color: var(--muted); }
.btn-ghost {
  background: transparent;
  color: var(--text-2);
  border: none;
  padding: 4px 8px;
  font-size: 12px;
}
.btn-ghost:hover:not(:disabled) { background: #f5f5f5; color: var(--text); }

/* ---- Layout ---- */
.main {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.pane-left {
  width: 380px;
  min-width: 260px;
  flex-shrink: 0;
  overflow-y: auto;
  padding: 20px 16px;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pane-right {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 20px 20px 16px;
}

/* ---- Section label ---- */
.sec-label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  padding: 4px 0 6px;
}

/* ---- Cards ---- */
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.card-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}
.card-hd:hover { background: #f5f5f5; }
.card-hd h2 {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-2);
}
.card-hd .tog {
  font-size: 11px;
  color: var(--muted);
  font-weight: 400;
}
.card-bd {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-top: 1px solid var(--border);
}
.card.collapsed .card-bd { display: none; }

/* ---- Fields ---- */
.field { display: flex; flex-direction: column; gap: 4px; }
.field label {
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-2);
}
.field input,
.field select,
.field textarea {
  padding: 6px 10px;
  border: 1px solid var(--border-2);
  border-radius: 3px;
  background: var(--panel);
  color: var(--text);
  font-size: 13px;
  font-family: var(--sans);
  transition: border-color 0.1s;
}
.field input:focus,
.field select:focus,
.field textarea:focus {
  outline: 2px solid rgba(23,23,23,0.12);
  outline-offset: 0;
  border-color: var(--accent);
}
.field input:disabled,
.field select:disabled,
.field textarea:disabled { opacity: 0.5; cursor: not-allowed; }
.field textarea {
  resize: vertical;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
}
.field .mono { font-family: var(--mono); font-size: 12px; }
.frow { display: flex; gap: 8px; }
.frow .field { flex: 1; }
.brow { display: flex; gap: 6px; align-items: flex-end; }
.brow .field { flex: 1; }
.browse-btn {
  padding: 6px 10px;
  background: var(--panel);
  border: 1px solid var(--border-2);
  border-radius: 3px;
  font-size: 12px;
  font-family: var(--sans);
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  color: var(--text-2);
}
.browse-btn:hover { background: var(--bg); border-color: var(--muted); }
.st { font-size: 11px; color: var(--muted); }
.st-ok  { color: var(--green); }
.st-err { color: var(--red); }
.st-muted { color: var(--muted); }
.note { font-size: 12px; color: var(--muted); }

/* ---- Collateral panel ---- */
.col-panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.col-panel-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--panel);
}
.col-panel-hd strong {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-2);
}
#col-status {
  font-size: 11px;
  color: var(--muted);
  flex: 1;
}
.col-panel-bd {
  padding: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.col-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.col-actions { display: flex; gap: 6px; flex-wrap: wrap; }
#col-results {
  display: none;
  margin-top: 4px;
  background: #0a0a0a;
  color: #e5e5e5;
  padding: 10px 12px;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.5;
  max-height: 180px;
  overflow: auto;
}

/* ---- Table ---- */
.tbl-wrap {
  flex: 2;
  min-height: 0;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel);
  margin-bottom: 12px;
}
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th {
  position: sticky;
  top: 0;
  background: var(--bg);
  padding: 8px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-2);
  border-bottom: 1px solid var(--border);
  z-index: 1;
  white-space: nowrap;
}
tbody tr { border-bottom: 1px solid #f5f5f5; cursor: pointer; }
tbody tr:hover { background: var(--bg); }
tbody tr.sel { background: #f5f5f5; }
tbody td { padding: 8px 12px; vertical-align: middle; }
.s-ok  {
  color: var(--green);
  background: rgba(22,163,74,0.08);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  display: inline-block;
}
.s-err {
  color: var(--red);
  background: rgba(220,38,38,0.08);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  display: inline-block;
}
.s-pen {
  color: var(--muted);
  background: rgba(163,163,163,0.12);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  display: inline-block;
}
.s-run { color: var(--blue); }
.td-clip { max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ---- Log ---- */
.log {
  flex-shrink: 0;
  height: 88px;
  overflow-y: auto;
  background: #0a0a0a;
  color: #737373;
  border-radius: 4px;
  padding: 8px 12px;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.5;
  margin-bottom: 12px;
}
.lok  { color: #4ade80; }
.lerr { color: #f87171; }
.lwrn { color: #fbbf24; }
.linf { color: #60a5fa; }

/* ---- SPICE preview ---- */
.sp-wrap {
  flex: 3;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.sp-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 6px;
  flex-shrink: 0;
}
.sp-hd span {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.copy-btn {
  padding: 3px 10px;
  background: #1a1a1a;
  color: #737373;
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  font-size: 11px;
  font-family: var(--sans);
  cursor: pointer;
}
.copy-btn:hover { background: #262626; color: #e5e5e5; }
.copy-btn.copied { background: #14532d; color: #bbf7d0; border-color: #14532d; }
.sp-pre {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: #0a0a0a;
  color: #e5e5e5;
  padding: 12px 16px;
  border-radius: 4px;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre;
}
.sp-empty { color: #525252; font-style: italic; }

/* ---- Spinner ---- */
.spin {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 2px solid rgba(255,255,255,0.25);
  border-top-color: #fff;
  border-radius: 50%;
  animation: rot 0.5s linear infinite;
  vertical-align: middle;
}
@keyframes rot { to { transform: rotate(360deg); } }

/* ---- Scrollbars (webkit) ---- */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d4d4d4; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #a3a3a3; }
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-brand">
    <h1>DeckGen</h1>
    <span class="ver">v0.3</span>
  </div>
  <span class="desc">SPICE Deck Generator -- delay / slew / hold</span>
  <div class="spacer"></div>
  <button class="btn btn-secondary" onclick="clearAll()">Clear</button>
  <button class="btn btn-secondary" id="btn-prev" onclick="doPreview()">Preview</button>
  <button class="btn btn-primary"   id="btn-run"  onclick="doRun()">Run Batch</button>
</div>

<div class="main">

  <!-- Left pane -->
  <div class="pane-left">

    <div class="sec-label">Collateral</div>
    <div id="collateral-panel" class="col-panel">
      <div class="col-panel-hd">
        <strong>Collateral Mode</strong>
        <span id="col-status"></span>
        <button type="button" class="btn btn-ghost" onclick="togglecol()">toggle</button>
      </div>
      <div id="col-body" class="col-panel-bd" style="display:none;">
        <div class="col-grid">
          <div class="field">
            <label>Node</label>
            <select id="col-node"></select>
          </div>
          <div class="field">
            <label>Library Type</label>
            <select id="col-lib"></select>
          </div>
        </div>
        <div class="field">
          <label>Corners (multi-select)</label>
          <select id="col-corners" multiple size="4"></select>
        </div>
        <div class="field">
          <label>Cell (for Single Arc)</label>
          <input type="text" id="col-cell" placeholder="DFFQ1">
        </div>
        <div class="col-actions">
          <button type="button" class="btn btn-secondary" onclick="colRescan()">Rescan</button>
          <button type="button" class="btn btn-secondary" onclick="colFillArcs()">Populate Arcs+Corners</button>
          <button type="button" class="btn btn-secondary" onclick="colPreviewV2()">Preview v2</button>
          <button type="button" class="btn btn-primary"   onclick="colGenerateV2()">Generate v2</button>
        </div>
        <pre id="col-results"></pre>
      </div>
    </div>

    <div class="sec-label" style="margin-top:8px;">Validation</div>
    <div class="card collapsed" id="val-card">
      <div class="card-hd" onclick="tog(this)"><h2>Deck Validation (DeckGen vs MCQC)</h2><span class="tog">[expand]</span></div>
      <div class="card-bd">
        <p class="note">Compare a DeckGen output tree against MCQC output to check parity.</p>
        <div class="field">
          <label>DeckGen output root</label>
          <input class="mono" type="text" id="val-dg" placeholder="/path/to/deckgen/lib/corner">
        </div>
        <div class="field">
          <label>MCQC output root</label>
          <input class="mono" type="text" id="val-mq" placeholder="/path/to/mcqc/root">
        </div>
        <div class="frow">
          <div class="field">
            <label>File</label>
            <select id="val-file">
              <option value="nominal_sim.sp">nominal_sim.sp</option>
              <option value="mc_sim.sp">mc_sim.sp</option>
            </select>
          </div>
          <div class="field">
            <label>Arc types (optional)</label>
            <input type="text" id="val-at" placeholder="delay hold mpw (blank=all)">
          </div>
        </div>
        <div style="display:flex;gap:6px;align-items:center;">
          <button class="btn btn-primary" id="btn-val" onclick="doValidate()">Run Validation</button>
          <a id="val-report-link" href="#" target="_blank" style="display:none;font-size:12px;">Open Report</a>
        </div>
        <pre id="val-results" style="display:none;background:#0a0a0a;color:#e5e5e5;padding:10px 12px;border-radius:3px;font-family:var(--mono);font-size:11px;line-height:1.5;max-height:200px;overflow:auto;"></pre>
      </div>
    </div>

    <div class="sec-label" style="margin-top:8px;">Inputs</div>

    <div class="card">
      <div class="card-hd" onclick="tog(this)"><h2>Targets (arc identifiers)</h2><span class="tog">[collapse]</span></div>
      <div class="card-bd">
        <div class="field">
          <label>One cell_arc_pt ID per line</label>
          <textarea id="ta-arcs" rows="5"
            placeholder="combinational_ND2MDLIMZD0P7BWP130HPNPN3P48CPD_ZN_rise_A1_fall_NO_CONDITION_4_4&#10;hold_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2"
            oninput="dArc()"></textarea>
          <div class="st" id="st-arcs"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-hd" onclick="tog(this)"><h2>Corners</h2><span class="tog">[collapse]</span></div>
      <div class="card-bd">
        <div class="field">
          <label>One per line or comma-separated</label>
          <textarea id="ta-corners" rows="3"
            placeholder="ssgnp_0p450v_m40c&#10;ttgnp_0p800v_25c"
            oninput="dCorn()"></textarea>
          <div class="st" id="st-corners"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-hd" onclick="tog(this)"><h2>Files</h2><span class="tog">[collapse]</span></div>
      <div class="card-bd">
        <div class="brow">
          <div class="field"><label>Netlist directory</label><input class="mono" type="text" id="f-nd" placeholder="/path/to/netlists/"></div>
          <input type="file" id="pk-nd" webkitdirectory style="display:none" onchange="fromPick('f-nd',this)">
          <button class="browse-btn" onclick="document.getElementById('pk-nd').click()">Browse</button>
        </div>
        <div class="brow">
          <div class="field"><label>Model file</label><input class="mono" type="text" id="f-model" placeholder="/path/to/model.spi"></div>
          <input type="file" id="pk-model" style="display:none" onchange="fromPick('f-model',this)">
          <button class="browse-btn" onclick="document.getElementById('pk-model').click()">Browse</button>
        </div>
        <div class="brow">
          <div class="field"><label>Waveform file</label><input class="mono" type="text" id="f-wv" placeholder="/path/to/waveform.spi"></div>
          <input type="file" id="pk-wv" style="display:none" onchange="fromPick('f-wv',this)">
          <button class="browse-btn" onclick="document.getElementById('pk-wv').click()">Browse</button>
        </div>
        <div class="brow">
          <div class="field"><label>Template.tcl dir (optional)</label><input class="mono" type="text" id="f-tcl" placeholder="/path/to/tcl/ (optional)"></div>
          <input type="file" id="pk-tcl" webkitdirectory style="display:none" onchange="fromPick('f-tcl',this)">
          <button class="browse-btn" onclick="document.getElementById('pk-tcl').click()">Browse</button>
        </div>
        <div class="field"><label>Output directory</label><input class="mono" type="text" id="f-out" value="./output"></div>
      </div>
    </div>

    <div class="card collapsed">
      <div class="card-hd" onclick="tog(this)"><h2>Overrides</h2><span class="tog">[expand]</span></div>
      <div class="card-bd">
        <div class="frow">
          <div class="field"><label>VDD</label><input type="text" id="ov-vdd" placeholder="auto from corner"></div>
          <div class="field"><label>Temp</label><input type="text" id="ov-temp" placeholder="auto from corner"></div>
        </div>
        <div class="frow">
          <div class="field"><label>Slew</label><input type="text" id="ov-slew" placeholder="auto from tcl"></div>
          <div class="field"><label>Load</label><input type="text" id="ov-load" placeholder="auto from tcl"></div>
          <div class="field"><label>Max slew</label><input type="text" id="ov-mslew" placeholder="auto"></div>
        </div>
        <div class="frow">
          <div class="field"><label>MC samples</label><input type="number" id="ov-samp" value="5000" min="1"></div>
          <div class="field" style="justify-content:flex-end;align-items:flex-end;">
            <label style="display:flex;align-items:center;gap:6px;cursor:pointer;text-transform:none;font-weight:400;font-size:13px;color:var(--text-2);">
              <input type="checkbox" id="ov-nom"> Nominal only
            </label>
          </div>
        </div>
      </div>
    </div>

    <div class="card collapsed">
      <div class="card-hd" onclick="tog(this)"><h2>Single Mode (manual fields)</h2><span class="tog">[expand]</span></div>
      <div class="card-bd">
        <p class="note">No identifier? Fill these fields to add a synthetic entry to Targets.</p>
        <div class="frow">
          <div class="field"><label>Cell</label><input type="text" id="sm-cell" placeholder="e.g. DFFQ1"></div>
          <div class="field"><label>Arc type</label>
            <select id="sm-at"><option value="hold">hold</option><option value="delay">delay</option><option value="slew">slew</option></select>
          </div>
        </div>
        <div class="frow">
          <div class="field"><label>Related pin</label><input type="text" id="sm-rp" placeholder="CP"></div>
          <div class="field"><label>Rel dir</label>
            <select id="sm-rd"><option value="rise">rise</option><option value="fall">fall</option></select>
          </div>
        </div>
        <div class="frow">
          <div class="field"><label>Probe pin</label><input type="text" id="sm-pp" placeholder="Q"></div>
          <div class="field"><label>When</label><input type="text" id="sm-when" value="NO_CONDITION"></div>
        </div>
        <div style="display:flex;justify-content:flex-end;">
          <button class="btn btn-secondary" onclick="addSingle()">Add to Targets</button>
        </div>
      </div>
    </div>

  </div><!-- end pane-left -->

  <!-- Right pane -->
  <div class="pane-right">

    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th style="width:28px;"><input type="checkbox" id="chk-all" onchange="chkAll(this)"></th>
            <th>#</th><th>Cell</th><th>Arc</th><th>Corner</th><th>Template</th>
            <th>Slew</th><th>Load</th><th>Status</th>
          </tr>
        </thead>
        <tbody id="tbody">
          <tr><td colspan="9" style="text-align:center;padding:20px;color:var(--muted);font-style:italic;font-size:13px;">Click Preview or Run Batch to populate.</td></tr>
        </tbody>
      </table>
    </div>

    <div class="log" id="log">
      <span class="linf">Ready. Enter identifiers and corners, then click Preview or Run Batch.</span>
    </div>

    <div class="sp-wrap">
      <div class="sp-hd">
        <span>SPICE Preview</span>
        <button class="copy-btn" id="copy-btn" onclick="copySpice(this)">Copy</button>
      </div>
      <pre class="sp-pre" id="sp-pre"><span class="sp-empty">Select a row to preview its deck.</span></pre>
    </div>

  </div><!-- end pane-right -->
</div>

<script>
'use strict';
var SKEY = 'deckgen_v3';

// Card toggle
function tog(hd) {
  var card = hd.parentElement;
  card.classList.toggle('collapsed');
  hd.querySelector('.tog').textContent = card.classList.contains('collapsed') ? '[expand]' : '[collapse]';
}

// File picker (browser can't expose full path; show what we get)
function fromPick(id, inp) {
  if (!inp.files || !inp.files.length) return;
  var f = inp.files[0];
  var p = f.webkitRelativePath || f.name || '';
  document.getElementById(id).value = p;
}

// Debounced live parse
var arcT = null, cornT = null;
function dArc()  { clearTimeout(arcT);  arcT  = setTimeout(parseArcs,  300); }
function dCorn() { clearTimeout(cornT); cornT = setTimeout(parseCorners,300); }

async function parseArcs() {
  var text = document.getElementById('ta-arcs').value;
  var st = document.getElementById('st-arcs');
  if (!text.trim()) { st.textContent = ''; return; }
  try {
    var r = await pj('/api/parse_arcs', {text: text});
    var ok = (r.arcs||[]).length, bad = (r.errors||[]).length;
    st.textContent = ok + ' valid' + (bad ? ', ' + bad + ' invalid' : '');
    st.className = 'st ' + (bad ? 'st-err' : 'st-ok');
  } catch(e) { st.textContent = ''; }
}

async function parseCorners() {
  var text = document.getElementById('ta-corners').value;
  var st = document.getElementById('st-corners');
  if (!text.trim()) { st.textContent = ''; return; }
  try {
    var r = await pj('/api/parse_corners', {text: text});
    var ok = (r.corners||[]).length, bad = (r.errors||[]).length;
    st.textContent = ok + ' valid' + (bad ? ', ' + bad + ' invalid' : '');
    st.className = 'st ' + (bad ? 'st-err' : 'st-ok');
  } catch(e) { st.textContent = ''; }
}

// Collect form state into payload
function payload() {
  var arcIds = document.getElementById('ta-arcs').value
    .split('\n').map(function(s){return s.trim();}).filter(Boolean);
  var cornText = document.getElementById('ta-corners').value;
  var cornNames = cornText.split(/[\n,;]+/).map(function(s){return s.trim();}).filter(Boolean);
  var ov = {};
  var vdd = v('ov-vdd'), temp = v('ov-temp'), slew = v('ov-slew'),
      load = v('ov-load'), ms = v('ov-mslew');
  if (vdd) ov.vdd = vdd;
  if (temp) ov.temperature = temp;
  if (slew) ov.slew = slew;
  if (load) ov.load = load;
  if (ms)   ov.max_slew = ms;
  return {
    arc_ids:         arcIds,
    corner_names:    cornNames,
    netlist_dir:     v('f-nd'),
    model:           v('f-model'),
    waveform:        v('f-wv'),
    template_tcl_dir: v('f-tcl'),
    output_dir:      v('f-out') || './output',
    overrides:       ov,
    num_samples:     parseInt(document.getElementById('ov-samp').value)||5000,
    nominal_only:    document.getElementById('ov-nom').checked,
  };
}
function v(id) { var el=document.getElementById(id); return el ? el.value.trim() : ''; }

// Preview
async function doPreview() {
  var p = payload();
  if (!p.arc_ids.length)    { addLog('wrn','No arc identifiers.'); return; }
  if (!p.corner_names.length){ addLog('wrn','No corners.'); return; }
  setBusy('btn-prev', true, 'Previewing...');
  addLog('inf','Resolving ' + p.arc_ids.length + ' arc(s) x ' + p.corner_names.length + ' corner(s)...');
  clearTbl();
  try {
    var r = await pj('/api/preview_batch', p);
    (r.errors||[]).forEach(function(e){ addLog('err',e); });
    fillTbl(r.jobs||[], false);
    addLog('ok','Preview: ' + (r.jobs||[]).length + ' job(s) resolved.');
    save();
  } catch(e) {
    addLog('err','Preview failed: ' + e.message);
  } finally {
    setBusy('btn-prev', false, 'Preview');
  }
}

// Run batch
async function doRun() {
  var p = payload();
  if (!p.arc_ids.length)    { addLog('wrn','No arc identifiers.'); return; }
  if (!p.corner_names.length){ addLog('wrn','No corners.'); return; }
  setBusy('btn-run', true, 'Running...');
  addLog('inf','Batch: ' + p.arc_ids.length + ' arc(s) x ' + p.corner_names.length + ' corner(s)');
  clearTbl();

  // Phase 1: preview to show jobs
  try {
    var prev = await pj('/api/preview_batch', p);
    (prev.errors||[]).forEach(function(e){ addLog('err',e); });
    fillTbl(prev.jobs||[], true);
  } catch(e) {
    addLog('err','Resolution failed: ' + e.message);
    setBusy('btn-run', false, 'Run Batch');
    return;
  }

  // Phase 2: generate, stream results
  var selIds = getSelIds();
  var rp = Object.assign({}, p, {selected_ids: selIds.length ? selIds : null});
  try {
    var resp = await fetch('/api/generate_batch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(rp)
    });
    var reader = resp.body.getReader();
    var dec = new TextDecoder();
    var buf = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += dec.decode(chunk.value, {stream: true});
      var lines = buf.split('\n');
      buf = lines.pop();
      lines.forEach(function(ln) {
        ln = ln.trim();
        if (!ln) return;
        try {
          var res = JSON.parse(ln);
          updRow(res);
          if (res.success) addLog('ok','[' + res.id + '] ' + (res.nominal||''));
          else             addLog('err','[' + res.id + '] ' + (res.error||'failed'));
        } catch(pe) {}
      });
    }
    addLog('ok','Batch complete.');
    save();
  } catch(e) {
    addLog('err','Run failed: ' + e.message);
  } finally {
    setBusy('btn-run', false, 'Run Batch');
  }
}

// Table helpers
function clearTbl() {
  document.getElementById('tbody').innerHTML =
    '<tr><td colspan="9" style="text-align:center;padding:14px;color:#94a3b8;font-style:italic;">Loading...</td></tr>';
  document.getElementById('sp-pre').innerHTML = '<span class="sp-empty">Select a row to preview its deck.</span>';
}

function fillTbl(jobs, pending) {
  var tb = document.getElementById('tbody');
  if (!jobs.length) {
    tb.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:14px;color:#94a3b8;font-style:italic;">No jobs resolved.</td></tr>';
    return;
  }
  tb.innerHTML = '';
  jobs.forEach(function(job) {
    var tr = document.createElement('tr');
    tr.id = 'row-' + job.id;
    tr.dataset.jobId = job.id;
    tr.dataset.job   = JSON.stringify(job);
    tr.onclick = function() { selRow(tr, job); };
    var sc = job.error ? 's-err' : (pending ? 's-pen' : 's-ok');
    var st = job.error ? 'error' : (pending ? 'pending' : 'ready');
    var arc = (job.probe_pin||'') + ' ' + (job.probe_dir||'') + ' / ' + (job.rel_pin||'') + ' ' + (job.rel_dir||'');
    var tpl = job.template ? job.template.split('/').pop() : '--';
    tr.innerHTML =
      '<td><input type="checkbox" class="rchk" checked onclick="rChk(event)"></td>' +
      '<td>' + job.id + '</td>' +
      '<td class="td-clip" title="' + esc(job.cell||'') + '">' + esc(job.cell||'') + '</td>' +
      '<td class="td-clip" title="' + esc(arc) + '">' + esc(arc) + '</td>' +
      '<td>' + esc(job.corner||'') + '</td>' +
      '<td class="td-clip" title="' + esc(job.template||'') + '">' + esc(tpl) + '</td>' +
      '<td>' + (job.rel_slew||'--') + '</td>' +
      '<td>' + (job.output_load||'--') + '</td>' +
      '<td class="' + sc + '">' + st + '</td>';
    tb.appendChild(tr);
  });
}

function updRow(result) {
  var tr = document.getElementById('row-' + result.id);
  if (!tr) return;
  var cells = tr.querySelectorAll('td');
  var sc = cells[cells.length-1];
  if (result.success) {
    sc.textContent = 'ok'; sc.className = 's-ok';
    tr.dataset.nominal = result.nominal || '';
    tr.dataset.mc      = result.mc || '';
  } else {
    sc.textContent = 'fail'; sc.className = 's-err';
    tr.dataset.error = result.error || '';
  }
}

function selRow(tr, job) {
  document.querySelectorAll('#tbody tr').forEach(function(r){r.classList.remove('sel');});
  tr.classList.add('sel');
  showPreview(job);
}

async function showPreview(job) {
  document.getElementById('sp-pre').textContent = 'Loading...';
  try {
    var r = await pj('/api/preview_one', {job: job});
    if (r.success) document.getElementById('sp-pre').textContent = r.deck;
    else           document.getElementById('sp-pre').textContent = 'Error: ' + r.error;
  } catch(e) {
    document.getElementById('sp-pre').textContent = 'Error: ' + e.message;
  }
}

function getSelIds() {
  return Array.from(document.querySelectorAll('.rchk:checked'))
    .map(function(c){ return parseInt(c.closest('tr').dataset.jobId); })
    .filter(Boolean);
}
function chkAll(chk) { document.querySelectorAll('.rchk').forEach(function(c){c.checked=chk.checked;}); }
function rChk(e) {
  e.stopPropagation();
  var all = document.querySelectorAll('.rchk').length;
  var chk = document.querySelectorAll('.rchk:checked').length;
  var ca = document.getElementById('chk-all');
  ca.indeterminate = chk > 0 && chk < all;
  ca.checked = chk === all;
}

// Single mode -> add to targets
function addSingle() {
  var cell = v('sm-cell');
  if (!cell) { addLog('wrn','Cell required in Single Mode.'); return; }
  var at   = document.getElementById('sm-at').value;
  var rp   = v('sm-rp') || 'CP';
  var rd   = document.getElementById('sm-rd').value;
  var pp   = v('sm-pp') || 'Q';
  var when = v('sm-when') || 'NO_CONDITION';
  var id = at + '_' + cell + '_' + pp + '_rise_' + rp + '_' + rd + '_' + when.replace(/!/g,'not').replace(/&/g,'_') + '_1_1';
  var ta = document.getElementById('ta-arcs');
  ta.value = ta.value ? ta.value.trimEnd() + '\n' + id : id;
  dArc();
  addLog('inf','Added: ' + id);
}

// Helpers
function setBusy(id, busy, lbl) {
  var btn = document.getElementById(id);
  btn.disabled = busy;
  btn.innerHTML = busy ? '<span class="spin"></span>' + lbl : lbl;
}

function addLog(kind, msg) {
  var log = document.getElementById('log');
  var sp = document.createElement('span');
  var cls = {ok:'lok', err:'lerr', wrn:'lwrn', inf:'linf'}[kind] || '';
  sp.className = cls; sp.textContent = msg;
  log.appendChild(document.createTextNode('\n'));
  log.appendChild(sp);
  log.scrollTop = log.scrollHeight;
}

function clearAll() {
  document.getElementById('ta-arcs').value = '';
  document.getElementById('ta-corners').value = '';
  document.getElementById('st-arcs').textContent = '';
  document.getElementById('st-corners').textContent = '';
  clearTbl();
  document.getElementById('log').innerHTML = '<span class="linf">Cleared.</span>';
}

function copySpice(btn) {
  var text = document.getElementById('sp-pre').textContent;
  navigator.clipboard.writeText(text).then(function() {
    btn.className = 'copy-btn copied'; btn.textContent = 'Copied!';
    setTimeout(function(){ btn.className = 'copy-btn'; btn.textContent = 'Copy'; }, 1400);
  });
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function pj(url, body) {
  var r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

// Persistence
function save() {
  try {
    localStorage.setItem(SKEY, JSON.stringify({
      arcs:    document.getElementById('ta-arcs').value,
      corners: document.getElementById('ta-corners').value,
      nd:      v('f-nd'), model: v('f-model'), wv: v('f-wv'),
      tcl:     v('f-tcl'), out: v('f-out')
    }));
  } catch(e) {}
}

window.addEventListener('load', function() {
  try {
    var s = JSON.parse(localStorage.getItem(SKEY)||'{}');
    if (s.arcs)    document.getElementById('ta-arcs').value    = s.arcs;
    if (s.corners) document.getElementById('ta-corners').value = s.corners;
    if (s.nd)    document.getElementById('f-nd').value    = s.nd;
    if (s.model) document.getElementById('f-model').value = s.model;
    if (s.wv)    document.getElementById('f-wv').value    = s.wv;
    if (s.tcl)   document.getElementById('f-tcl').value   = s.tcl;
    if (s.out)   document.getElementById('f-out').value   = s.out;
    if (s.arcs)    dArc();
    if (s.corners) dCorn();
  } catch(e) {}
});

// ---------------------------------------------------------------------------
// Collateral Mode panel
// ---------------------------------------------------------------------------

async function pjv2(path, body) {
  var r = await fetch(path, {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {})});
  return r.json();
}

async function colRefreshNodes() {
  var r = await pjv2('/api/nodes', {});
  var sel = document.getElementById('col-node');
  sel.innerHTML = '';
  (r.nodes || []).forEach(function(n) {
    var o = document.createElement('option');
    o.value = o.textContent = n;
    sel.appendChild(o);
  });
  if ((r.nodes || []).length) {
    sel.value = r.nodes[0];
    colRefreshLibs();
  }
}

async function colRefreshLibs() {
  var node = document.getElementById('col-node').value;
  var r = await pjv2('/api/lib_types', {node: node});
  var sel = document.getElementById('col-lib');
  sel.innerHTML = '';
  (r.lib_types || []).forEach(function(l) {
    var o = document.createElement('option');
    o.value = o.textContent = l;
    sel.appendChild(o);
  });
  if ((r.lib_types || []).length) {
    sel.value = r.lib_types[0];
    colRefreshCorners();
  }
}

async function colRefreshCorners() {
  var node = document.getElementById('col-node').value;
  var lib  = document.getElementById('col-lib').value;
  var rc = await pjv2('/api/corners', {node: node, lib_type: lib});
  var rk = await pjv2('/api/cells',   {node: node, lib_type: lib});
  var sel = document.getElementById('col-corners');
  sel.innerHTML = '';
  (rc.corners || []).forEach(function(c) {
    var o = document.createElement('option');
    o.value = o.textContent = c;
    sel.appendChild(o);
  });
  document.getElementById('col-status').textContent =
    (rc.corners || []).length + ' corners / ' + (rk.cells || []).length + ' cells';
}

async function colRescan() {
  var node = document.getElementById('col-node').value;
  var lib  = document.getElementById('col-lib').value;
  document.getElementById('col-status').textContent = 'Rescanning...';
  var r = await pjv2('/api/rescan', {node: node, lib_type: lib});
  document.getElementById('col-status').textContent =
    r.ok ? 'Rescan complete' : ('Rescan failed: ' + (r.error || ''));
  colRefreshCorners();
}

function colFillArcs() {
  var selected = Array.from(document.getElementById('col-corners').selectedOptions)
    .map(function(o){return o.value;});
  var cornerArea = document.getElementById('ta-corners') ||
                   document.querySelector('textarea[name="corners"]');
  if (cornerArea) cornerArea.value = selected.join('\n');
  document.getElementById('col-status').textContent =
    'Populated ' + selected.length + ' corners';
}

async function colPreviewV2() {
  var body = collectCollateralBody();
  document.getElementById('col-results').style.display = 'block';
  document.getElementById('col-results').textContent = 'Previewing...';
  var r = await pjv2('/api/preview_v2', body);
  document.getElementById('col-results').textContent = JSON.stringify(r, null, 2);
}

async function colGenerateV2() {
  var body = collectCollateralBody();
  document.getElementById('col-results').style.display = 'block';
  document.getElementById('col-results').textContent = 'Generating...';
  var r = await pjv2('/api/generate_v2', body);
  document.getElementById('col-results').textContent = JSON.stringify(r, null, 2);
}

function collectCollateralBody() {
  var node = document.getElementById('col-node').value;
  var lib  = document.getElementById('col-lib').value;
  var corners = Array.from(document.getElementById('col-corners').selectedOptions)
    .map(function(o){return o.value;});
  var arcArea = document.getElementById('ta-arcs') ||
                document.querySelector('textarea[name="arcs"]');
  var arc_ids = [];
  if (arcArea) {
    arc_ids = arcArea.value.split('\n').map(function(s){return s.trim();}).filter(Boolean);
  }
  var outputEl = document.getElementById('f-out') ||
                 document.querySelector('input[name="output"]');
  var output = outputEl ? outputEl.value : './output';
  return {
    mode: 'batch', node: node, lib_type: lib,
    corners: corners, arc_ids: arc_ids, output: output,
    cell: document.getElementById('col-cell').value,
  };
}

function togglecol() {
  var b = document.getElementById('col-body');
  b.style.display = (b.style.display === 'none') ? 'block' : 'none';
}

(function(){
  var onReady = function() { colRefreshNodes(); };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
  setTimeout(function(){
    var n = document.getElementById('col-node');
    var l = document.getElementById('col-lib');
    if (n) n.addEventListener('change', colRefreshLibs);
    if (l) l.addEventListener('change', colRefreshCorners);
  }, 100);
})();

// ---------------------------------------------------------------------------
// Validation panel
// ---------------------------------------------------------------------------

async function doValidate() {
  var dg = document.getElementById('val-dg').value.trim();
  var mq = document.getElementById('val-mq').value.trim();
  if (!dg || !mq) { addLog('wrn', 'Set DeckGen and MCQC roots first.'); return; }
  var file = document.getElementById('val-file').value;
  var atRaw = document.getElementById('val-at').value.trim();
  var arcTypes = atRaw ? atRaw.split(/[\s,]+/).filter(Boolean) : [];
  var res = document.getElementById('val-results');
  res.style.display = 'block';
  res.textContent = 'Running validation...';
  document.getElementById('btn-val').disabled = true;
  try {
    var r = await pj('/api/validate', {
      deckgen_root: dg, mcqc_root: mq,
      file: file, arc_types: arcTypes, max_detail: 100
    });
    if (r.ok && r.report) {
      var s = r.report.summary || {};
      var lines = [
        'Total pairs:  ' + s.total,
        'Identical:    ' + s.identical,
        'Different:    ' + s.different,
      ];
      Object.keys(r.report.arc_types || {}).forEach(function(at) {
        var d = r.report.arc_types[at];
        lines.push('');
        lines.push('[' + at + '] pairs=' + d.total_pairs +
          ' L1=' + d.level1_identical +
          ' L2=' + d.level2_identical +
          ' L3=' + d.level3_only_diffs +
          ' orphans_dg=' + (d.orphans_deckgen||[]).length +
          ' orphans_mq=' + (d.orphans_mcqc||[]).length);
      });
      res.textContent = lines.join('\n');
      addLog('ok', 'Validation done: ' + s.total + ' pairs, ' + s.different + ' diffs.');
      // Request HTML report path
      try {
        var hr = await pj('/api/validate_html', {
          deckgen_root: dg, mcqc_root: mq,
          file: file, arc_types: arcTypes, max_detail: 100
        });
        if (hr.html_path) {
          var link = document.getElementById('val-report-link');
          link.href = '/api/validate_html_serve?path=' + encodeURIComponent(hr.html_path);
          link.style.display = '';
        }
      } catch(e) {}
    } else {
      res.textContent = 'Error: ' + (r.error || JSON.stringify(r));
      addLog('err', 'Validation failed: ' + (r.error || ''));
    }
  } catch(e) {
    res.textContent = 'Error: ' + e.message;
    addLog('err', 'Validation error: ' + e.message);
  } finally {
    document.getElementById('btn-val').disabled = false;
  }
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class DeckgenHandler(http.server.BaseHTTPRequestHandler):

    COLLATERAL_ROOT = _DEFAULT_COLLATERAL_ROOT

    def log_message(self, fmt, *args):
        pass  # suppress request logs

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

    def _serve_validate_html(self):
        import urllib.parse
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        path = (params.get('path') or [''])[0]
        if not path or not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return
        try:
            with open(path, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _serve_deck(self):
        """GET /api/deck?path=<path>
        Returns raw SPICE file content as plain text.
        Path must end in .sp or .spi (basic path-traversal guard).
        """
        import urllib.parse
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        rel = (params.get('path') or [''])[0]
        if not rel:
            self.send_response(400)
            self.end_headers()
            return

        path = os.path.abspath(rel) if not os.path.isabs(rel) else rel

        # Extension check FIRST to avoid leaking file existence of non-SPICE paths
        if not path.lower().endswith(('.sp', '.spi')):
            self.send_response(403)
            self.end_headers()
            return

        if not os.path.isfile(path):
            self.send_response(404)
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

    def do_POST(self):
        data = self._read_json()
        path = self.path

        if path == '/api/parse_arcs':
            result = self._handle_parse_arcs(data)
            self._send_json(result)
        elif path == '/api/parse_corners':
            result = self._handle_parse_corners(data)
            self._send_json(result)
        elif path == '/api/preview_batch':
            result = self._handle_preview_batch(data)
            self._send_json(result)
        elif path == '/api/generate_batch':
            self._handle_generate_batch(data)  # streams NDJSON
        elif path == '/api/preview_one':
            result = self._handle_preview_one(data)
            self._send_json(result)
        elif path == '/api/generate':
            result = self._handle_generate(data)
            self._send_json(result)
        elif path == '/api/match':
            result = self._handle_match(data)
            self._send_json(result)
        elif path == '/api/nodes':
            self._send_json({'nodes': _api_list_nodes()}); return
        elif path == '/api/lib_types':
            self._send_json({'lib_types': _api_list_lib_types(data.get('node', ''))}); return
        elif path == '/api/corners':
            self._send_json({'corners': _api_list_corners(
                data.get('node', ''), data.get('lib_type', ''))}); return
        elif path == '/api/cells':
            self._send_json({'cells': _api_list_cells(
                data.get('node', ''), data.get('lib_type', ''))}); return
        elif path == '/api/arcs':
            self._send_json({'arcs': _api_list_arcs(
                data.get('node', ''), data.get('lib_type', ''),
                data.get('cell', ''))}); return
        elif path == '/api/rescan':
            self._send_json(_api_rescan(data.get('node', ''), data.get('lib_type', ''))); return
        elif path == '/api/preview_v2':
            self._handle_preview_v2(data); return
        elif path == '/api/generate_v2':
            self._handle_generate_v2(data); return
        elif path == '/api/validate':
            self._send_json(_api_validate(
                data.get('deckgen_root', ''),
                data.get('mcqc_root', ''),
                data.get('file', 'nominal_sim.sp'),
                data.get('arc_types') or None,
                data.get('max_detail', 100),
            )); return
        elif path == '/api/validate_html':
            self._send_json(self._handle_validate_html(data)); return
        else:
            self.send_response(404)
            self.end_headers()

    def _read_json(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _send_json(self, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------
    # /api/parse_arcs
    # ------------------------------------------------------------------

    def _handle_parse_arcs(self, data):
        text = data.get('text', '')
        arcs = []
        errors = []
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            parsed = parse_arc_identifier(line)
            if parsed:
                arcs.append(parsed)
            else:
                errors.append(f"Line {i}: cannot parse {line!r}")
        return {'arcs': arcs, 'errors': errors}

    # ------------------------------------------------------------------
    # /api/parse_corners
    # ------------------------------------------------------------------

    def _handle_parse_corners(self, data):
        text = data.get('text', '')
        corners = []
        errors = []
        names = [s.strip() for s in text.replace('\n', ',').split(',') if s.strip()]
        for name in names:
            parsed = parse_corner_name(name)
            if parsed:
                corners.append(parsed)
            else:
                errors.append(f"Cannot parse corner {name!r}")
        return {'corners': corners, 'errors': errors}

    # ------------------------------------------------------------------
    # /api/preview_batch
    # ------------------------------------------------------------------

    def _handle_preview_batch(self, data):
        arc_ids = data.get('arc_ids', [])
        corner_names = data.get('corner_names', [])
        files = {
            'netlist_dir':      data.get('netlist_dir', ''),
            'netlist':          data.get('netlist', ''),
            'model':            data.get('model', ''),
            'waveform':         data.get('waveform', ''),
            'template_tcl_dir': data.get('template_tcl_dir', ''),
        }
        overrides = data.get('overrides', {})
        try:
            jobs, errors = plan_jobs(arc_ids, corner_names, files, overrides)
            # Make jobs JSON-serialisable (remove non-serialisable fields if any)
            return {'jobs': jobs, 'errors': errors}
        except Exception as e:
            return {'jobs': [], 'errors': [str(e)]}

    # ------------------------------------------------------------------
    # /api/generate_batch  (streams NDJSON)
    # ------------------------------------------------------------------

    def _handle_generate_batch(self, data):
        arc_ids = data.get('arc_ids', [])
        corner_names = data.get('corner_names', [])
        files = {
            'netlist_dir':      data.get('netlist_dir', ''),
            'netlist':          data.get('netlist', ''),
            'model':            data.get('model', ''),
            'waveform':         data.get('waveform', ''),
            'template_tcl_dir': data.get('template_tcl_dir', ''),
        }
        overrides  = data.get('overrides', {})
        output_dir = data.get('output_dir', './output')
        selected   = data.get('selected_ids')
        nom_only   = data.get('nominal_only', False)
        n_samples  = data.get('num_samples', 5000)

        try:
            jobs, errors = plan_jobs(arc_ids, corner_names, files, overrides)
        except Exception as e:
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.end_headers()
            line = json.dumps({'id': 0, 'success': False, 'error': str(e)}) + '\n'
            self.wfile.write(line.encode('utf-8'))
            return

        if selected is not None:
            sel_set = set(selected)
            jobs_to_run = [j for j in jobs if j['id'] in sel_set]
        else:
            jobs_to_run = jobs

        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.end_headers()

        results = execute_jobs(
            jobs_to_run, output_dir,
            nominal_only=nom_only, num_samples=n_samples, files=files
        )
        for r in results:
            line = json.dumps(r) + '\n'
            try:
                self.wfile.write(line.encode('utf-8'))
                self.wfile.flush()
            except BrokenPipeError:
                break

    # ------------------------------------------------------------------
    # /api/validate_html  (generate HTML report, return its path)
    # ------------------------------------------------------------------

    def _handle_validate_html(self, data):
        from tools.validate_decks import validate, write_reports
        import tempfile
        try:
            at = data.get('arc_types') or None
            report = validate(
                deckgen_root=data.get('deckgen_root', ''),
                mcqc_root=data.get('mcqc_root', ''),
                filename=data.get('file', 'nominal_sim.sp'),
                arc_types=at,
                max_detail=data.get('max_detail', 100),
            )
            out_dir = tempfile.mkdtemp(prefix='deckgen_val_')
            _, html_path = write_reports(report, out_dir)
            return {'ok': True, 'html_path': html_path}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # /api/preview_v2  (collateral-backed preview)
    # ------------------------------------------------------------------

    def _handle_preview_v2(self, data):
        """Preview: plan jobs via collateral, return job summary."""
        try:
            mode = data.get('mode', 'batch')
            if mode == 'single':
                arc_id = self._build_arc_id_single(data)
                arc_ids = [arc_id] if arc_id else []
            else:
                arc_ids = data.get('arc_ids', [])

            jobs, errors = plan_jobs(
                arc_ids=arc_ids,
                corner_names=data.get('corners', []),
                files={},
                node=data.get('node') or None,
                lib_type=data.get('lib_type') or None,
                collateral_root=DeckgenHandler.COLLATERAL_ROOT)
            safe_jobs = []
            for j in jobs:
                safe_jobs.append({
                    k: v for k, v in j.items() if k != 'arc_info'
                })
            self._send_json({'jobs': safe_jobs, 'errors': errors})
        except Exception as e:
            self._send_json({'error': str(e)})

    # ------------------------------------------------------------------
    # /api/generate_v2  (collateral-backed generate)
    # ------------------------------------------------------------------

    def _handle_generate_v2(self, data):
        """Generate: run the batch using collateral-backed planning."""
        from core.batch import run_batch
        try:
            mode = data.get('mode', 'batch')
            # Expand arc_ids using table_points if provided.
            # table_points: {arc_type: "(i1,i2) ..." text}
            # arc_ids may be bare (no _i1_i2 suffix) - we expand them.
            raw_arc_ids = data.get('arc_ids', [])
            table_points = data.get('table_points', {})
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
                data = dict(data)
                data['arc_ids'] = expanded
            if mode == 'single':
                arc_id = self._build_arc_id_single(data)
                arc_ids = [arc_id] if arc_id else []
            else:
                arc_ids = data.get('arc_ids', [])

            jobs, results, errors = run_batch(
                arc_ids=arc_ids,
                corner_names=data.get('corners', []),
                files={},
                output_dir=data.get('output', './output'),
                node=data.get('node') or None,
                lib_type=data.get('lib_type') or None,
                collateral_root=DeckgenHandler.COLLATERAL_ROOT)
            self._send_json({
                'job_count': len(jobs),
                'results': results,
                'errors': errors,
            })
        except Exception as e:
            self._send_json({'error': str(e)})

    @staticmethod
    def _build_arc_id_single(data):
        """Construct a synthetic arc_id from single-mode inputs."""
        at  = data.get('arc_type', 'combinational')
        c   = data.get('cell', '')
        p   = data.get('probe', 'Q')
        pd  = data.get('probe_dir', 'rise')
        rp  = data.get('rel_pin', '')
        rd  = data.get('rel_dir', 'rise')
        if not (c and rp):
            return ''
        return f"{at}_{c}_{p}_{pd}_{rp}_{rd}_NO_CONDITION_1_1"

    # ------------------------------------------------------------------
    # /api/preview_one  (SPICE preview for a single job row)
    # ------------------------------------------------------------------

    def _handle_preview_one(self, data):
        job = data.get('job', {})
        if not job:
            return {'success': False, 'error': 'No job data provided.'}
        try:
            files = {
                'model':    data.get('model', ''),
                'waveform': data.get('waveform', ''),
            }
            arc_info = _job_to_arc_info(job, files)
            slew = (job.get('constr_slew') or '0', job.get('rel_slew') or '0')
            load = job.get('output_load') or '0'
            when = job.get('when', 'NO_CONDITION')
            lines = build_deck(arc_info, slew=slew, load=load, when=when,
                               max_slew=job.get('max_slew'))
            preview = ''.join(lines[:150])
            if len(lines) > 150:
                preview += f"\n... ({len(lines) - 150} more lines)"
            return {'success': True, 'deck': preview}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # /api/generate  (single-arc, kept for backwards compat)
    # ------------------------------------------------------------------

    def _handle_generate(self, data):
        from core.resolver import resolve_all
        from core.deck_builder import build_mc_deck
        from core.writer import write_nominal_and_mc, write_deck, get_deck_dirname
        import os
        try:
            action = data.get('action', 'generate')
            registry_path = os.path.join(SCRIPT_DIR, 'config', 'template_registry.yaml')
            templates_dir = os.path.join(SCRIPT_DIR, 'templates')

            if data.get('arc_type') == 'hold' and not data.get('constr_pin'):
                return {'success': False, 'error': 'Constrained pin required for hold arcs.'}

            cli_overrides = {
                'vdd':         data.get('vdd') or None,
                'temperature': data.get('temp') or None,
                'model_file':  data.get('model') or None,
                'waveform_file': data.get('waveform') or None,
                'pushout_per': '0.4',
                'num_samples': int(data.get('num_samples', 5000) or 5000),
            }
            arc_info = resolve_all(
                cell_name=data['cell'], arc_type=data['arc_type'],
                rel_pin=data['rel_pin'], rel_dir=data['rel_dir'],
                constr_pin=data.get('constr_pin') or data['rel_pin'],
                constr_dir=data.get('constr_dir') or None,
                probe_pin=data.get('probe_pin') or None,
                registry_path=registry_path, templates_dir=templates_dir,
                netlist_dir=None, corner_config=None,
                cli_overrides=cli_overrides,
                template_override=data.get('template') or None,
                netlist_override=data.get('netlist') or None,
                pins_override=data.get('pins') or None,
            )
            cs = data.get('slew') or '0'
            rs = data.get('rel_slew') or data.get('slew') or '0'
            ms = data.get('max_slew') or rs or cs
            nominal_lines = build_deck(arc_info=arc_info, slew=(cs, rs),
                                       load=data.get('load') or '0',
                                       when=data.get('when') or 'NO_CONDITION',
                                       max_slew=ms)
            tpl_used = os.path.relpath(
                arc_info['TEMPLATE_DECK_PATH'], templates_dir
            ) if arc_info.get('TEMPLATE_DECK_PATH') else '(custom)'

            if action == 'preview':
                return {'success': True,
                        'message': f"Preview (not written). Template: {tpl_used}",
                        'deck_preview': ''.join(nominal_lines)}

            nom_only = data.get('nominal_only', False)
            output_dir = data.get('output', './output')
            if nom_only:
                from core.deck_builder import build_mc_deck as _bmc
                dirname = get_deck_dirname(arc_info, data.get('when'))
                out_path = os.path.join(output_dir, dirname, 'nominal_sim.sp')
                write_deck(nominal_lines, out_path)
                msg = f"Nominal deck: {out_path}\nTemplate: {tpl_used}"
            else:
                mc_lines = build_mc_deck(nominal_lines, int(data.get('num_samples',5000) or 5000))
                nom_p, mc_p = write_nominal_and_mc(
                    nominal_lines, mc_lines, output_dir, arc_info, data.get('when'))
                msg = f"Nominal: {nom_p}\nMC:      {mc_p}\nTemplate: {tpl_used}"

            preview = ''.join(nominal_lines[:120])
            if len(nominal_lines) > 120:
                preview += f"\n... ({len(nominal_lines)-120} more lines)"
            return {'success': True, 'message': msg, 'deck_preview': preview}

        except ResolutionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': f"{type(e).__name__}: {e}"}

    # ------------------------------------------------------------------
    # /api/match  (template match check, kept for backwards compat)
    # ------------------------------------------------------------------

    def _handle_match(self, data):
        try:
            registry_path = os.path.join(SCRIPT_DIR, 'config', 'template_registry.yaml')
            templates_dir = os.path.join(SCRIPT_DIR, 'templates')

            if data.get('template'):
                if os.path.exists(data['template']):
                    return {'success': True, 'template': data['template'],
                            'note': 'Custom template override'}
                return {'success': False,
                        'error': f"Custom template not found: {data['template']}"}

            if not data.get('cell') or not data.get('rel_pin'):
                return {'success': False, 'error': 'Cell and Related Pin required.'}

            resolver = TemplateResolver(registry_path, templates_dir)
            path = resolver.resolve(
                cell_name=data['cell'],
                arc_type=data.get('arc_type', 'hold'),
                rel_pin=data['rel_pin'],
                rel_dir=data.get('rel_dir', 'rise'),
                constr_dir=data.get('constr_dir') or None,
            )
            rel = os.path.relpath(path, templates_dir)
            return {'success': True, 'template': rel}
        except ResolutionError as e:
            msg = str(e)
            if e.suggestions:
                msg += '\nClosest matches:\n' + '\n'.join(e.suggestions)
            return {'success': False, 'error': msg}
        except Exception as e:
            return {'success': False, 'error': f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='deckgen GUI v0.3')
    parser.add_argument('--port', type=int, default=8585, help='Port (default: 8585)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    args = parser.parse_args()

    server = http.server.HTTPServer(('127.0.0.1', args.port), DeckgenHandler)
    url = f'http://127.0.0.1:{args.port}'
    print(f"deckgen GUI v0.3 at {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == '__main__':
    main()
