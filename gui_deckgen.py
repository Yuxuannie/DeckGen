#!/usr/bin/env python3
"""
gui_deckgen.py -- the deck-generation GUI (production side; independent of the
engine analysis GUI). Server-rendered, minimal JS, purple+gold theme.

Pick collateral (node / lib / corner / cell), choose a method, and:
  - template  : generate the combinational FMC decks via template substitution
  - generator : generate via the programmatic recipe (core.deck_recipe)
  - diff       : cross-validate the two paths (tools.deck_diff)
Results embed the interactive report (core.report) or the diff table.

  python3 gui_deckgen.py [--port 8585] [--collateral_root collateral]

All page-building and action logic is in pure functions (testable without the
HTTP layer; see tests/test_gui_deckgen.py). Stdlib only, ASCII source.
"""
from __future__ import annotations

import argparse
import html as _html
import os
import sys
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.collateral import CollateralStore
from core.parsers.template_tcl import parse_template_tcl_full
from core.report import render_html
from tools.scan_collateral import build_manifest

_DEFAULT_ROOT = "collateral"
_REPORTS = {}          # id -> report html (served to the result iframe)
_rid = [0]

THEME = """
:root{--purple:#5B3E8E;--gold:#9C7A12;--ink:#26223a;--muted:#7a748f;
 --line:#e8e3f1;--soft:#faf9fd;--bg:#f5f3fa;--green:#1f7a4d;--red:#c0392b;--amber:#9a6b00}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-size:14px;line-height:1.5;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.top{background:#fff;border-bottom:3px solid var(--gold);padding:14px 24px}
.top h1{margin:0;color:var(--purple);font-size:18px}
.top .s{color:var(--muted);font-size:12px;margin-top:2px}
.wrap{max-width:1180px;margin:18px auto;padding:0 16px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 18px;
 margin:0 0 16px;box-shadow:0 1px 3px rgba(40,30,70,.05)}
form{display:flex;flex-wrap:wrap;gap:14px 18px;align-items:flex-end}
label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted)}
select,input[type=text]{font:inherit;font-size:13px;padding:7px 9px;border:1px solid var(--line);
 border-radius:8px;background:#fff;color:var(--ink);min-width:170px}
.methods{display:flex;gap:14px;align-items:center}
.methods label{flex-direction:row;align-items:center;gap:5px;color:var(--ink);font-size:13px}
button{font:inherit;font-weight:600;font-size:13px;cursor:pointer;padding:8px 18px;border-radius:8px;
 border:1px solid var(--purple);background:var(--purple);color:#fff}
button:hover{background:#4d3479}
.muted{color:var(--muted)}
.tiles{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 14px}
.tile{border:1px solid var(--line);border-radius:10px;padding:10px 14px;text-align:center;min-width:78px}
.tile .n{font-size:22px;font-weight:700}.tile .l{font-size:11px;color:var(--muted);text-transform:uppercase}
.tile.ok .n{color:var(--green)}.tile.fail .n{color:var(--red)}.tile.diff .n{color:var(--amber)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:11px;text-transform:uppercase}
.pill{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;border:1px solid}
.pill.MATCH{color:var(--green);background:#eef6f1;border-color:#cfe6da}
.pill.DIFF,.pill.ERROR{color:var(--red);background:#fbeeec;border-color:#f1cfca}
pre{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px 12px;
 overflow:auto;font-size:12px;font-family:Menlo,Consolas,monospace;max-height:360px}
iframe{width:100%;height:1100px;border:1px solid var(--line);border-radius:10px;background:#fff}
"""


def _esc(s):
    return _html.escape("" if s is None else str(s))


def list_nodes(root):
    try:
        return sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)))
    except OSError:
        return []


def list_libs(root, node):
    try:
        return sorted(d for d in os.listdir(os.path.join(root, node))
                      if os.path.isdir(os.path.join(root, node, d)))
    except OSError:
        return []


def _store(root, node, lib):
    if not (root and node and lib):
        return None
    if not os.path.isfile(os.path.join(root, node, lib, "manifest.json")):
        try:
            build_manifest(root, node, lib)
        except Exception:
            return None
    try:
        return CollateralStore(root, node, lib, skip_autoscan=True)
    except Exception:
        return None


def list_corners(root, node, lib):
    st = _store(root, node, lib)
    try:
        return sorted(st.list_corners()) if st else []
    except Exception:
        return []


def list_cells(root, node, lib, corner):
    st = _store(root, node, lib)
    if not st or not corner:
        return []
    try:
        parsed = parse_template_tcl_full(st.get_template_tcl(corner))
        return sorted(parsed.get("cells", {}).keys())
    except Exception:
        return []


def _select(name, options, selected):
    opts = ["<option value='%s'%s>%s</option>"
            % (_esc(o), " selected" if o == selected else "", _esc(o))
            for o in options]
    if not options:
        opts = ["<option value=''>(none found)</option>"]
    return "<select name='%s'>%s</select>" % (name, "".join(opts))


