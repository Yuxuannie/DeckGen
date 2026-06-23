"""report.py -- turn a batch deck-generation run into a structured report dict
plus a self-contained interactive HTML report.

Pure functions, stdlib only. Never raises to the caller for a single bad row:
a malformed row is recorded as status ERROR with a reason, not raised.

Public API:
    build_report(rows, context) -> dict
    render_html(report) -> str   (complete <!doctype...></html> document)
"""

import html as _html

# Canonical statuses. Anything else is normalized to ERROR.
_STATUSES = ("OK", "FAIL", "SKIP", "ERROR")

# Row field order used for the per-arc results table.
_ROW_FIELDS = (
    "cell", "arc_type", "rel_pin", "rel_dir", "probe_pin", "constr_dir",
    "when", "corner", "template", "status", "reason",
    "index_1", "index_2", "deck_path", "deck_text",
)


def _s(value):
    """Coerce any value to a plain string ('' for None)."""
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _basename(path):
    """Return the trailing component of a path-like string (no os dependency)."""
    p = _s(path)
    if not p:
        return ""
    p = p.replace("\\", "/")
    return p.rsplit("/", 1)[-1]


def _normalize_status(raw):
    s = _s(raw).strip().upper()
    if s in _STATUSES:
        return s
    return "ERROR"


def _normalize_row(raw):
    """Normalize one input row into a dict with every _ROW_FIELDS key.

    Returns (row_dict, error_reason_or_None). Never raises: if the input is not
    a mapping or otherwise unusable, error_reason explains why and the row is
    forced to status ERROR.
    """
    row = {f: "" for f in _ROW_FIELDS}

    if not isinstance(raw, dict):
        row["status"] = "ERROR"
        row["reason"] = "malformed row: not a dict (got %s)" % type(raw).__name__
        return row, row["reason"]

    err = None
    try:
        for f in _ROW_FIELDS:
            row[f] = _s(raw.get(f))
        # template is stored as a basename for display.
        row["template"] = _basename(raw.get("template"))
        row["status"] = _normalize_status(raw.get("status"))
        if _s(raw.get("status")).strip().upper() not in _STATUSES \
                and _s(raw.get("status")).strip() != "":
            err = "unknown status %r normalized to ERROR" % _s(raw.get("status"))
        if _s(raw.get("status")).strip() == "":
            row["status"] = "ERROR"
            err = "missing status, recorded as ERROR"
    except Exception as e:  # defensive: never propagate
        row["status"] = "ERROR"
        err = "row normalization error: %s" % e
        row["reason"] = err

    if err and not row.get("reason"):
        row["reason"] = err
    return row, err


def _empty_counts():
    return {"ok": 0, "fail": 0, "skip": 0, "error": 0}


def _bump(counts, status):
    key = status.lower()
    if key not in counts:
        counts[key] = 0
    counts[key] += 1


def _mentions_template(reason):
    return "template" in _s(reason).lower()


