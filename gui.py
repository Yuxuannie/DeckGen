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

# Add deckgen dir to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from resolver import resolve_all, ResolutionError, TemplateResolver, load_yaml
from deck_builder import build_deck, build_mc_deck
from writer import write_nominal_and_mc, get_deck_dirname, write_deck


def get_template_list():
    """Get list of available templates from the registry."""
    registry_path = os.path.join(SCRIPT_DIR, 'template_registry.yaml')
    if os.path.exists(registry_path):
        reg = load_yaml(registry_path)
        return reg.get('templates', [])
    return []


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>deckgen - SPICE Deck Generator</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f0f2f5; color: #333; padding: 20px;
  }
  .container { max-width: 900px; margin: 0 auto; }
  h1 {
    font-size: 22px; margin-bottom: 4px; color: #1a1a2e;
  }
  .subtitle { color: #666; font-size: 13px; margin-bottom: 20px; }
  .card {
    background: white; border-radius: 8px; padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 16px;
  }
  .card h2 {
    font-size: 15px; color: #1a1a2e; margin-bottom: 14px;
    padding-bottom: 8px; border-bottom: 1px solid #eee;
  }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .field { display: flex; flex-direction: column; }
  .field label {
    font-size: 12px; font-weight: 600; color: #555;
    margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.3px;
  }
  .field input, .field select {
    padding: 8px 10px; border: 1px solid #ddd; border-radius: 5px;
    font-size: 14px; transition: border-color 0.2s;
  }
  .field input:focus, .field select:focus {
    outline: none; border-color: #4a6cf7;
  }
  .field input.file-path {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace; font-size: 12px;
  }
  .btn-row { display: flex; gap: 10px; margin-top: 6px; }
  .btn {
    padding: 10px 24px; border: none; border-radius: 6px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.2s;
  }
  .btn-primary {
    background: #4a6cf7; color: white;
  }
  .btn-primary:hover { background: #3a5ce5; }
  .btn-secondary {
    background: #e8ecf1; color: #333;
  }
  .btn-secondary:hover { background: #d8dce3; }
  .result {
    display: none; margin-top: 16px; padding: 14px;
    border-radius: 6px; font-family: 'SF Mono', Monaco, monospace;
    font-size: 13px; white-space: pre-wrap; line-height: 1.5;
  }
  .result.success { display: block; background: #e8f5e9; color: #2e7d32; border: 1px solid #c8e6c9; }
  .result.error { display: block; background: #fbe9e7; color: #c62828; border: 1px solid #ffccbc; }
  .preview {
    display: none; margin-top: 12px;
  }
  .preview.show { display: block; }
  .preview pre {
    background: #1e1e2e; color: #cdd6f4; padding: 14px;
    border-radius: 6px; font-size: 12px; line-height: 1.5;
    max-height: 500px; overflow-y: auto;
  }
  .preview h3 { font-size: 13px; margin-bottom: 8px; color: #555; }
  .template-info {
    font-size: 12px; color: #888; margin-top: 4px; font-style: italic;
  }
  .checkbox-field {
    display: flex; align-items: center; gap: 6px; margin-top: 8px;
  }
  .checkbox-field input { width: auto; }
  .checkbox-field label { font-size: 13px; text-transform: none; margin: 0; }
  .sep { grid-column: 1 / -1; border-top: 1px solid #f0f0f0; margin: 4px 0; }
</style>
</head>
<body>
<div class="container">
  <h1>deckgen</h1>
  <p class="subtitle">Direct SPICE Deck Generator &mdash; delay / slew / hold</p>

  <form id="deckform" onsubmit="return generate(event)">

  <div class="card">
    <h2>Arc Specification</h2>
    <div class="grid">
      <div class="field">
        <label>Cell Name *</label>
        <input type="text" name="cell" placeholder="e.g. DFFQ1, SYNC2X4" required>
      </div>
      <div class="field">
        <label>Arc Type *</label>
        <select name="arc_type" required>
          <option value="delay">delay</option>
          <option value="slew">slew</option>
          <option value="hold" selected>hold</option>
        </select>
      </div>
      <div class="field">
        <label>When Condition</label>
        <input type="text" name="when" placeholder="e.g. !SE&amp;SI  (default: none)" value="NO_CONDITION">
      </div>
      <div class="field">
        <label>Related Pin *</label>
        <input type="text" name="rel_pin" placeholder="e.g. CP, A" required>
      </div>
      <div class="field">
        <label>Related Dir *</label>
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
        <label>Constrained Pin</label>
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
    </div>
  </div>

  <div class="card">
    <h2>Electrical Parameters</h2>
    <div class="grid">
      <div class="field">
        <label>VDD *</label>
        <input type="text" name="vdd" placeholder="e.g. 0.45" required>
      </div>
      <div class="field">
        <label>Temperature *</label>
        <input type="text" name="temp" placeholder="e.g. -40, 25, 125" required>
      </div>
      <div class="field">
        <label>Output Load</label>
        <input type="text" name="load" placeholder="e.g. 0.5f" value="0">
      </div>
      <div class="field">
        <label>Constr Pin Slew</label>
        <input type="text" name="slew" placeholder="e.g. 2.5n">
      </div>
      <div class="field">
        <label>Related Pin Slew</label>
        <input type="text" name="rel_slew" placeholder="e.g. 1.2n (defaults to slew)">
      </div>
      <div class="field">
        <label>Max Slew</label>
        <input type="text" name="max_slew" placeholder="auto (max of slew values)">
      </div>
    </div>
  </div>

  <div class="card">
    <h2>File Paths</h2>
    <div class="grid-2">
      <div class="field">
        <label>Netlist File *</label>
        <input class="file-path" type="text" name="netlist" placeholder="/path/to/cell.spi" required>
      </div>
      <div class="field">
        <label>Pin List (auto-extracted from netlist)</label>
        <input type="text" name="pins" placeholder="e.g. VDD VSS CP D Q SE SI">
      </div>
      <div class="field">
        <label>Model File *</label>
        <input class="file-path" type="text" name="model" placeholder="/path/to/model.spi" required>
      </div>
      <div class="field">
        <label>Waveform File *</label>
        <input class="file-path" type="text" name="waveform" placeholder="/path/to/waveform.spi" required>
      </div>
      <div class="sep"></div>
      <div class="field">
        <label>Custom Template (optional, bypasses registry)</label>
        <input class="file-path" type="text" name="template" placeholder="/path/to/custom_template.sp">
      </div>
      <div class="field">
        <label>Output Directory *</label>
        <input class="file-path" type="text" name="output" value="./output" required>
      </div>
    </div>
    <div class="checkbox-field">
      <input type="checkbox" id="nominal_only" name="nominal_only">
      <label for="nominal_only">Generate nominal deck only (skip Monte Carlo)</label>
    </div>
    <div class="field" style="margin-top:8px">
      <label>MC Samples</label>
      <input type="number" name="num_samples" value="5000" style="width:120px">
    </div>
  </div>

  <div class="btn-row">
    <button type="submit" class="btn btn-primary">Generate Deck</button>
    <button type="button" class="btn btn-secondary" onclick="previewOnly()">Preview Only</button>
    <button type="reset" class="btn btn-secondary">Reset</button>
  </div>

  </form>

  <div id="result" class="result"></div>
  <div id="preview" class="preview">
    <h3>Generated SPICE Deck Preview</h3>
    <pre id="preview-content"></pre>
  </div>

</div>

<script>
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

async function generate(e) {
  if (e) e.preventDefault();
  const data = getFormData();
  data.action = 'generate';
  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const result = await resp.json();
    const el = document.getElementById('result');
    const prev = document.getElementById('preview');
    const prevContent = document.getElementById('preview-content');
    if (result.success) {
      el.className = 'result success';
      el.textContent = result.message;
      if (result.deck_preview) {
        prev.className = 'preview show';
        prevContent.textContent = result.deck_preview;
      }
    } else {
      el.className = 'result error';
      el.textContent = result.error;
      prev.className = 'preview';
    }
  } catch(err) {
    const el = document.getElementById('result');
    el.className = 'result error';
    el.textContent = 'Connection error: ' + err.message;
  }
}

async function previewOnly() {
  const data = getFormData();
  data.action = 'preview';
  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const result = await resp.json();
    const el = document.getElementById('result');
    const prev = document.getElementById('preview');
    const prevContent = document.getElementById('preview-content');
    if (result.success) {
      el.className = 'result success';
      el.textContent = 'Preview generated (not written to disk)';
      prev.className = 'preview show';
      prevContent.textContent = result.deck_preview;
    } else {
      el.className = 'result error';
      el.textContent = result.error;
      prev.className = 'preview';
    }
  } catch(err) {
    const el = document.getElementById('result');
    el.className = 'result error';
    el.textContent = 'Connection error: ' + err.message;
  }
}
</script>
</body>
</html>
"""


class DeckgenHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the deckgen GUI."""

    def log_message(self, format, *args):
        # Quieter logging
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
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            result = self._handle_generate(data)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_generate(self, data):
        """Process a generate/preview request."""
        try:
            action = data.get('action', 'generate')

            # Config paths
            registry_path = os.path.join(SCRIPT_DIR, 'template_registry.yaml')
            templates_dir = os.path.join(SCRIPT_DIR, 'templates')

            # Validate hold requires constr_pin
            if data.get('arc_type') == 'hold' and not data.get('constr_pin'):
                return {'success': False, 'error': 'Constrained pin is required for hold arcs.'}

            # CLI overrides
            cli_overrides = {
                'vdd': data.get('vdd') or None,
                'temperature': data.get('temp') or None,
                'model_file': data.get('model') or None,
                'waveform_file': data.get('waveform') or None,
                'pushout_per': '0.4',
                'num_samples': int(data.get('num_samples', 5000)),
            }

            # Resolve
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

            # Slew values
            constr_slew = data.get('slew') or '0'
            rel_slew = data.get('rel_slew') or data.get('slew') or '0'
            max_slew = data.get('max_slew') or rel_slew or constr_slew

            # Build deck
            nominal_lines = build_deck(
                arc_info=arc_info,
                slew=(constr_slew, rel_slew),
                load=data.get('load') or '0',
                when=data.get('when') or 'NO_CONDITION',
                max_slew=max_slew,
            )

            deck_text = ''.join(nominal_lines)

            if action == 'preview':
                return {
                    'success': True,
                    'message': 'Preview generated',
                    'deck_preview': deck_text,
                }

            # Write to disk
            nominal_only = data.get('nominal_only', False)
            output_dir = data.get('output', './output')

            if nominal_only:
                dirname = get_deck_dirname(arc_info, data.get('when'))
                out_path = os.path.join(output_dir, dirname, 'nominal_sim.sp')
                write_deck(nominal_lines, out_path)
                msg = f"Nominal deck written to:\n{out_path}"
            else:
                num_samples = int(data.get('num_samples', 5000))
                mc_lines = build_mc_deck(nominal_lines, num_samples)
                nom_path, mc_path = write_nominal_and_mc(
                    nominal_lines, mc_lines, output_dir, arc_info,
                    data.get('when')
                )
                msg = f"Nominal deck: {nom_path}\nMC deck:      {mc_path}"

            # First 120 lines for preview
            preview_lines = nominal_lines[:120]
            preview_text = ''.join(preview_lines)
            if len(nominal_lines) > 120:
                preview_text += f"\n... ({len(nominal_lines) - 120} more lines)"

            return {
                'success': True,
                'message': msg,
                'deck_preview': preview_text,
            }

        except ResolutionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': f"Error: {type(e).__name__}: {e}"}


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