def render_form(state):
    root = state.get("root") or _DEFAULT_ROOT
    nodes = list_nodes(root)
    node = state.get("node") or (nodes[0] if nodes else "")
    libs = list_libs(root, node)
    lib = state.get("lib") or (libs[0] if libs else "")
    corners = list_corners(root, node, lib)
    corner = state.get("corner") or (corners[0] if corners else "")
    cells = list_cells(root, node, lib, corner)
    cell = state.get("cell") or ""
    method = state.get("method") or "generator"

    dl = "".join("<option value='%s'>" % _esc(c) for c in cells[:5000])
    radios = "".join(
        "<label><input type='radio' name='method' value='%s'%s> %s</label>"
        % (m, " checked" if m == method else "", lbl)
        for m, lbl in (("generator", "generator"), ("template", "template"),
                       ("diff", "diff (cross-validate)")))
    return (
        "<form method='get' action='/run'>"
        "<label>collateral_root<input type='text' name='root' value='%s'></label>"
        "<label>node%s</label>"
        "<label>lib_type%s</label>"
        "<label>corner%s</label>"
        "<label>cell<input type='text' name='cell' value='%s' list='cells' "
        "placeholder='type a cell'></label>"
        "<datalist id='cells'>%s</datalist>"
        "<div class='methods'>%s</div>"
        "<button type='submit'>Run</button>"
        "</form>"
        "<div class='muted' style='margin-top:8px'>%d cell(s) in this lib/corner."
        " Method 'diff' compares template vs generator line-by-line.</div>"
        % (_esc(root), _select("node", nodes, node), _select("lib", libs, lib),
           _select("corner", corners, corner), _esc(cell), dl, radios, len(cells)))


def _tiles(pairs):
    return ("<div class='tiles'>"
            + "".join("<div class='tile %s'><div class='n'>%d</div>"
                      "<div class='l'>%s</div></div>" % (cls, n, lbl)
                      for lbl, n, cls in pairs) + "</div>")


def run_action(state):
    """Execute the chosen method. Returns (results_html, report_id_or_None)."""
    root = state.get("root") or _DEFAULT_ROOT
    node, lib = state.get("node"), state.get("lib")
    corner, cell = state.get("corner"), state.get("cell")
    method = state.get("method") or "generator"
    if not cell:
        return "<div class='muted'>Enter a cell name, then Run.</div>", None
    out = tempfile.mkdtemp(prefix="deckgen_gui_")

    if method == "diff":
        from tools.deck_diff import run as diff_run
        rows, ok = diff_run(root, node, lib, corner, [cell], out_path=None)
        nm = sum(1 for r in rows if r["status"] == "MATCH")
        nd = sum(1 for r in rows if r["status"] == "DIFF")
        ne = sum(1 for r in rows if r["status"] == "ERROR")
        body = [_tiles([("arcs", len(rows), ""), ("match", nm, "ok"),
                        ("diff", nd, "diff"), ("error", ne, "fail")])]
        body.append("<table><tr><th>arc</th><th>status</th><th>diff lines</th></tr>")
        for r in rows:
            body.append("<tr><td>%s</td><td><span class='pill %s'>%s</span></td>"
                        "<td>%d</td></tr>"
                        % (_esc(r["arc"]), r["status"], r["status"], r["ndiff"]))
        body.append("</table>")
        for r in rows:
            if r["diff"]:
                body.append("<h4>%s</h4><pre>%s</pre>"
                            % (_esc(r["arc"]), _esc(r["diff"])))
        verdict = "ALL MATCH" if ok else "DIFFERENCES FOUND"
        return ("<h3>Cross-validation: %s</h3>%s" % (verdict, "".join(body)), None)

    # template / generator -> the report
    from tools.gen_cell_report import run as gen_run
    report = gen_run(root, node, lib, corner, cell, out, method=method)
    s = report["summary"]
    _rid[0] += 1
    rid = str(_rid[0])
    _REPORTS[rid] = render_html(report)
    tiles = _tiles([("arcs", s["total"], ""), ("ok", s["ok"], "ok"),
                    ("fail", s["fail"], "fail"), ("skip", s["skip"], "")])
    return ("<h3>%s decks for %s</h3>%s"
            "<iframe src='/report?id=%s' title='report'></iframe>"
            % (_esc(method), _esc(cell), tiles, rid), rid)


def page(state, results_html=""):
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>DeckGen</title><style>%s</style></head><body>"
        "<div class='top'><h1>DeckGen -- deck generation</h1>"
        "<div class='s'>combinational FMC decks from collateral; template / "
        "generator / cross-validate</div></div>"
        "<div class='wrap'><div class='card'>%s</div>%s</div></body></html>"
        % (THEME, render_form(state),
           ("<div class='card'>%s</div>" % results_html) if results_html else ""))


# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    COLLATERAL_ROOT = _DEFAULT_ROOT

    def _send(self, body, ctype="text/html"):
        b = body.encode("ascii", "xmlcharrefreplace")
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=ascii")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/report":
            self._send(_REPORTS.get(q.get("id", ""), "<p>expired</p>"))
            return
        state = {"root": q.get("root") or self.COLLATERAL_ROOT,
                 "node": q.get("node"), "lib": q.get("lib"),
                 "corner": q.get("corner"), "cell": q.get("cell"),
                 "method": q.get("method")}
        if u.path == "/run":
            try:
                results, _ = run_action(state)
            except Exception as e:
                results = "<div style='color:#c0392b'>error: %s</div>" % _esc(e)
            self._send(page(state, results))
            return
        self._send(page(state))

    def log_message(self, *a):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="DeckGen deck-generation GUI")
    ap.add_argument("--port", type=int, default=8585)
    ap.add_argument("--collateral_root", default=_DEFAULT_ROOT)
    args = ap.parse_args(argv)
    Handler.COLLATERAL_ROOT = args.collateral_root
    print("DeckGen GUI: http://127.0.0.1:%d  (collateral_root=%s)"
          % (args.port, args.collateral_root))
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
