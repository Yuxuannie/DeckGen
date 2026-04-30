#!/usr/bin/env python3
"""
gui.py - Browser-based GUI for deckgen v1.0.

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
    result = []
    for m in re.finditer(r'\(\s*(\d+)\s*,\s*(\d+)\s*\)', text or ''):
        result.append((int(m.group(1)), int(m.group(2))))
    return result


# ---------------------------------------------------------------------------
# HTML page (ASCII-only: no em-dashes, no smart quotes, no emojis)
# ---------------------------------------------------------------------------

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
.main{position:fixed;top:104px;left:0;right:0;bottom:0;
  display:grid;grid-template-columns:1fr 380px;overflow:hidden;}
.main-full{grid-template-columns:1fr;}
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
.atag{font-size:10px;padding:1px 6px;border-radius:8px;
  background:var(--tag-bg);color:var(--tag-fg);
  font-family:"SF Mono",Menlo,monospace;}
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
.tprow{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.tprow:last-child{margin-bottom:0;}
.tpin{flex:1;height:28px;padding:0 8px;border:1px solid var(--border-2);
  border-radius:4px;font-size:11px;font-family:"SF Mono",Menlo,monospace;color:var(--text);}
.tpin:focus{outline:2px solid rgba(23,23,23,.12);border-color:var(--accent);}
.tp-hint{font-size:10px;color:var(--text-3);margin-top:6px;margin-bottom:4px;}
.qsum{background:var(--tint);border:1px solid var(--border);
  border-radius:4px;padding:10px 12px;font-size:12px;}
.qsrow{display:flex;align-items:center;justify-content:space-between;
  padding:2px 0;color:var(--text-2);}
.qsrow.total{border-top:1px solid var(--border-2);margin-top:6px;
  padding-top:8px;color:var(--text);font-weight:600;}
.qnum{font-family:"SF Mono",Menlo,monospace;}
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
.dgrid{display:grid;grid-template-columns:1fr 1fr;height:100%;}
.dgrid .panel{border-right:1px solid var(--border);}
.dgrid .panel:last-child{border-right:none;}
.dta{width:100%;height:100%;border:none;resize:none;outline:none;
  font-family:"SF Mono",Menlo,monospace;font-size:12px;padding:14px 16px;
  line-height:1.6;background:var(--panel);color:var(--text);}
.vi{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;}
.vi .fl{flex:1;min-width:200px;}
.vi .fl input{width:100%;font-family:"SF Mono",Menlo,monospace;font-size:12px;}
.vcards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px;}
.vcard{border:1px solid var(--border);border-radius:6px;padding:12px 14px;background:var(--panel);}
.vc-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);}
.vc-num{font-size:26px;font-weight:700;font-family:"SF Mono",Menlo,monospace;margin-top:4px;}
.vc-num.ok{color:var(--ok);}.vc-num.warn{color:var(--warn);}.vc-num.err{color:var(--err);}
table.vtbl{width:100%;border-collapse:collapse;font-size:12px;}
table.vtbl th{text-align:left;font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;color:var(--text-2);padding:8px 10px;
  border-bottom:1px solid var(--border);background:#fafafa;position:sticky;top:0;}
table.vtbl td{padding:8px 10px;border-bottom:1px solid var(--border);
  font-family:"SF Mono",Menlo,monospace;}
table.vtbl tr:hover td{background:var(--tint);}
.l1{color:var(--ok);font-weight:600;}.l2{color:var(--warn);font-weight:600;}.l3{color:var(--err);font-weight:600;}
.view-hidden{display:none!important;}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">DeckGen</div>
  <div class="tabs">
    <div class="tab active" onclick="showTab('explore')">Explore</div>
    <div class="tab" onclick="showTab('direct')">Direct</div>
    <div class="tab" onclick="showTab('validate')">Validate</div>
  </div>
  <div class="spacer"></div>
  <div class="status-pill" id="statusPill">Loading&#x2026;</div>
</div>
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
      <div class="msearch"><input type="text" id="cornerSearch" placeholder="Search corners&#x2026;" oninput="filterCorners()"></div>
      <div class="mlist" id="cornerList"></div>
    </div>
  </div>
  <div class="spacer"></div>
  <button class="btn" onclick="doRescan()">Rescan</button>
</div>
<div class="main" id="view-explore">
  <div class="panel">
    <div class="ph">
      <span class="pt">Cells &amp; Arcs</span>
      <span class="status-pill" id="cellsCount" style="margin-left:4px;">&#x2014;</span>
    </div>
    <div class="pb">
      <div class="srow">
        <div class="swrap">
          <span class="sico">&#9906;</span>
          <input type="text" id="cellSearch" placeholder="Search cells&#x2026;" oninput="filterCells()">
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
  <div class="panel">
    <div class="ph">
      <span class="pt">Queue</span>
      <span class="status-pill" id="queueCount" style="margin-left:4px;">0 arcs</span>
      <div class="spacer"></div>
    </div>
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
    <div class="pb view-hidden" id="resultsBody">
      <div class="qsl">Generated decks
        <div class="spacer"></div>
        <button class="btn btn-sm btn-ghost" onclick="showQueueView()">&larr; Back</button>
      </div>
      <div id="genStatus" style="font-size:11px;color:var(--text-2);margin-bottom:10px;"></div>
      <div id="resultList"></div>
    </div>
    <div class="pf view-hidden" id="resultsFooter">
      <button class="btn btn-sm btn-ghost" onclick="copyAllPaths()">Copy all paths</button>
      <button class="btn btn-sm btn-ghost" onclick="openOutputDir()" style="margin-left:6px;">Open output dir</button>
      <div class="spacer"></div>
    </div>
  </div>
</div>
<div class="deck-ov" id="deckOv">
  <div class="dvh">
    <span class="pt">Deck</span>
    <span class="dvtitle" id="dvTitle">&#x2014;</span>
    <button class="btn btn-sm btn-ghost" onclick="closeDeck()">&#215; Close</button>
    <button class="btn btn-sm" onclick="copyDeck()">Copy</button>
  </div>
  <div class="dvbody"><pre id="dvContent"></pre></div>
</div>
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
        <span class="status-pill" id="directPill" style="margin-left:4px;">&#x2014;</span>
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
</div>
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
      <div class="vcards">
        <div class="vcard"><div class="vc-lbl">Total pairs</div><div class="vc-num" id="vTotal">&#x2014;</div></div>
        <div class="vcard"><div class="vc-lbl">Identical (L1)</div><div class="vc-num ok" id="vL1">&#x2014;</div></div>
        <div class="vcard"><div class="vc-lbl">Normalized (L2)</div><div class="vc-num warn" id="vL2">&#x2014;</div></div>
        <div class="vcard"><div class="vc-lbl">Different (L3)</div><div class="vc-num err" id="vL3">&#x2014;</div></div>
      </div>
      <div class="fbar" id="vFilters">
        <div class="fc on" onclick="setVFilter('all',this)">All</div>
        <div class="fc" onclick="setVFilter('l3',this)">L3 only</div>
        <div class="fc" onclick="setVFilter('hold',this)">hold</div>
        <div class="fc" onclick="setVFilter('setup',this)">setup</div>
        <div class="fc" onclick="setVFilter('recovery',this)">recovery</div>
        <div class="fc" onclick="setVFilter('removal',this)">removal</div>
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
</div>
<script>
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
var S={node:'',libtype:'',corners:[],selCorners:new Set(),cells:[],arcCache:{},
  queue:[],arcFilter:'all',cellFilter:'',results:[],lastDeckPath:'',
  vResults:[],vFilter:'all'};
function showTab(name){
  ['explore','direct','validate'].forEach(function(n){
    document.getElementById('view-'+n).classList.toggle('view-hidden',n!==name);});
  document.querySelectorAll('.tab').forEach(function(t,i){
    t.classList.toggle('active',['explore','direct','validate'][i]===name);});
  document.getElementById('dbar').style.display=name==='validate'?'none':'flex';
  closeDeck();}
function post(url,body){return fetch(url,{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(body)
  }).then(function(r){return r.json();});}
function loadNodes(){post('/api/nodes',{}).then(function(d){
  var sel=document.getElementById('selNode');sel.innerHTML='';
  (d.nodes||[]).forEach(function(n){var o=document.createElement('option');
    o.value=o.textContent=n;sel.appendChild(o);});
  if(d.nodes&&d.nodes.length){S.node=d.nodes[0];loadLibtypes();}
  else updateStatusPill();}).catch(function(){updateStatusPill();});}
function onNodeChange(){S.node=document.getElementById('selNode').value;
  S.libtype='';S.selCorners=new Set();S.cells=[];S.arcCache={};loadLibtypes();}
function loadLibtypes(){post('/api/lib_types',{node:S.node}).then(function(d){
  var sel=document.getElementById('selLibtype');sel.innerHTML='';
  (d.lib_types||[]).forEach(function(lt){var o=document.createElement('option');
    o.value=o.textContent=lt;sel.appendChild(o);});
  if(d.lib_types&&d.lib_types.length){S.libtype=d.lib_types[0];loadCorners();}
  else updateStatusPill();});}
function onLibtypeChange(){S.libtype=document.getElementById('selLibtype').value;
  S.selCorners=new Set();S.cells=[];S.arcCache={};loadCorners();}
function loadCorners(){post('/api/corners',{node:S.node,lib_type:S.libtype}).then(function(d){
  S.corners=d.corners||[];S.selCorners=new Set(S.corners);
  renderCornerChips();renderCornerMenu();loadCells();});}
function renderCornerChips(){var el=document.getElementById('cornerChips');
  var sel=Array.from(S.selCorners);
  if(!sel.length){el.innerHTML='<span style="color:var(--text-3);font-size:11px;">none selected</span>';return;}
  var html='';
  sel.slice(0,2).forEach(function(c){
    var short=c.split('_').slice(0,3).join('_');
    html+='<span class="chip">'+esc(short)+'</span>';});
  if(sel.length>2)html+='<span class="chip-more">+'+(sel.length-2)+' more</span>';
  el.innerHTML=html;}
function renderCornerMenu(){var list=document.getElementById('cornerList');
  list.innerHTML='';
  S.corners.forEach(function(c){
    var div=document.createElement('div');div.className='mitem';
    var chk=document.createElement('input');chk.type='checkbox';chk.checked=S.selCorners.has(c);
    chk.addEventListener('change',function(){
      if(this.checked)S.selCorners.add(c);else S.selCorners.delete(c);
      renderCornerChips();updateStatusPill();renderQueue();});
    div.appendChild(chk);div.appendChild(document.createTextNode(c));list.appendChild(div);});}
function filterCorners(){var q=document.getElementById('cornerSearch').value.toLowerCase();
  document.querySelectorAll('#cornerList .mitem').forEach(function(el){
    el.style.display=el.textContent.toLowerCase().includes(q)?'':'none';});}
function toggleCornerMenu(){document.getElementById('cdrop').classList.toggle('open');}
document.addEventListener('click',function(e){
  if(!e.target.closest('.fl'))document.getElementById('cdrop').classList.remove('open');});
function doRescan(){post('/api/rescan',{node:S.node,lib_type:S.libtype}).then(function(){loadCells();});}
function updateStatusPill(){var pill=document.getElementById('statusPill');
  var nc=document.getElementById('cellsCount');
  var n=S.node||'--';var lt=S.libtype?S.libtype.split('_').slice(-1)[0]:'--';
  var c=S.selCorners.size;var cells=S.cells?S.cells.length:0;
  pill.textContent=n+' / '+lt+' / '+c+' corners / '+cells+' cells';
  if(nc)nc.textContent=cells+' cells';}
function loadCells(){document.getElementById('cellList').innerHTML='<div class="cell-loading">Loading cells...</div>';
  post('/api/cells',{node:S.node,lib_type:S.libtype}).then(function(d){
    S.cells=d.cells||[];S.arcCache={};updateStatusPill();renderCells();});}
function filterCells(){S.cellFilter=document.getElementById('cellSearch').value.toLowerCase();renderCells();}
function setArcFilter(type,el){S.arcFilter=type;
  document.querySelectorAll('.fbar .fc').forEach(function(c){c.classList.remove('on');});
  el.classList.add('on');renderCells();}
function renderCells(){var list=document.getElementById('cellList');
  var filtered=S.cells.filter(function(c){
    var name=(typeof c==='string')?c:c.name;
    return !S.cellFilter||name.toLowerCase().includes(S.cellFilter);});
  if(!filtered.length){list.innerHTML='<div class="cell-loading">No cells match.</div>';return;}
  list.innerHTML='';
  filtered.forEach(function(c){
    var name=(typeof c==='string')?c:c.name;
    var counts=(typeof c==='object'&&c.arc_counts)?c.arc_counts:{};
    var row=document.createElement('div');row.className='crow';
    var tagsHtml='';
    Object.keys(counts).forEach(function(t){
      if(S.arcFilter==='all'||S.arcFilter===t)
        tagsHtml+='<span class="atag">'+esc(t)+':'+counts[t]+'</span>';});
    row.innerHTML='<div class="chead" data-cell="'+encodeURIComponent(name)+'">'+
      '<span class="twisty">&#9654;</span>'+
      '<span class="cname">'+esc(name)+'</span>'+
      '<div class="ctags">'+tagsHtml+'</div></div>';
    row.querySelector('.chead').addEventListener('click',function(){
      toggleCell(this,name);});
    list.appendChild(row);});}
function toggleCell(head,cellName){
  var existing=head.nextElementSibling;
  var twisty=head.querySelector('.twisty');
  if(existing&&existing.classList.contains('alist')){
    existing.style.display=existing.style.display==='none'?'':'none';
    twisty.innerHTML=existing.style.display==='none'?'&#9654;':'&#9660;';return;}
  twisty.innerHTML='&#9660;';
  if(S.arcCache[cellName]){renderArcList(head,cellName,S.arcCache[cellName]);}
  else{post('/api/arcs',{node:S.node,lib_type:S.libtype,cell:cellName}).then(function(d){
    S.arcCache[cellName]=d.arcs||[];renderArcList(head,cellName,S.arcCache[cellName]);});}}
function renderArcList(head,cellName,arcs){
  var alist=document.createElement('div');alist.className='alist';
  var filtered=S.arcFilter==='all'?arcs:arcs.filter(function(a){return a.arc_type===S.arcFilter;});
  if(!filtered.length){alist.innerHTML='<div style="padding:6px 12px;font-size:11px;color:var(--text-3);">No arcs for this filter.</div>';}
  filtered.forEach(function(a){
    var arcId=buildArcId(cellName,a);
    var inQueue=S.queue.some(function(q){return q.arc_id===arcId;});
    var div=document.createElement('div');
    div.className='arow'+(inQueue?' inq':'');
    div.dataset.arcId=arcId;
    div.innerHTML='<span class="adesc">'+esc(a.arc_type)+' &nbsp;|&nbsp; '+
      esc(a.probe_pin)+'/'+esc(a.probe_dir)+' &nbsp;&middot;&nbsp; '+
      esc(a.rel_pin)+'/'+esc(a.rel_dir)+' &nbsp;|&nbsp; '+esc(a.when||'NO_CONDITION')+'</span>'+
      '<span class="abtn">'+(inQueue?'&#10003; added':'+ Add')+'</span>';
    if(!inQueue){div.addEventListener('click',function(){addToQueue(cellName,a,div);});}
    alist.appendChild(div);});
  head.parentNode.insertBefore(alist,head.nextSibling);}
function buildArcId(cellName,a){
  return [a.arc_type,cellName,a.probe_pin,a.probe_dir,a.rel_pin,a.rel_dir,a.when||'NO_CONDITION'].join('_');}
function addToQueue(cellName,a,rowEl){
  var arcId=buildArcId(cellName,a);
  if(S.queue.some(function(q){return q.arc_id===arcId;}))return;
  S.queue.push({arc_type:a.arc_type,probe_pin:a.probe_pin,probe_dir:a.probe_dir,
    rel_pin:a.rel_pin,rel_dir:a.rel_dir,when:a.when||'NO_CONDITION',
    cell:cellName,arc_id:arcId,index_1:a.index_1||[],index_2:a.index_2||[]});
  rowEl.classList.add('inq');rowEl.querySelector('.abtn').textContent='added';rowEl.onclick=null;
  renderQueue();}
function clearQueue(){S.queue=[];
  document.querySelectorAll('.arow.inq').forEach(function(r){
    r.classList.remove('inq');r.querySelector('.abtn').textContent='+ Add';});
  renderQueue();}
function removeFromQueue(arcId){
  S.queue=S.queue.filter(function(q){return q.arc_id!==arcId;});
  var el=document.querySelector('.arow[data-arc-id="'+arcId+'"]');
  if(el){el.classList.remove('inq');el.querySelector('.abtn').textContent='+ Add';}
  renderQueue();}
function renderQueue(){var qList=document.getElementById('arcQueueList');
  if(!S.queue.length){qList.innerHTML='<div class="qempty">Add arcs from the left panel.</div>';}
  else{qList.innerHTML='';
    S.queue.forEach(function(q){
      var div=document.createElement('div');div.className='qrow';
      div.innerHTML='<span class="atag" style="flex-shrink:0;">'+esc(q.arc_type)+'</span>'+
        '<span class="qtext">'+esc(q.cell)+' &nbsp;|&nbsp; '+
        esc(q.probe_pin)+'/'+esc(q.probe_dir)+' &middot; '+esc(q.rel_pin)+'/'+esc(q.rel_dir)+'</span>'+
        '<span class="qx" data-arc="'+encodeURIComponent(q.arc_id)+'">&#215;</span>';
      div.querySelector('.qx').addEventListener('click',function(){
        removeFromQueue(decodeURIComponent(this.dataset.arc));});
      qList.appendChild(div);});}
  renderTpInputs();renderQueueSummary();updateGenerateButton();}
function renderTpInputs(){var container=document.getElementById('tpInputs');container.innerHTML='';
  var types=arcTypesInQueue();if(!types.length)return;
  types.forEach(function(t){
    var row=document.createElement('div');row.className='tprow';
    row.innerHTML='<span class="atag" style="min-width:90px;">'+esc(t)+'</span>'+
      '<input class="tpin" id="tp_'+esc(t)+'" type="text" placeholder="(1,1) (2,3) (4,4)" oninput="renderQueueSummary()">'+
      '<button class="btn btn-sm btn-ghost" data-type="'+esc(t)+'">Sweep</button>';
    row.querySelector('button').addEventListener('click',function(){sweepAll(this.dataset.type);});
    container.appendChild(row);});}
function arcTypesInQueue(){var seen={};var types=[];
  S.queue.forEach(function(q){if(!seen[q.arc_type]){seen[q.arc_type]=true;types.push(q.arc_type);}});return types;}
function sweepAll(arcType){var q=S.queue.find(function(x){return x.arc_type===arcType&&x.index_1&&x.index_1.length;});
  if(!q)return;var pts=[];
  for(var i=1;i<=q.index_1.length;i++){for(var j=1;j<=q.index_2.length;j++){pts.push('('+i+','+j+')');}}
  var inp=document.getElementById('tp_'+arcType);
  if(inp){inp.value=pts.join(' ');renderQueueSummary();}}
function getTpMap(){var map={};
  arcTypesInQueue().forEach(function(t){var el=document.getElementById('tp_'+t);map[t]=el?el.value:'';});return map;}
function parseTpText(text){var pts=[];var re=/\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*\\)/g;var m;
  while((m=re.exec(text))!==null)pts.push([parseInt(m[1]),parseInt(m[2])]);return pts;}
function renderQueueSummary(){var el=document.getElementById('qSummary');
  if(!S.queue.length){el.innerHTML='<div class="qsrow total"><span>0 arcs x 0 corners</span><span class="qnum">0 total</span></div>';return;}
  var byType={};S.queue.forEach(function(q){byType[q.arc_type]=(byType[q.arc_type]||0)+1;});
  var tpMap=getTpMap();var total=0;var rows='';
  Object.keys(byType).forEach(function(t){
    var pts=parseTpText(tpMap[t]||'').length;var decks=byType[t]*pts;total+=decks;
    rows+='<div class="qsrow"><span><span class="atag" style="margin-right:4px;">'+esc(t)+'</span>'+
      byType[t]+' arcs x '+pts+' pts</span><span class="qnum">'+decks+' decks</span></div>';});
  var corners=S.selCorners.size;
  rows+='<div class="qsrow total"><span>'+total+' decks x '+corners+' corners</span><span class="qnum">'+(total*corners)+' total</span></div>';
  el.innerHTML=rows;document.getElementById('queueCount').textContent=S.queue.length+' arcs';updateGenerateButton();}
function updateGenerateButton(){var tpMap=getTpMap();
  var hasPoints=Object.values(tpMap).some(function(v){return parseTpText(v).length>0;});
  var btn=document.getElementById('btnGenerate');var total=calcTotal();
  btn.textContent=total>0?'Generate '+total+' decks':'Generate';
  btn.disabled=!(S.queue.length&&S.selCorners.size&&hasPoints);}
function calcTotal(){var byType={};
  S.queue.forEach(function(q){byType[q.arc_type]=(byType[q.arc_type]||0)+1;});
  var tpMap=getTpMap();var total=0;
  Object.keys(byType).forEach(function(t){total+=byType[t]*parseTpText(tpMap[t]||'').length;});
  return total*S.selCorners.size;}
function doPreview(){var body=buildGenerateBody();
  post('/api/preview_v2',body).then(function(d){
    alert('Preview: '+(d.jobs?d.jobs.length:0)+' jobs planned. Errors: '+(d.errors?d.errors.length:0));});}
function buildGenerateBody(){var tpMap=getTpMap();
  var arcIds=S.queue.map(function(q){return q.arc_id;});
  return{mode:'explore',node:S.node,lib_type:S.libtype,
    corners:Array.from(S.selCorners),arc_ids:arcIds,table_points:tpMap,output_dir:'./output/'};}
function doGenerate(){var body=buildGenerateBody();showResultsView();
  document.getElementById('genStatus').textContent='Generating...';
  document.getElementById('resultList').innerHTML='';S.results=[];
  fetch('/api/generate_v2',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)}).then(function(resp){
    var reader=resp.body.getReader();var decoder=new TextDecoder();var buf='';
    function pump(){return reader.read().then(function(chunk){
      if(chunk.done){finalizeResults();return;}
      buf+=decoder.decode(chunk.value,{stream:true});
      var lines=buf.split('\n');buf=lines.pop();
      lines.forEach(function(line){if(!line.trim())return;
        try{var r=JSON.parse(line);
          if(r.status==='progress')return;
          if(r.status==='done'){(r.results||[]).forEach(function(res){S.results.push(res);appendResultRow(res);});return;}
          S.results.push(r);appendResultRow(r);}catch(e){}});
      return pump();});}
    return pump();}).catch(function(e){
    document.getElementById('genStatus').textContent='Error: '+e.message;});}
function appendResultRow(r){var list=document.getElementById('resultList');
  var ok=r.success!==false&&!r.error;
  var div=document.createElement('div');div.className='rrow';
  div.innerHTML='<span class="rico" style="color:'+(ok?'var(--ok)':'var(--err)')+';">&#9679;</span>'+
    '<div class="rtxt"><div class="rname" style="'+(ok?'':'color:var(--err);')+'">'+
    esc(r.arc_id||r.id||'?')+'</div>'+
    '<div class="rmeta">'+esc(r.corner||'')+(r.error?' -- '+esc(r.error):'')+'</div></div>'+
    '<span class="rarrow">&#8250;</span>';
  if(ok&&r.output_path){div.addEventListener('click',function(){
    openDeck(div,r.output_path,(r.arc_id||'')+(r.corner?' - '+r.corner:''));});}
  list.appendChild(div);}
function finalizeResults(){var ok=S.results.filter(function(r){return r.success!==false&&!r.error;}).length;
  var fail=S.results.length-ok;
  document.getElementById('genStatus').innerHTML=
    '<span style="color:var(--ok);font-weight:600;">&#10003; '+ok+' succeeded</span>&nbsp;&nbsp;'+
    '<span style="color:var(--err);font-weight:600;">&#10007; '+fail+' failed</span>&nbsp;&nbsp;'+
    '<span style="color:var(--text-3);">Click a row to preview deck</span>';}
function showResultsView(){
  document.getElementById('queueBody').classList.add('view-hidden');
  document.getElementById('queueFooter').classList.add('view-hidden');
  document.getElementById('resultsBody').classList.remove('view-hidden');
  document.getElementById('resultsFooter').classList.remove('view-hidden');}
function showQueueView(){
  document.getElementById('queueBody').classList.remove('view-hidden');
  document.getElementById('queueFooter').classList.remove('view-hidden');
  document.getElementById('resultsBody').classList.add('view-hidden');
  document.getElementById('resultsFooter').classList.add('view-hidden');closeDeck();}
function copyAllPaths(){var paths=S.results.filter(function(r){return r.output_path;})
  .map(function(r){return r.output_path;}).join('\n');
  navigator.clipboard.writeText(paths).catch(function(){});}
function openOutputDir(){var row=document.querySelector('#resultList .result-row');
  if(!row)return;var path=row.dataset.path||'';
  var dir=path.split('/').slice(0,-1).join('/');
  if(dir){navigator.clipboard.writeText(dir).then(function(){alert('Output directory path copied: '+dir);}).catch(function(){});}}
function openDeck(row,path,title){
  document.querySelectorAll('.rrow').forEach(function(r){r.classList.remove('sel');});
  if(row)row.classList.add('sel');S.lastDeckPath=path;
  document.getElementById('dvTitle').textContent=title||path;
  document.getElementById('dvContent').textContent='Loading...';
  document.getElementById('deckOv').classList.add('open');
  fetch('/api/deck?path='+encodeURIComponent(path))
    .then(function(r){return r.text();})
    .then(function(txt){document.getElementById('dvContent').textContent=txt;})
    .catch(function(e){document.getElementById('dvContent').textContent='Error: '+e.message;});}
function closeDeck(){document.getElementById('deckOv').classList.remove('open');
  document.querySelectorAll('.rrow').forEach(function(r){r.classList.remove('sel');});}
function copyDeck(){navigator.clipboard.writeText(document.getElementById('dvContent').textContent).catch(function(){});}
function directLoadFile(){document.getElementById('directFile').click();}
function directFileChosen(e){var f=e.target.files[0];if(!f)return;
  var reader=new FileReader();reader.onload=function(ev){
    document.getElementById('directTA').value=ev.target.result;directParse();};reader.readAsText(f);}
function directClear(){document.getElementById('directTA').value='';directParse();}
function directParse(){var lines=document.getElementById('directTA').value.split('\n')
  .map(function(l){return l.trim();}).filter(Boolean);
  var byType={};var errors=[];
  lines.forEach(function(l){var parts=l.split('_');var arcType=parts[0]||'';
    if(!arcType){errors.push(l);return;}byType[arcType]=(byType[arcType]||0)+1;});
  var corners=S.selCorners.size;var total=lines.length*corners;
  var pill=document.getElementById('directPill');
  pill.textContent=lines.length+' arcs x '+corners+' corners = '+total+' decks';
  var sumEl=document.getElementById('directSummary');
  if(!lines.length){sumEl.innerHTML='<div class="qempty">Paste identifiers or load a file to begin.</div>';return;}
  var html='<div class="qsl">Arc-types detected</div>';
  Object.keys(byType).forEach(function(t){html+='<div class="qrow"><span class="atag" style="flex-shrink:0;">'+esc(t)+
    '</span><span class="qtext">'+byType[t]+' arcs -- i1/i2 from identifier suffix</span></div>';});
  if(errors.length)html+='<div style="margin-top:8px;font-size:11px;color:var(--err);">'+errors.length+' unrecognized lines</div>';
  html+='<div style="margin-top:14px;" class="qsum"><div class="qsrow total"><span>'+
    lines.length+' arcs x '+corners+' corners</span><span class="qnum">'+total+' decks</span></div></div>';
  sumEl.innerHTML=html;}
function directPreview(){var lines=document.getElementById('directTA').value.split('\n')
  .map(function(l){return l.trim();}).filter(Boolean);
  post('/api/preview_v2',{mode:'batch',node:S.node,lib_type:S.libtype,
    corners:Array.from(S.selCorners),arc_ids:lines}).then(function(d){
    alert('Preview: '+(d.jobs?d.jobs.length:0)+' jobs planned. Errors: '+(d.errors?d.errors.length:0));});}
function directGenerate(){var lines=document.getElementById('directTA').value.split('\n')
  .map(function(l){return l.trim();}).filter(Boolean);
  showTab('explore');showResultsView();
  document.getElementById('genStatus').textContent='Generating (direct mode)...';
  document.getElementById('resultList').innerHTML='';S.results=[];
  fetch('/api/generate_v2',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({mode:'batch',node:S.node,lib_type:S.libtype,
      corners:Array.from(S.selCorners),arc_ids:lines,output_dir:'./output/'})
  }).then(function(resp){var reader=resp.body.getReader();var decoder=new TextDecoder();var buf='';
    function pump(){return reader.read().then(function(chunk){
      if(chunk.done){finalizeResults();return;}
      buf+=decoder.decode(chunk.value,{stream:true});
      var ls=buf.split('\n');buf=ls.pop();
      ls.forEach(function(line){if(!line.trim())return;
        try{var r=JSON.parse(line);
          if(r.status==='progress')return;
          if(r.status==='done'){(r.results||[]).forEach(function(res){S.results.push(res);appendResultRow(res);});return;}
          S.results.push(r);appendResultRow(r);}catch(e){}});
      return pump();});}return pump();});}
var _vAllRows=[];
function runValidation(){post('/api/validate',{
  deckgen_root:document.getElementById('vDeckgenRoot').value,
  mcqc_root:document.getElementById('vMcqcRoot').value,
  file:document.getElementById('vFile').value,max_detail:200})
  .then(function(d){_vAllRows=d.pairs||[];
    document.getElementById('vTotal').textContent=d.total||0;
    document.getElementById('vL1').textContent=d.l1||0;
    document.getElementById('vL2').textContent=d.l2||0;
    document.getElementById('vL3').textContent=d.l3||0;
    renderVTable();}).catch(function(e){alert('Validation error: '+e.message);});}
function setVFilter(f,el){S.vFilter=f;
  document.querySelectorAll('#vFilters .fc').forEach(function(c){c.classList.remove('on');});
  el.classList.add('on');renderVTable();}
function renderVTable(){var rows=_vAllRows.filter(function(r){
  if(S.vFilter==='all')return true;if(S.vFilter==='l3')return r.level===3;
  return r.arc_type===S.vFilter;});
  var tbody=document.getElementById('vTbody');tbody.innerHTML='';
  rows.forEach(function(r){var tr=document.createElement('tr');
    var lvlClass='l'+(r.level||1);
    tr.innerHTML='<td><span class="atag">'+esc(r.arc_type||'')+'</span></td>'+
      '<td>'+esc(r.arc_id||'')+'</td>'+
      '<td><span class="'+esc(lvlClass)+'">L'+(r.level||1)+'</span></td>'+
      '<td>'+esc(r.top_class||'--')+'</td>'+
      '<td>'+(r.lines_diff||0)+'</td>'+
      '<td><button class="btn btn-sm btn-ghost">View diff</button></td>';
    tbody.appendChild(tr);});}
function exportHtml(){post('/api/validate_html',{
  deckgen_root:document.getElementById('vDeckgenRoot').value,
  mcqc_root:document.getElementById('vMcqcRoot').value,
  file:document.getElementById('vFile').value,max_detail:200})
  .then(function(d){if(d.ok&&d.html_path){
    window.open('/api/validate_html_serve?path='+encodeURIComponent(d.html_path));}
  else{alert('Export failed: '+(d.error||'unknown error'));}});}
loadNodes();
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
        if not path:
            self.send_response(400)
            self.end_headers()
            return
        if not path.lower().endswith('.html'):
            self.send_response(403)
            self.end_headers()
            return
        import tempfile as _tempfile
        tmp_root = os.path.realpath(_tempfile.gettempdir())
        real_path = os.path.realpath(path)
        if not (real_path.startswith(tmp_root + os.sep) or real_path == tmp_root):
            self.send_response(403)
            self.end_headers()
            return
        if not os.path.isfile(path):
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

        # Directory restriction: path must be under output dir or collateral root
        allowed_roots = []
        out_dir = getattr(DeckgenHandler, 'OUTPUT_DIR', None)
        if out_dir:
            allowed_roots.append(os.path.realpath(out_dir))
        coll_root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
        if coll_root:
            allowed_roots.append(os.path.realpath(coll_root))

        if allowed_roots:
            real_path = os.path.realpath(path)
            if not any(real_path.startswith(r + os.sep) or real_path == r
                       for r in allowed_roots):
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
        """Generate: run the batch using collateral-backed planning (streams NDJSON)."""
        from core.batch import plan_jobs, execute_jobs
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

            jobs, errors = plan_jobs(
                arc_ids,
                corner_names=data.get('corners', []),
                files={},
                overrides=None,
                node=data.get('node') or None,
                lib_type=data.get('lib_type') or None,
                collateral_root=DeckgenHandler.COLLATERAL_ROOT)
        except Exception as e:
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            line = json.dumps({'status': 'done', 'succeeded': 0, 'failed': 0,
                               'results': [], 'errors': [str(e)]}) + '\n'
            self.wfile.write(line.encode('utf-8'))
            self.wfile.flush()
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

        output_dir = data.get('output', './output')
        total = len(jobs)
        all_results = []
        done_count = 0

        for job in jobs:
            arc_id = job.get('arc_id', '')
            results = execute_jobs(
                [job], output_dir,
                nominal_only=data.get('nominal_only', False),
                num_samples=data.get('num_samples', 5000),
                files={})
            for r in results:
                all_results.append(r)
            done_count += 1
            prog = json.dumps({
                'status': 'progress',
                'done': done_count,
                'total': total,
                'current': arc_id,
            }) + '\n'
            try:
                self.wfile.write(prog.encode('utf-8'))
                self.wfile.flush()
            except BrokenPipeError:
                return

        succeeded = sum(1 for r in all_results if r.get('success'))
        failed = sum(1 for r in all_results if not r.get('success'))
        final = json.dumps({
            'status': 'done',
            'succeeded': succeeded,
            'failed': failed,
            'results': all_results,
            'errors': errors,
        }) + '\n'
        try:
            self.wfile.write(final.encode('utf-8'))
            self.wfile.flush()
        except BrokenPipeError:
            pass

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
    parser = argparse.ArgumentParser(description='deckgen GUI v1.0')
    parser.add_argument('--port', type=int, default=8585, help='Port (default: 8585)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    args = parser.parse_args()

    server = http.server.HTTPServer(('127.0.0.1', args.port), DeckgenHandler)
    url = f'http://127.0.0.1:{args.port}'
    print(f"deckgen GUI v1.0 at {url}")
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