def build_report(rows, context):
    """Build a structured report dict from per-arc rows.

    rows: list of per-arc dicts (see module docstring / task spec).
    context: dict of optional provenance strings.

    Returns a JSON-serializable dict (see task spec for shape). Never raises on a
    malformed row -- it is counted as ERROR with a reason.
    """
    if rows is None:
        rows = []
    if not isinstance(context, dict):
        context = {}

    norm_rows = []
    summary = {
        "total": 0,
        "ok": 0, "fail": 0, "skip": 0, "error": 0,
        "by_arc_type": {},
        "by_cell": {},
        "by_status": {},
    }
    failures = []
    warnings = []
    unmatched_templates = []
    _seen_templates = set()

    for raw in (rows if isinstance(rows, (list, tuple)) else [rows]):
        row, _err = _normalize_row(raw)
        norm_rows.append(row)

        status = row["status"]
        summary["total"] += 1
        _bump(summary, status)
        summary["by_status"][status] = summary["by_status"].get(status, 0) + 1

        at = row["arc_type"] or "(unknown)"
        cell = row["cell"] or "(unknown)"
        summary["by_arc_type"].setdefault(at, _empty_counts())
        summary["by_cell"].setdefault(cell, _empty_counts())
        _bump(summary["by_arc_type"][at], status)
        _bump(summary["by_cell"][cell], status)

        if status in ("FAIL", "ERROR"):
            failures.append(row)

        if status == "SKIP":
            reason = row["reason"] or "(no reason given)"
            warnings.append("SKIP %s/%s: %s" % (cell, at, reason))

        # Collect distinct templates referenced by template-related failures.
        if _mentions_template(row["reason"]):
            tmpl = row["template"] or "(unspecified template)"
            if tmpl not in _seen_templates:
                _seen_templates.add(tmpl)
                unmatched_templates.append(tmpl)
            if status not in ("FAIL", "ERROR", "SKIP"):
                warnings.append(
                    "template issue for %s/%s: %s" % (cell, at, row["reason"]))

    return {
        "summary": summary,
        "failures": failures,
        "warnings": warnings,
        "rows": norm_rows,
        "unmatched_templates": unmatched_templates,
        "context": context,
    }


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CSS = """
:root{
 --purple:#5B3E8E;--purple2:#7E5BB5;--gold:#9C7A12;--ink:#26223a;--muted:#7a748f;
 --line:#e8e3f1;--soft:#faf9fd;--bg:#f5f3fa;--green:#1f7a4d;--red:#c0392b;--amber:#9a6b00;
}
*{box-sizing:border-box}
body{margin:0;padding:30px 16px;background:var(--bg);color:var(--ink);
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 font-size:14px;line-height:1.55}
.wrap{max-width:1040px;margin:0 auto}
a{color:var(--purple)}
h1{font-size:21px;margin:0;color:var(--purple);letter-spacing:.2px}
.sub{color:var(--muted);margin:6px 0 0;font-size:13px}
.verdict{background:#fff;border:1px solid var(--line);border-top:3px solid var(--gold);
 border-radius:14px;padding:20px 22px;margin:0 0 16px;box-shadow:0 1px 3px rgba(40,30,70,.05)}
.vhead{display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap}
.vhead .grow{flex:1 1 auto}
.badge{display:inline-block;padding:4px 13px;border-radius:999px;font-weight:600;font-size:12px;white-space:nowrap}
.badge.ok{color:var(--green);background:#eef6f1;border:1px solid #cfe6da}
.badge.fail{color:var(--red);background:#fbeeec;border:1px solid #f1cfca}
.badge.warn{color:var(--amber);background:#fbf4e6;border:1px solid #ecdcb8}
.badge.neutral{color:var(--muted);background:var(--soft);border:1px solid var(--line)}
.tiles{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 0}
.tile{flex:1 1 84px;border:1px solid var(--line);border-radius:10px;padding:12px 8px;text-align:center;background:#fff}
.tile .n{font-size:25px;font-weight:700;line-height:1}
.tile .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:5px}
.tile.total .n{color:var(--purple)}.tile.ok .n{color:var(--green)}
.tile.fail .n{color:var(--red)}.tile.skip .n{color:var(--amber)}.tile.error .n{color:var(--red)}
.controls{display:flex;gap:8px;margin:0 0 14px}
.controls button{font:inherit;font-size:12px;cursor:pointer;padding:6px 13px;background:#fff;
 color:var(--purple);border:1px solid var(--line);border-radius:8px}
.controls button:hover{background:var(--soft);border-color:#d9d0ea}
summary{list-style:none}summary::-webkit-details-marker{display:none}
.tw{display:inline-block;color:var(--gold);font-size:11px;transition:transform .12s;flex:0 0 auto}
details[open]>summary .tw{transform:rotate(90deg)}
details.card{background:#fff;border:1px solid var(--line);border-radius:12px;margin:0 0 12px;
 box-shadow:0 1px 3px rgba(40,30,70,.04);overflow:hidden}
details.card>summary{cursor:pointer;padding:14px 18px;display:flex;align-items:center;gap:10px;
 font-weight:600;color:var(--purple);user-select:none}
details.card>summary:hover{background:var(--soft)}
.ctitle{flex:0 1 auto}.count{margin-left:auto;color:var(--muted);font-weight:400;font-size:12px}
.card-body{padding:2px 18px 18px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
.st{font-weight:600}.st.OK{color:var(--green)}.st.FAIL,.st.ERROR{color:var(--red)}.st.SKIP{color:var(--amber)}
.reason{color:var(--red)}
.warn-list{margin:0;padding-left:18px}.warn-list li{color:var(--amber);margin:3px 0}
.empty{color:var(--muted);font-style:italic;padding:6px 0}
.minis{display:flex;flex-wrap:wrap;gap:26px;align-items:flex-start}
table.mini{border-collapse:collapse;font-size:12px}
table.mini caption{text-align:left;font-weight:600;color:var(--purple);padding:0 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
table.mini th,table.mini td{padding:3px 12px 3px 0;text-align:left;border:none}
table.mini th{color:var(--muted);font-weight:600}
.scrollbox{max-height:320px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 12px;background:var(--soft)}
details.arc{border:1px solid var(--line);border-radius:10px;margin:8px 0;background:#fff}
details.arc>summary{cursor:pointer;padding:10px 14px;display:flex;align-items:center;gap:11px;user-select:none;flex-wrap:wrap}
details.arc>summary:hover{background:var(--soft)}
.pill{font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;border:1px solid}
.pill.OK{color:var(--green);background:#eef6f1;border-color:#cfe6da}
.pill.FAIL,.pill.ERROR{color:var(--red);background:#fbeeec;border-color:#f1cfca}
.pill.SKIP{color:var(--amber);background:#fbf4e6;border-color:#ecdcb8}
.cell{font-weight:600}
.adir{color:var(--muted);font-family:Menlo,Consolas,monospace;font-size:12px}
.awhen{color:var(--muted);font-size:12px;margin-left:auto}
.arc-body{padding:6px 14px 14px}
dl.kv{margin:0 0 10px;display:grid;grid-template-columns:max-content 1fr;gap:3px 14px;font-size:12px}
dl.kv dt{color:var(--muted)}dl.kv dd{margin:0;word-break:break-all}
pre.deck{margin:0;padding:12px 14px;background:var(--soft);color:#2c2740;border:1px solid var(--line);
 border-radius:8px;overflow:auto;font-size:12px;line-height:1.5;white-space:pre;max-height:460px;
 font-family:Menlo,Consolas,monospace}
"""

