#!/usr/bin/env python3
"""
gui.py - Browser-based GUI for deckgen.

Launches a small local web server with a form UI for generating SPICE decks.
Opens automatically in the default browser.

Usage:
    python gui.py [--port 8585]
"""

import http.server
import json
import os
import sys
import webbrowser
import urllib.parse
import threading
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from resolver import (
    resolve_all, ResolutionError, TemplateResolver, NetlistResolver, load_yaml
)
from deck_builder import build_deck, build_mc_deck
from writer import write_nominal_and_mc, get_deck_dirname, write_deck


HTML_PAGE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>deckgen - SPICE Deck Generator</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f0f2f5; color: #333; padding: 18px;
  }
  .container { max-width: 960px; margin: 0 auto; }
  .header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 4px; }
  h1 {
    font-size: 24px; color: #1a1a2e;
  }
  .version { color: #888; font-size: 12px; }
  .subtitle { color: #666; font-size: 13px; margin-bottom: 18px; }
  .card {
    background: white; border-radius: 8px; padding: 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 14px;
  }
  .card-header {
    display: flex; justify-content: space-between; align-items: center;
    cursor: pointer; user-select: none;
  }
  .card-header h2 {
    font-size: 14px; color: #1a1a2e; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .card-body {
    padding-top: 14px; margin-top: 10px; border-top: 1px solid #eee;
  }
  .card.collapsed .card-body { display: none; }
  .card.collapsed .card-header { margin-bottom: 0; }
  .toggle { color: #888; font-size: 12px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .field { display: flex; flex-direction: column; position: relative; }
  .field label {
    font-size: 11px; font-weight: 600; color: #555;
    margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.3px;
    display: flex; align-items: center; gap: 4px;
  }
  .help {
    display: inline-flex; width: 13px; height: 13px; border-radius: 50%;
    background: #bbb; color: white; font-size: 9px; font-weight: bold;
    align-items: center; justify-content: center; cursor: help;
    text-transform: none;
  }
  .help:hover { background: #666; }
  .help-text {
    display: none; position: absolute; top: 100%; left: 0; right: 0;
    background: #333; color: white; padding: 6px 10px; border-radius: 4px;
    font-size: 11px; font-weight: normal; text-transform: none;
    line-height: 1.4; z-index: 100; margin-top: 2px;
    letter-spacing: normal;
  }
  .help:hover + .help-text { display: block; }
  .field input, .field select, .field textarea {
    padding: 8px 10px; border: 1px solid #ddd; border-radius: 5px;
    font-size: 14px; transition: border-color 0.15s, box-shadow 0.15s;
    font-family: inherit;
  }
  .field input:focus, .field select:focus {
    outline: none; border-color: #4a6cf7;
    box-shadow: 0 0 0 3px rgba(74, 108, 247, 0.15);
  }
  .field input.file-path {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace; font-size: 12px;
  }
  .field input.invalid { border-color: #e57373; }
  .btn-row { display: flex; gap: 10px; margin-top: 4px; flex-wrap: wrap; }
  .btn {
    padding: 10px 22px; border: none; border-radius: 6px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.15s;
  }
  .btn:active { transform: scale(0.98); }
  .btn-primary { background: #4a6cf7; color: white; }
  .btn-primary:hover { background: #3a5ce5; }
  .btn-secondary { background: #e8ecf1; color: #333; }
  .btn-secondary:hover { background: #d8dce3; }
  .btn-subtle {
    background: transparent; color: #4a6cf7; padding: 6px 12px;
    font-size: 12px; font-weight: 500;
  }
  .btn-subtle:hover { background: #e8ecf1; }
  .result {
    display: none; margin-top: 12px; padding: 12px 14px;
    border-radius: 6px; font-family: 'SF Mono', Monaco, monospace;
    font-size: 12px; white-space: pre-wrap; line-height: 1.5;
  }
  .result.success { display: block; background: #e8f5e9; color: #2e7d32; border-left: 3px solid #4caf50; }
  .result.error { display: block; background: #fbe9e7; color: #c62828; border-left: 3px solid #f44336; }
  .result.info { display: block; background: #e3f2fd; color: #1565c0; border-left: 3px solid #2196f3; }
  .preview {
    display: none; margin-top: 12px;
  }
  .preview.show { display: block; }
  .preview-head {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 8px;
  }
  .preview-head h3 { font-size: 13px; color: #555; font-weight: 600; }
  .preview pre {
    background: #1e1e2e; color: #cdd6f4; padding: 14px;
    border-radius: 6px; font-size: 12px; line-height: 1.5;
    max-height: 520px; overflow-y: auto;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  }
  .match-preview {
    margin-top: 10px; padding: 10px 12px;
    background: #f5f7fb; border-radius: 5px; border-left: 3px solid #4a6cf7;
    font-family: 'SF Mono', Monaco, monospace; font-size: 12px;
    display: none;
  }
  .match-preview.show { display: block; }
  .match-preview strong { color: #1a1a2e; }
  .match-preview .path { color: #4a6cf7; }
  .examples {
    display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px;
  }
  .example-chip {
    font-size: 11px; background: #f0f2f5; padding: 3px 8px;
    border-radius: 10px; cursor: pointer; color: #555;
    border: 1px solid transparent;
  }
  .example-chip:hover { background: #e1e4ea; border-color: #4a6cf7; color: #4a6cf7; }
  .checkbox-field {
    display: flex; align-items: center; gap: 6px; margin-top: 10px;
  }
  .checkbox-field input { width: auto; }
  .checkbox-field label { font-size: 13px; text-transform: none; margin: 0; }
  .sep { grid-column: 1 / -1; border-top: 1px solid #f0f0f0; margin: 4px 0; }
  .spinner {
    display: inline-block; width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid #fff; border-top-color: transparent;
    animation: spin 0.6s linear infinite; vertical-align: middle;
    margin-right: 6px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .copy-btn {
    background: #2a2a3e; color: #888; border: 1px solid #3a3a4e;
    padding: 4px 10px; border-radius: 4px; font-size: 11px;
    cursor: pointer;
  }
  .copy-btn:hover { background: #3a3a4e; color: #cdd6f4; }
  .copy-btn.copied { background: #2e7d32; color: white; border-color: #2e7d32; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>deckgen</h1>
    <span class="version">v0.2</span>
  </div>
  <p class="subtitle">Direct SPICE Deck Generator &mdash; delay / slew / hold</p>

  <form id="deckform" onsubmit="return generate(event)">

  <div class="card" id="card-arc">
    <div class="card-header" onclick="toggleCard('card-arc')">
      <h2>Arc Specification</h2>
      <span class="toggle">[ collapse ]</span>
    </div>
    <div class="card-body">
    <div class="grid">
      <div class="field">
        <label>Cell Name <span class="help">?</span>
          <span class="help-text">Full cell name (e.g. DFFQ1, SYNC2X4). Used for template pattern matching.</span>
        </label>
        <input type="text" name="cell" placeholder="e.g. DFFQ1, SYNC2X4" required list="cell-examples">
        <datalist id="cell-examples">
          <option value="DFFQ1">
          <option value="SYNC2X4">
          <option value="SYNC3X2">
          <option value="CKGMUX3">
          <option value="CKGOR2">
          <option value="INV1">
          <option value="AO2">
          <option value="OR2">
        </datalist>
        <div class="examples">
          <span class="example-chip" onclick="fillCell('DFFQ1')">DFFQ1</span>
          <span class="example-chip" onclick="fillCell('SYNC2X4')">SYNC2X4</span>
          <span class="example-chip" onclick="fillCell('CKGMUX3')">CKGMUX3</span>
          <span class="example-chip" onclick="fillCell('INV1')">INV1</span>
        </div>
      </div>
      <div class="field">
        <label>Arc Type</label>
        <select name="arc_type" required>
          <option value="delay">delay</option>
          <option value="slew">slew</option>
          <option value="hold" selected>hold</option>
        </select>
      </div>
      <div class="field">
        <label>When Condition <span class="help">?</span>
          <span class="help-text">Logical condition for side pins (e.g. "!SE&amp;SI" means SE=0, SI=1). Use NO_CONDITION for none.</span>
        </label>
        <input type="text" name="when" placeholder="e.g. !SE&amp;SI" value="NO_CONDITION">
      </div>
      <div class="field">
        <label>Related Pin</label>
        <input type="text" name="rel_pin" placeholder="e.g. CP, A" required>
      </div>
      <div class="field">
        <label>Related Dir</label>
        <select name="rel_dir" required>
          <option value="rise">rise</option>
          <option value="fall">fall</option>
        </select>
      </div>
      <div class="field">
        <label>Probe/Output Pin</label>
        <input type="text" name="probe_pin" placeholder="e.g. Q, Y">
      </div>
      <div class="field">
        <label>Constrained Pin <span class="help">?</span>
          <span class="help-text">Required for hold arcs. The pin being constrained relative to the related pin.</span>
        </label>
        <input type="text" name="constr_pin" placeholder="e.g. D (required for hold)">
      </div>
      <div class="field">
        <label>Constrained Dir</label>
        <select name="constr_dir">
          <option value="">-- auto --</option>
          <option value="rise">rise</option>
          <option value="fall">fall</option>
        </select>
      </div>
      <div class="field" style="display:flex;justify-content:flex-end;align-items:flex-end">
        <button type="button" class="btn btn-subtle" onclick="checkTemplateMatch()">
          Check Template Match
        </button>
      </div>
    </div>
    <div id="match-preview" class="match-preview"></div>
    </div>
  </div>

  <div class="card" id="card-elec">
    <div class="card-header" onclick="toggleCard('card-elec')">
      <h2>Electrical Parameters</h2>
      <span class="toggle">[ collapse ]</span>
    </div>
    <div class="card-body">
    <div class="grid">
      <div class="field">
        <label>VDD <span class="help">?</span>
          <span class="help-text">Supply voltage in volts, e.g. 0.45, 0.75, 1.0</span>
        </label>
        <input type="text" name="vdd" placeholder="e.g. 0.45" required>
      </div>
      <div class="field">
        <label>Temperature</label>
        <input type="text" name="temp" placeholder="e.g. -40, 25, 125" required>
      </div>
      <div class="field">
        <label>Output Load</label>
        <input type="text" name="load" placeholder="e.g. 0.5f" value="0">
      </div>
      <div class="field">
        <label>Constr Pin Slew <span class="help">?</span>
          <span class="help-text">Slew rate of the constrained pin with units (f=femto, p=pico, n=nano).</span>
        </label>
        <input type="text" name="slew" placeholder="e.g. 2.5n">
      </div>
      <div class="field">
        <label>Related Pin Slew</label>
        <input type="text" name="rel_slew" placeholder="defaults to --slew">
      </div>
      <div class="field">
        <label>Max Slew</label>
        <input type="text" name="max_slew" placeholder="auto (max of both)">
      </div>
    </div>
    </div>
  </div>

  <div class="card" id="card-paths">
    <div class="card-header" onclick="toggleCard('card-paths')">
      <h2>File Paths</h2>
      <span class="toggle">[ collapse ]</span>
    </div>
    <div class="card-body">
    <div class="grid-2">
      <div class="field">
        <label>Netlist File</label>
        <input class="file-path" type="text" name="netlist" placeholder="/path/to/cell.spi" required>
      </div>
      <div class="field">
        <label>Pin List <span class="help">?</span>
          <span class="help-text">Space-separated pin list. Auto-extracted from the .subckt line if left blank.</span>
        </label>
        <input type="text" name="pins" placeholder="auto-extracted (e.g. VDD VSS CP D Q)">
      </div>
      <div class="field">
        <label>Model File</label>
        <input class="file-path" type="text" name="model" placeholder="/path/to/model.spi" required>
      </div>
      <div class="field">
        <label>Waveform File</label>
        <input class="file-path" type="text" name="waveform" placeholder="/path/to/waveform.spi" required>
      </div>
      <div class="sep"></div>
      <div class="field">
        <label>Custom Template <span class="help">?</span>
          <span class="help-text">Bypass the registry and use this .sp file directly.</span>
        </label>
        <input class="file-path" type="text" name="template" placeholder="/path/to/custom.sp (optional)">
      </div>
      <div class="field">
        <label>Output Directory</label>
        <input class="file-path" type="text" name="output" value="./output" required>
      </div>
    </div>
    <div class="checkbox-field">
      <input type="checkbox" id="nominal_only" name="nominal_only">
      <label for="nominal_only">Generate nominal deck only (skip Monte Carlo)</label>
    </div>
    <div class="field" style="margin-top:8px;max-width:180px">
      <label>MC Samples</label>
      <input type="number" name="num_samples" value="5000">
    </div>
    </div>
  </div>

  <div class="btn-row">
    <button type="submit" class="btn btn-primary" id="gen-btn">Generate Deck</button>
    <button type="button" class="btn btn-secondary" onclick="previewOnly()">Preview Only</button>
    <button type="button" class="btn btn-subtle" onclick="clearForm()">Reset</button>
    <button type="button" class="btn btn-subtle" onclick="loadLast()">Load Last Input</button>
  </div>

  </form>

  <div id="result" class="result"></div>
  <div id="preview" class="preview">
    <div class="preview-head">
      <h3>Generated SPICE Deck</h3>
      <button class="copy-btn" onclick="copyPreview(this)">Copy</button>
    </div>
    <pre id="preview-content"></pre>
  </div>

</div>

<script>
const STORAGE_KEY = 'deckgen_last_input';

function toggleCard(id) {
  document.getElementById(id).classList.toggle('collapsed');
}

function fillCell(name) {
  document.querySelector('[name=cell]').value = name;
  // Auto-fill reasonable defaults based on cell type
  const relPin = document.querySelector('[name=rel_pin]');
  const constrPin = document.querySelector('[name=constr_pin]');
  const probePin = document.querySelector('[name=probe_pin]');
  if (name.includes('DFF') || name.includes('SYNC')) {
    if (!relPin.value) relPin.value = 'CP';
    if (!constrPin.value) constrPin.value = 'D';
    if (!probePin.value) probePin.value = 'Q';
  } else if (name === 'INV1') {
    if (!relPin.value) relPin.value = 'A';
    if (!probePin.value) probePin.value = 'Y';
  }
}

function getFormData() {
  const form = document.getElementById('deckform');
  const data = {};
  const inputs = form.querySelectorAll('input, select');
  inputs.forEach(el => {
    if (el.type === 'checkbox') data[el.name] = el.checked;
    else data[el.name] = el.value;
  });
  return data;
}

function setFormData(data) {
  Object.keys(data).forEach(key => {
    const el = document.querySelector(`[name="${key}"]`);
    if (!el) return;
    if (el.type === 'checkbox') el.checked = !!data[key];
    else el.value = data[key];
  });
}

function saveLast(data) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch(e){}
}

function loadLast() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (Object.keys(saved).length === 0) {
      showResult('info', 'No previous input found.');
    } else {
      setFormData(saved);
      showResult('info', 'Loaded last used input.');
    }
  } catch(e) { showResult('error', 'Could not load last input: ' + e.message); }
}

function clearForm() {
  document.getElementById('deckform').reset();
  document.querySelector('[name=when]').value = 'NO_CONDITION';
  document.querySelector('[name=output]').value = './output';
  document.querySelector('[name=num_samples]').value = '5000';
  document.querySelector('[name=load]').value = '0';
  hideResults();
}

function showResult(kind, text) {
  const el = document.getElementById('result');
  el.className = 'result ' + kind;
  el.textContent = text;
}

function hideResults() {
  document.getElementById('result').className = 'result';
  document.getElementById('preview').className = 'preview';
  document.getElementById('match-preview').className = 'match-preview';
}

async function checkTemplateMatch() {
  const data = getFormData();
  data.action = 'check_match';
  try {
    const resp = await fetch('/api/match', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const result = await resp.json();
    const el = document.getElementById('match-preview');
    el.className = 'match-preview show';
    if (result.success) {
      el.innerHTML = `<strong>Template match:</strong> <span class="path">${result.template}</span>` +
        (result.note ? `<br><em>${result.note}</em>` : '');
    } else {
      el.innerHTML = `<strong>No match:</strong> ${result.error.replace(/\n/g,'<br>')}`;
    }
  } catch(err) { showResult('error', 'Connection error: ' + err.message); }
}

async function callApi(action) {
  const data = getFormData();
  data.action = action;
  const genBtn = document.getElementById('gen-btn');
  const origText = genBtn.textContent;
  if (action === 'generate') {
    genBtn.innerHTML = '<span class="spinner"></span>Generating...';
    genBtn.disabled = true;
  }
  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const result = await resp.json();
    if (result.success) {
      showResult('success', result.message);
      if (result.deck_preview) {
        document.getElementById('preview').className = 'preview show';
        document.getElementById('preview-content').textContent = result.deck_preview;
      }
      if (action === 'generate') saveLast(data);
    } else {
      showResult('error', result.error);
      document.getElementById('preview').className = 'preview';
    }
  } catch(err) {
    showResult('error', 'Connection error: ' + err.message);
  } finally {
    genBtn.textContent = origText;
    genBtn.disabled = false;
  }
}

function generate(e) { if (e) e.preventDefault(); callApi('generate'); return false; }
function previewOnly() { callApi('preview'); }

function copyPreview(btn) {
  const text = document.getElementById('preview-content').textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.classList.remove('copied'); btn.textContent = 'Copy'; }, 1400);
  });
}

// Auto-load last input on startup (without announcing it)
window.addEventListener('load', () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (Object.keys(saved).length > 0) setFormData(saved);
  } catch(e){}
});
</script>
</body>
</html>
"""


class DeckgenHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the deckgen GUI."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/generate':
            result = self._handle_generate(self._read_json())
        elif self.path == '/api/match':
            result = self._handle_match(self._read_json())
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode('utf-8'))

    def _read_json(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))

    def _handle_match(self, data):
        """Return the template that would be chosen -- without generating."""
        try:
            registry_path = os.path.join(SCRIPT_DIR, 'template_registry.yaml')
            templates_dir = os.path.join(SCRIPT_DIR, 'templates')

            if data.get('template'):
                if os.path.exists(data['template']):
                    return {'success': True, 'template': data['template'],
                            'note': 'Using custom template override'}
                return {'success': False, 'error': f"Custom template not found: {data['template']}"}

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
            rel_path = os.path.relpath(path, templates_dir)
            return {'success': True, 'template': rel_path}
        except ResolutionError as e:
            msg = str(e)
            if e.suggestions:
                msg += '\nClosest matches:\n' + '\n'.join(e.suggestions)
            return {'success': False, 'error': msg}
        except Exception as e:
            return {'success': False, 'error': f"{type(e).__name__}: {e}"}

    def _handle_generate(self, data):
        """Generate or preview a deck."""
        try:
            action = data.get('action', 'generate')
            registry_path = os.path.join(SCRIPT_DIR, 'template_registry.yaml')
            templates_dir = os.path.join(SCRIPT_DIR, 'templates')

            if data.get('arc_type') == 'hold' and not data.get('constr_pin'):
                return {'success': False,
                        'error': 'Constrained pin is required for hold arcs.'}

            cli_overrides = {
                'vdd': data.get('vdd') or None,
                'temperature': data.get('temp') or None,
                'model_file': data.get('model') or None,
                'waveform_file': data.get('waveform') or None,
                'pushout_per': '0.4',
                'num_samples': int(data.get('num_samples', 5000) or 5000),
            }

            arc_info = resolve_all(
                cell_name=data['cell'],
                arc_type=data['arc_type'],
                rel_pin=data['rel_pin'],
                rel_dir=data['rel_dir'],
                constr_pin=data.get('constr_pin') or data['rel_pin'],
                constr_dir=data.get('constr_dir') or None,
                probe_pin=data.get('probe_pin') or None,
                registry_path=registry_path,
                templates_dir=templates_dir,
                netlist_dir=None,
                corner_config=None,
                cli_overrides=cli_overrides,
                template_override=data.get('template') or None,
                netlist_override=data.get('netlist') or None,
                pins_override=data.get('pins') or None,
            )

            constr_slew = data.get('slew') or '0'
            rel_slew = data.get('rel_slew') or data.get('slew') or '0'
            max_slew = data.get('max_slew') or rel_slew or constr_slew

            nominal_lines = build_deck(
                arc_info=arc_info,
                slew=(constr_slew, rel_slew),
                load=data.get('load') or '0',
                when=data.get('when') or 'NO_CONDITION',
                max_slew=max_slew,
            )

            template_used = os.path.relpath(
                arc_info['TEMPLATE_DECK_PATH'], templates_dir
            ) if arc_info.get('TEMPLATE_DECK_PATH') else '(custom)'

            if action == 'preview':
                preview = ''.join(nominal_lines)
                return {
                    'success': True,
                    'message': f"Preview generated (not written to disk).\nTemplate: {template_used}",
                    'deck_preview': preview,
                }

            nominal_only = data.get('nominal_only', False)
            output_dir = data.get('output', './output')

            if nominal_only:
                dirname = get_deck_dirname(arc_info, data.get('when'))
                out_path = os.path.join(output_dir, dirname, 'nominal_sim.sp')
                write_deck(nominal_lines, out_path)
                msg = (
                    f"Nominal deck written:\n  {out_path}\n"
                    f"Template: {template_used}"
                )
            else:
                num_samples = int(data.get('num_samples', 5000) or 5000)
                mc_lines = build_mc_deck(nominal_lines, num_samples)
                nom_path, mc_path = write_nominal_and_mc(
                    nominal_lines, mc_lines, output_dir, arc_info,
                    data.get('when')
                )
                msg = (
                    f"Nominal deck: {nom_path}\n"
                    f"MC deck:      {mc_path}\n"
                    f"Template:     {template_used}"
                )

            preview_lines = nominal_lines[:120]
            preview_text = ''.join(preview_lines)
            if len(nominal_lines) > 120:
                preview_text += f"\n... ({len(nominal_lines) - 120} more lines)"

            return {'success': True, 'message': msg, 'deck_preview': preview_text}

        except ResolutionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': f"{type(e).__name__}: {e}"}


def main():
    parser = argparse.ArgumentParser(description='deckgen GUI')
    parser.add_argument('--port', type=int, default=8585, help='Port (default: 8585)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    args = parser.parse_args()

    server = http.server.HTTPServer(('127.0.0.1', args.port), DeckgenHandler)
    url = f'http://127.0.0.1:{args.port}'

    print(f"deckgen GUI running at {url}")
    print("Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == '__main__':
    main()
