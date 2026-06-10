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