_JS = """
(function(){
  function setAll(open){
    var ds=document.querySelectorAll('details');
    for(var i=0;i<ds.length;i++){ds[i].open=open;}
  }
  var ex=document.getElementById('expand-all');
  var co=document.getElementById('collapse-all');
  if(ex){ex.addEventListener('click',function(){setAll(true);});}
  if(co){co.addEventListener('click',function(){setAll(false);});}
})();
"""


def _esc(value):
    """HTML-escape a value (quotes included), coercing to string first.

    Also escapes any non-ASCII code point to a numeric character reference so the
    rendered document is guaranteed ASCII-only (latin-1 locale safety).
    """
    s = _html.escape(_s(value), quote=True)
    if all(ord(c) < 128 for c in s):
        return s
    out = []
    for c in s:
        if ord(c) < 128:
            out.append(c)
        else:
            out.append("&#%d;" % ord(c))
    return "".join(out)


def _status_badge_class(summary):
    if summary.get("fail", 0) or summary.get("error", 0):
        return "fail"
    if summary.get("skip", 0):
        return "warn"
    if summary.get("total", 0):
        return "ok"
    return "neutral"


def _status_word(summary):
    if summary.get("fail", 0) or summary.get("error", 0):
        return "ACTION REQUIRED"
    if summary.get("skip", 0):
        return "PASS WITH SKIPS"
    if summary.get("total", 0):
        return "ALL OK"
    return "NO ROWS"


def _tile(label, n, cls):
    return ('<div class="tile %s"><div class="n">%d</div>'
            '<div class="l">%s</div></div>') % (cls, int(n), _esc(label))


