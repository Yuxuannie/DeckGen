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


def _api_rescan(node, lib_type):
    from tools.scan_collateral import build_manifest
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    try:
        build_manifest(root, node, lib_type)
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


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
  --blue:   #2563eb;
  --green:  #10b981;
  --red:    #ef4444;
  --bg:     #f8fafc;
  --panel:  #ffffff;
  --border: #e2e8f0;
  --text:   #0f172a;
  --muted:  #64748b;
  --label:  #475569;
  --mono:   'SF Mono', Menlo, Consolas, 'Courier New', monospace;
  --sans:   -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  --r:      6px;
  --rc:     8px;
  --sh:     0 1px 2px rgba(0,0,0,0.04);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body { font-family: var(--sans); background: var(--bg); color: var(--text); font-size: 13px; display: flex; flex-direction: column; overflow: hidden; }

/* Top bar */
.topbar { display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: var(--panel); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.topbar h1 { font-size: 15px; font-weight: 700; }
.topbar .ver { font-size: 10px; color: var(--muted); margin-right: 4px; }
.topbar .desc { font-size: 11px; color: var(--muted); }
.spacer { flex: 1; }
.btn { padding: 6px 13px; border: none; border-radius: var(--r); font-size: 12px; font-weight: 600; cursor: pointer; transition: background 0.1s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--blue); color: #fff; }
.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-secondary { background: #e2e8f0; color: var(--text); }
.btn-secondary:hover:not(:disabled) { background: #cbd5e1; }

/* Layout */
.main { display: flex; flex: 1; min-height: 0; overflow: hidden; }
.pane-left { width: 400px; min-width: 280px; flex-shrink: 0; overflow-y: auto; padding: 12px; border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 9px; }
.pane-right { flex: 1; min-width: 0; overflow: hidden; display: flex; flex-direction: column; gap: 9px; padding: 12px; }

/* Cards */
.card { background: var(--panel); border: 1px solid var(--border); border-radius: var(--rc); box-shadow: var(--sh); overflow: hidden; }
.card-hd { display: flex; align-items: center; justify-content: space-between; padding: 7px 11px; cursor: pointer; user-select: none; background: #f8fafc; }
.card-hd:hover { background: #f1f5f9; }
.card-hd h2 { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--label); }
.card-hd .tog { font-size: 10px; color: var(--muted); }
.card-bd { padding: 11px; display: flex; flex-direction: column; gap: 8px; }
.card.collapsed .card-bd { display: none; }

/* Fields */
.field { display: flex; flex-direction: column; gap: 3px; }
.field label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; color: var(--label); }
.field input, .field select, .field textarea {
  padding: 5px 8px; border: 1px solid var(--border); border-radius: var(--r);
  font-size: 12px; font-family: var(--sans); background: var(--panel); color: var(--text);
  transition: border-color 0.1s, box-shadow 0.1s;
}
.field input:focus, .field select:focus, .field textarea:focus {
  outline: none; border-color: var(--blue); box-shadow: 0 0 0 2px rgba(37,99,235,0.12);
}
.field textarea { resize: vertical; font-family: var(--mono); font-size: 11px; line-height: 1.5; }
.field .mono { font-family: var(--mono); font-size: 11px; }
.frow { display: flex; gap: 7px; }
.frow .field { flex: 1; }
.brow { display: flex; gap: 6px; align-items: flex-end; }
.brow .field { flex: 1; }
.browse-btn { padding: 5px 9px; background: #f1f5f9; border: 1px solid var(--border); border-radius: var(--r); font-size: 11px; cursor: pointer; white-space: nowrap; flex-shrink: 0; }
.browse-btn:hover { background: #e2e8f0; }
.st { font-size: 10px; margin-top: 2px; }
.st-ok { color: var(--green); }
.st-err { color: var(--red); }
.st-muted { color: var(--muted); }

/* Note text */
.note { font-size: 11px; color: var(--muted); }

/* Table */
.tbl-wrap { flex: 2; min-height: 0; overflow-y: auto; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel); }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
thead th { position: sticky; top: 0; background: #f8fafc; padding: 5px 8px; text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--label); border-bottom: 1px solid var(--border); z-index: 1; white-space: nowrap; }
tbody tr { border-bottom: 1px solid #f1f5f9; cursor: pointer; }
tbody tr:hover { background: #f8fafc; }
tbody tr.sel { background: #eff6ff; }
tbody td { padding: 5px 8px; vertical-align: middle; }
.s-ok  { color: var(--green); font-weight: 600; }
.s-err { color: var(--red);   font-weight: 600; }
.s-pen { color: var(--muted); }
.s-run { color: var(--blue);  }
.td-clip { max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Log */
.log { flex-shrink: 0; height: 100px; overflow-y: auto; background: #0f172a; color: #94a3b8; border-radius: var(--r); padding: 7px 10px; font-family: var(--mono); font-size: 11px; line-height: 1.5; }
.lok  { color: #34d399; }
.lerr { color: #f87171; }
.lwrn { color: #fbbf24; }
.linf { color: #60a5fa; }

/* SPICE preview */
.sp-wrap { flex: 3; min-height: 0; display: flex; flex-direction: column; }
.sp-hd { display: flex; align-items: center; justify-content: space-between; padding: 2px 0 5px; flex-shrink: 0; }
.sp-hd span { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; color: var(--label); }
.copy-btn { padding: 3px 8px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 4px; font-size: 10px; cursor: pointer; }
.copy-btn:hover { background: #334155; color: #e2e8f0; }
.copy-btn.copied { background: #065f46; color: #a7f3d0; border-color: #065f46; }
.sp-pre { flex: 1; min-height: 0; overflow-y: auto; background: #0f172a; color: #e2e8f0; padding: 9px 11px; border-radius: var(--r); font-family: var(--mono); font-size: 11px; line-height: 1.5; white-space: pre; }
.sp-empty { color: #475569; font-style: italic; }

/* Spinner */
.spin { display: inline-block; width: 11px; height: 11px; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; border-radius: 50%; animation: rot 0.5s linear infinite; vertical-align: middle; margin-right: 4px; }
@keyframes rot { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="topbar">
  <h1>deckgen</h1>
  <span class="ver">v0.3</span>
  <span class="desc">SPICE Deck Generator -- delay / slew / hold</span>
  <div class="spacer"></div>
  <button class="btn btn-secondary" onclick="clearAll()">Clear</button>
  <button class="btn btn-secondary" id="btn-prev" onclick="doPreview()">Preview</button>
  <button class="btn btn-primary"   id="btn-run"  onclick="doRun()">Run Batch</button>
</div>

<div class="main">

  <!-- Left pane -->
  <div class="pane-left">

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
            <label style="display:flex;align-items:center;gap:5px;cursor:pointer;text-transform:none;font-weight:normal;font-size:12px;">
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
          <button class="btn btn-secondary" style="font-size:11px;padding:5px 10px;" onclick="addSingle()">Add to Targets</button>
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
          <tr><td colspan="9" style="text-align:center;padding:18px;color:#94a3b8;font-style:italic;">Click Preview or Run Batch to populate.</td></tr>
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
            body = HTML_PAGE.encode('ascii')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
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
        elif path == '/api/rescan':
            self._send_json(_api_rescan(data.get('node', ''), data.get('lib_type', ''))); return
        elif path == '/api/preview_v2':
            self._handle_preview_v2(data); return
        elif path == '/api/generate_v2':
            self._handle_generate_v2(data); return
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