def _mini_table(caption, mapping):
    parts = ['<table class="mini"><caption>%s</caption>' % _esc(caption)]
    parts.append('<tr><th>name</th><th>ok</th><th>fail</th>'
                 '<th>skip</th><th>err</th></tr>')
    if not mapping:
        parts.append('<tr><td colspan="5" class="empty">none</td></tr>')
    for name in sorted(mapping.keys()):
        c = mapping[name]
        parts.append(
            '<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td></tr>'
            % (_esc(name), c.get("ok", 0), c.get("fail", 0),
               c.get("skip", 0), c.get("error", 0)))
    parts.append('</table>')
    return "".join(parts)


def _card(title, body_html, count_text="", collapsed=True):
    op = "" if collapsed else " open"
    cnt = ('<span class="count">%s</span>' % _esc(count_text)) if count_text else ""
    return ('<details class="card"%s><summary><span class="tw">&#9656;</span>'
            '<span class="ctitle">%s</span>%s</summary>'
            '<div class="card-body">%s</div></details>'
            % (op, _esc(title), cnt, body_html))


def _failures_body(failures):
    if not failures:
        return '<div class="empty">No failures or errors.</div>'
    parts = ['<table><tr><th>cell</th><th>arc</th><th>rel</th>'
             '<th>probe</th><th>corner</th><th>status</th>'
             '<th>reason</th></tr>']
    for r in failures:
        parts.append(
            '<tr><td>%s</td><td>%s</td><td>%s/%s</td><td>%s/%s</td>'
            '<td>%s</td><td class="st %s">%s</td>'
            '<td class="reason">%s</td></tr>'
            % (_esc(r["cell"]), _esc(r["arc_type"]),
               _esc(r["rel_pin"]), _esc(r["rel_dir"]),
               _esc(r["probe_pin"]), _esc(r["constr_dir"]),
               _esc(r["corner"]), _esc(r["status"]), _esc(r["status"]),
               _esc(r["reason"])))
    parts.append('</table>')
    return "".join(parts)


def _warnings_body(warnings, unmatched):
    parts = []
    if unmatched:
        parts.append('<p>Unmatched / empty templates:</p>')
        parts.append('<ul class="warn-list">')
        for t in unmatched:
            parts.append('<li>%s</li>' % _esc(t))
        parts.append('</ul>')
    if warnings:
        parts.append('<ul class="warn-list">')
        for w in warnings:
            parts.append('<li>%s</li>' % _esc(w))
        parts.append('</ul>')
    if not parts:
        return '<div class="empty">No warnings.</div>'
    return "".join(parts)


def _arc_rows_body(rows):
    if not rows:
        return '<div class="empty">No arcs.</div>'
    parts = []
    for r in rows:
        summary = (
            '<span class="tw">&#9656;</span>'
            '<span class="pill %s">%s</span>'
            '<span class="cell">%s</span>'
            '<span class="adir">%s %s &#8594; %s %s</span>'
            '<span class="awhen">when %s</span>'
            % (_esc(r["status"]), _esc(r["status"]), _esc(r["cell"]),
               _esc(r["rel_pin"]), _esc(r["rel_dir"]),
               _esc(r["probe_pin"]), _esc(r["constr_dir"]), _esc(r["when"])))
        kv = ['<dl class="kv">']
        for label, key in (("template", "template"), ("corner", "corner"),
                           ("index_1", "index_1"), ("index_2", "index_2"),
                           ("deck_path", "deck_path"), ("reason", "reason")):
            kv.append('<dt>%s</dt><dd>%s</dd>' % (_esc(label), _esc(r[key])))
        kv.append('</dl>')
        deck = r["deck_text"]
        deck_html = ('<pre class="deck">%s</pre>' % _esc(deck)) if deck \
            else '<div class="empty">No deck text.</div>'
        parts.append('<details class="arc"><summary>%s</summary>'
                     '<div class="arc-body">%s%s</div></details>'
                     % (summary, "".join(kv), deck_html))
    return "".join(parts)


def _context_body(context):
    keys = ("node", "lib_type", "corner", "collateral_root", "output_dir",
            "tool_version")
    extra = [k for k in context.keys() if k not in keys]
    ordered = list(keys) + sorted(extra)
    parts = ['<dl class="kv">']
    any_val = False
    for k in ordered:
        if k in context:
            parts.append('<dt>%s</dt><dd>%s</dd>' % (_esc(k), _esc(context[k])))
            any_val = True
    parts.append('</dl>')
    if not any_val:
        return '<div class="empty">No provenance recorded.</div>'
    return "".join(parts)


def render_html(report):
    """Render a complete self-contained HTML document for a report dict.

    Accepts the dict returned by build_report. Defensive: missing keys default
    to empty. Returns an ASCII-only string from '<!doctype' to '</html>'.
    """
    if not isinstance(report, dict):
        report = {}
    summary = report.get("summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    failures = report.get("failures") or []
    warnings = report.get("warnings") or []
    rows = report.get("rows") or []
    unmatched = report.get("unmatched_templates") or []
    context = report.get("context") or {}
    if not isinstance(context, dict):
        context = {}

    total = int(summary.get("total", 0))
    n_ok = int(summary.get("ok", 0))
    n_fail = int(summary.get("fail", 0))
    n_skip = int(summary.get("skip", 0))
    n_err = int(summary.get("error", 0))

    badge_cls = _status_badge_class(summary)
    word = _status_word(summary)

    # Section 1: headline verdict (always visible).
    verdict = ['<div class="verdict">']
    verdict.append('<div class="vhead"><div class="grow">')
    verdict.append('<h1>Deck Generation Report</h1>')
    verdict.append('<p class="sub">Coverage summary across %d arc%s.</p>'
                   % (total, "" if total == 1 else "s"))
    verdict.append('</div>')
    verdict.append('<span class="badge %s">%s</span>' % (badge_cls, _esc(word)))
    verdict.append('</div>')
    verdict.append('<div class="tiles">')
    verdict.append(_tile("total", total, "total"))
    verdict.append(_tile("ok", n_ok, "ok"))
    verdict.append(_tile("fail", n_fail, "fail"))
    verdict.append(_tile("skip", n_skip, "skip"))
    verdict.append(_tile("error", n_err, "error"))
    verdict.append('</div>')
    verdict.append('</div>')

    # Coverage breakdown (by type / by cell) -- collapsible + scrollable, since a
    # run may have thousands of cells.
    by_cell = summary.get("by_cell", {})
    breakdown = ('<div class="minis">%s'
                 '<div><div class="scrollbox">%s</div></div></div>'
                 % (_mini_table("By arc type", summary.get("by_arc_type", {})),
                    _mini_table("By cell", by_cell)))

    n_actionable = n_fail + n_err
    sections = []
    # Section 2: failures (expanded by default).
    sections.append(_card(
        "Failures and errors", _failures_body(failures),
        count_text="%d row%s" % (n_actionable, "" if n_actionable == 1 else "s"),
        collapsed=False))
    # Section 3: coverage breakdown by type / cell (collapsed; scrollable).
    sections.append(_card(
        "Coverage breakdown -- by type / by cell", breakdown,
        count_text="%d cell%s" % (len(by_cell), "" if len(by_cell) == 1 else "s"),
        collapsed=True))
    # Section 4: warnings (collapsed).
    sections.append(_card(
        "Warnings", _warnings_body(warnings, unmatched),
        count_text="%d" % (len(warnings) + len(unmatched)),
        collapsed=True))
    # Section 4: per-arc results (collapsed).
    sections.append(_card(
        "Per-arc results", _arc_rows_body(rows),
        count_text="%d arc%s" % (len(rows), "" if len(rows) == 1 else "s"),
        collapsed=True))
    # Section 5: environment / provenance (collapsed).
    sections.append(_card(
        "Environment / provenance", _context_body(context),
        collapsed=True))

    controls = ('<div class="controls">'
                '<button id="expand-all" type="button">Expand all</button>'
                '<button id="collapse-all" type="button">Collapse all</button>'
                '</div>')

    doc = [
        "<!doctype html>",
        '<html lang="en"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Deck Generation Report</title>",
        "<style>%s</style>" % _CSS,
        "</head><body><div class=\"wrap\">",
        "".join(verdict),
        controls,
        "".join(sections),
        "</div>",
        "<script>%s</script>" % _JS,
        "</body></html>",
    ]
    return "".join(doc)
