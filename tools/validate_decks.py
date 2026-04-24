"""
validate_decks.py - Compare DeckGen output against MCQC output.

CLI:
    python3 tools/validate_decks.py \
        --deckgen /path/to/deckgen/{lib}/{corner} \
        --mcqc    /path/to/mcqc/{root} \
        --arc_types delay hold mpw \
        --file nominal_sim.sp \
        --output /path/to/report/ \
        --max-detail 100

Produces report.json + report.html under --output.
"""

import argparse
import datetime
import difflib
import hashlib
import json
import os
import re
import sys


# ---------------------------------------------------------------------------
# Noise normalization
# ---------------------------------------------------------------------------

_RE_INC_ABS  = re.compile(r"(\.inc\s+['\"]?)(/[^\s'\"]+)")
_RE_COMMENT  = re.compile(
    r"^\*\s*(Created|Generated|Date:|Run|Timestamp|Version)\b", re.IGNORECASE)
_RE_SEED     = re.compile(r"(seed\s*=\s*)\d+", re.IGNORECASE)
_RE_MONTE    = re.compile(r"(monte\s*=\s*)\d+", re.IGNORECASE)
_RE_SWEEP    = re.compile(r"(sweep\s+monte\s+)\d+", re.IGNORECASE)


def _normalize_lines(lines):
    """Apply noise normalization; return list of stripped canonical lines."""
    out = []
    for ln in lines:
        # Strip trailing whitespace
        ln = ln.rstrip()
        # Skip generator/timestamp comment lines
        if _RE_COMMENT.match(ln):
            continue
        # Strip absolute paths in .inc -- keep only basename
        def _abs_to_base(m):
            return m.group(1) + os.path.basename(m.group(2))
        ln = _RE_INC_ABS.sub(_abs_to_base, ln)
        # Force seed=1
        ln = _RE_SEED.sub(r"\g<1>1", ln)
        # Force monte=1
        ln = _RE_MONTE.sub(r"\g<1>1", ln)
        # Force sweep monte count to 1
        ln = _RE_SWEEP.sub(r"\g<1>1", ln)
        out.append(ln)
    # Strip trailing blank lines
    while out and not out[-1]:
        out.pop()
    return out


def _sha256_lines(lines):
    h = hashlib.sha256()
    for ln in lines:
        h.update(ln.encode('utf-8', errors='replace'))
        h.update(b'\n')
    return h.hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Level 3 line classification
# ---------------------------------------------------------------------------

_RE_NUMERIC   = re.compile(r'^[\d.eE+\-]+[a-zA-Z]*$')
_RE_ABS_PATH  = re.compile(r'/[^\s]+')


def _classify_hunk(a_lines, b_lines):
    """Classify a diff hunk. Returns one of: path, value_numeric, comment,
    extra, missing, other."""
    a_text = ' '.join(a_lines).strip()
    b_text = ' '.join(b_lines).strip()

    if not a_lines:
        return 'extra'   # present only in b (mcqc)
    if not b_lines:
        return 'missing' # present only in a (deckgen)

    # Comment-only difference
    if all(l.lstrip().startswith('*') for l in a_lines + b_lines):
        return 'comment'

    # Path difference: strip abs paths and compare
    a_strip = _RE_ABS_PATH.sub('ABSPATH', a_text)
    b_strip = _RE_ABS_PATH.sub('ABSPATH', b_text)
    if a_strip == b_strip:
        return 'path'

    # Numeric difference: split on whitespace and '=' then compare tokens
    def tokens(s):
        parts = []
        for w in s.split():
            parts.extend(w.split('='))
        return [p for p in parts if p]

    a_toks = tokens(a_text)
    b_toks = tokens(b_text)
    if len(a_toks) == len(b_toks):
        diffs = [(a, b) for a, b in zip(a_toks, b_toks) if a != b]
        if diffs and all(_RE_NUMERIC.match(a) and _RE_NUMERIC.match(b)
                         for a, b in diffs):
            return 'value_numeric'

    return 'other'


def _level3_classify(dg_lines, mq_lines, max_detail):
    """Run unified diff and classify hunks. Returns (line_classes dict, detail_hunks list)."""
    matcher = difflib.SequenceMatcher(None, dg_lines, mq_lines, autojunk=False)
    classes = {}
    hunks = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            continue
        a_seg = dg_lines[i1:i2]
        b_seg = mq_lines[j1:j2]
        cat = _classify_hunk(a_seg, b_seg)
        classes[cat] = classes.get(cat, 0) + 1
        if len(hunks) < max_detail:
            hunks.append({
                'category': cat,
                'deckgen': a_seg[:10],
                'mcqc':    b_seg[:10],
            })

    return classes, hunks


# ---------------------------------------------------------------------------
# Pair comparison
# ---------------------------------------------------------------------------

def _compare_pair(dg_path, mq_path, filename, max_detail):
    """Compare one arc pair. Returns pair_result dict."""
    dg_file = os.path.join(dg_path, filename)
    mq_file = os.path.join(mq_path, filename)

    dg_missing = not os.path.isfile(dg_file)
    mq_missing = not os.path.isfile(mq_file)

    if dg_missing or mq_missing:
        return {
            'level': None,
            'file_missing': True,
            'deckgen_missing': dg_missing,
            'mcqc_missing':   mq_missing,
            'line_classes': {},
            'detail_hunks': [],
        }

    # Level 1: byte-identical
    dg_hash = _sha256_file(dg_file)
    mq_hash = _sha256_file(mq_file)
    if dg_hash == mq_hash:
        return {'level': 1, 'line_classes': {}, 'detail_hunks': []}

    # Level 2: normalized
    with open(dg_file, 'r', errors='replace') as f:
        dg_raw = f.readlines()
    with open(mq_file, 'r', errors='replace') as f:
        mq_raw = f.readlines()

    dg_norm = _normalize_lines(dg_raw)
    mq_norm = _normalize_lines(mq_raw)
    if _sha256_lines(dg_norm) == _sha256_lines(mq_norm):
        return {'level': 2, 'line_classes': {}, 'detail_hunks': []}

    # Level 3: classify diffs
    classes, hunks = _level3_classify(dg_norm, mq_norm, max_detail)
    return {'level': 3, 'line_classes': classes, 'detail_hunks': hunks}


# ---------------------------------------------------------------------------
# Main validate function
# ---------------------------------------------------------------------------

def validate(deckgen_root, mcqc_root, filename='nominal_sim.sp',
             arc_types=None, max_detail=100):
    """Compare DeckGen vs MCQC output trees. Returns report dict."""

    if arc_types is None:
        # Discover arc_type subdirs from both roots (union)
        found = set()
        for root in (deckgen_root, mcqc_root):
            try:
                found.update(d for d in os.listdir(root)
                             if os.path.isdir(os.path.join(root, d)))
            except OSError:
                pass
        arc_types = sorted(found)

    arc_types_data = {}
    total_pairs = 0
    total_identical = 0
    total_different = 0

    for arc_type in sorted(arc_types):
        dg_at_dir = os.path.join(deckgen_root, arc_type)
        mq_at_dir = os.path.join(mcqc_root,    arc_type)

        dg_ids = set()
        mq_ids = set()

        if os.path.isdir(dg_at_dir):
            dg_ids = {d for d in os.listdir(dg_at_dir)
                      if os.path.isdir(os.path.join(dg_at_dir, d))}
        if os.path.isdir(mq_at_dir):
            mq_ids = {d for d in os.listdir(mq_at_dir)
                      if os.path.isdir(os.path.join(mq_at_dir, d))}

        both      = dg_ids & mq_ids
        dg_only   = sorted(dg_ids - mq_ids)
        mq_only   = sorted(mq_ids - dg_ids)

        pairs_data   = []
        l1_count     = 0
        l2_count     = 0
        l3_count     = 0
        agg_classes  = {}

        for arc_id in sorted(both):
            dg_path = os.path.join(dg_at_dir, arc_id)
            mq_path = os.path.join(mq_at_dir, arc_id)
            pr = _compare_pair(dg_path, mq_path, filename, max_detail)

            if pr.get('file_missing'):
                if pr.get('deckgen_missing'):
                    dg_only_entry = arc_id + ' (file missing)'
                    dg_only.append(dg_only_entry)
                else:
                    mq_only.append(arc_id + ' (file missing)')
                continue

            total_pairs += 1
            level = pr['level']
            if level == 1:
                l1_count += 1; total_identical += 1
            elif level == 2:
                l2_count += 1; total_identical += 1
            else:
                l3_count += 1; total_different += 1

            for cat, cnt in pr.get('line_classes', {}).items():
                agg_classes[cat] = agg_classes.get(cat, 0) + cnt

            pairs_data.append({
                'arc_id':       arc_id,
                'level':        level,
                'deckgen_path': dg_path,
                'mcqc_path':    mq_path,
                'line_classes': pr.get('line_classes', {}),
                'detail_hunks': pr.get('detail_hunks', []),
            })

        arc_types_data[arc_type] = {
            'total_pairs':      l1_count + l2_count + l3_count,
            'level1_identical': l1_count,
            'level2_identical': l2_count,
            'level3_only_diffs': l3_count,
            'orphans_deckgen':  dg_only,
            'orphans_mcqc':     mq_only,
            'line_classes':     agg_classes,
            'pairs':            pairs_data,
        }

    return {
        'deckgen_root':  deckgen_root,
        'mcqc_root':     mcqc_root,
        'file':          filename,
        'generated_at':  datetime.datetime.now().isoformat(),
        'arc_types':     arc_types_data,
        'summary': {
            'total':     total_pairs,
            'identical': total_identical,
            'different': total_different,
        },
    }


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

_HTML_TMPL = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>DeckGen vs MCQC Validation Report</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
       font-size:14px; margin:0; background:#f8f8f8; color:#111; }
.topbar { background:#171717; color:#fff; padding:10px 20px; display:flex;
          align-items:baseline; gap:16px; }
.topbar h1 { font-size:16px; font-weight:600; margin:0; }
.topbar .meta { font-size:12px; color:#aaa; }
.summary { display:flex; gap:12px; padding:12px 20px; background:#fff;
           border-bottom:1px solid #e5e5e5; flex-wrap:wrap; }
.stat { background:#f4f4f4; border-radius:4px; padding:8px 16px; }
.stat .val { font-size:22px; font-weight:700; }
.stat .lbl { font-size:11px; color:#666; text-transform:uppercase; }
.filters { padding:8px 20px; background:#fff; border-bottom:1px solid #e5e5e5;
           display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.filters label { font-size:12px; }
.filters select, .filters input { font-size:12px; padding:3px 6px; border:1px solid #ccc;
                                   border-radius:3px; }
.filters button { font-size:12px; padding:3px 10px; border:1px solid #ccc;
                  border-radius:3px; cursor:pointer; background:#fff; }
table { width:100%; border-collapse:collapse; font-size:13px; }
thead th { background:#fafafa; padding:8px 10px; text-align:left; font-size:11px;
           font-weight:600; text-transform:uppercase; letter-spacing:0.04em;
           border-bottom:2px solid #e5e5e5; position:sticky; top:0; cursor:pointer; }
thead th:hover { background:#f0f0f0; }
tbody tr { border-bottom:1px solid #f0f0f0; cursor:pointer; }
tbody tr:hover { background:#fafafa; }
tbody tr.sel { background:#eff6ff; }
tbody td { padding:7px 10px; }
.l1 { color:#16a34a; font-weight:600; }
.l2 { color:#2563eb; font-weight:600; }
.l3 { color:#dc2626; font-weight:600; }
.detail { display:none; padding:10px 20px; background:#1a1a1a; }
.detail.open { display:block; }
.detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.side { font-family:monospace; font-size:11px; color:#e5e5e5; white-space:pre-wrap;
        background:#111; padding:8px; border-radius:3px; max-height:180px; overflow:auto; }
.side-lbl { font-size:10px; color:#888; margin-bottom:3px; }
.tbl-wrap { overflow:auto; max-height:calc(100vh - 220px); padding:0 20px; }
.cat-badge { display:inline-block; background:#e5e5e5; border-radius:10px;
             padding:1px 7px; font-size:11px; margin:1px; }
</style>
</head>
<body>
<div class="topbar">
  <h1>DeckGen vs MCQC Validation Report</h1>
  <span class="meta" id="gen-at"></span>
</div>
<div class="summary" id="summary-bar"></div>
<div class="filters">
  <label>Arc type: <select id="flt-at" onchange="applyFilters()"><option value="">All</option></select></label>
  <label>Level: <select id="flt-lv" onchange="applyFilters()">
    <option value="">All</option>
    <option value="1">L1 identical</option>
    <option value="2">L2 identical</option>
    <option value="3">L3 diff</option>
  </select></label>
  <label>Filter arc_id: <input type="text" id="flt-id" oninput="applyFilters()" placeholder="substring..."></label>
  <button onclick="clearFilters()">Clear</button>
</div>
<div class="tbl-wrap">
<table id="main-tbl">
<thead>
  <tr>
    <th onclick="sortBy('arc_type')">Arc Type</th>
    <th onclick="sortBy('arc_id')">Arc ID</th>
    <th onclick="sortBy('level')">Level</th>
    <th>Categories</th>
  </tr>
</thead>
<tbody id="tbody"></tbody>
</table>
</div>
<script>
var DATA = __DATA__;
var sortCol = null, sortAsc = true;
var allRows = [];

function init() {
  document.getElementById('gen-at').textContent = 'Generated: ' + (DATA.generated_at || '');
  var s = DATA.summary || {};
  var sb = document.getElementById('summary-bar');
  sb.innerHTML = stat(s.total, 'Total Pairs') + stat(s.identical, 'Identical') +
    stat(s.different, 'Different') +
    stat(pct(s.identical, s.total), 'Match Rate');

  var atSel = document.getElementById('flt-at');
  Object.keys(DATA.arc_types || {}).forEach(function(at) {
    var o = document.createElement('option');
    o.value = o.textContent = at;
    atSel.appendChild(o);
  });

  // Build flat row list
  allRows = [];
  Object.keys(DATA.arc_types || {}).forEach(function(at) {
    var atd = DATA.arc_types[at];
    (atd.pairs || []).forEach(function(p) {
      allRows.push(Object.assign({arc_type: at}, p));
    });
  });
  renderRows(allRows);
}

function stat(val, lbl) {
  return '<div class="stat"><div class="val">' + val + '</div><div class="lbl">' + lbl + '</div></div>';
}
function pct(a, b) { return b ? (100 * a / b).toFixed(1) + '%' : '--'; }

function renderRows(rows) {
  var tb = document.getElementById('tbody');
  tb.innerHTML = '';
  rows.forEach(function(row, idx) {
    var tr = document.createElement('tr');
    tr.id = 'row-' + idx;
    tr.onclick = function() { toggleDetail(tr, row, idx); };
    var lv = row.level;
    var lvcls = lv === 1 ? 'l1' : lv === 2 ? 'l2' : 'l3';
    var lvtxt = lv === 1 ? 'L1 identical' : lv === 2 ? 'L2 identical' : 'L3 diff';
    var cats = Object.keys(row.line_classes || {}).map(function(c) {
      return '<span class="cat-badge">' + c + ':' + row.line_classes[c] + '</span>';
    }).join(' ');
    tr.innerHTML =
      '<td>' + esc(row.arc_type) + '</td>' +
      '<td style="font-family:monospace;font-size:11px;">' + esc(row.arc_id) + '</td>' +
      '<td class="' + lvcls + '">' + lvtxt + '</td>' +
      '<td>' + (cats || '--') + '</td>';
    tb.appendChild(tr);

    var det = document.createElement('tr');
    det.id = 'det-' + idx;
    det.style.display = 'none';
    var td = document.createElement('td');
    td.colSpan = 4;
    td.style.padding = '0';
    var div = document.createElement('div');
    div.className = 'detail';
    div.id = 'detdiv-' + idx;
    if ((row.detail_hunks || []).length) {
      var html = '<div class="detail-grid">';
      row.detail_hunks.slice(0, 5).forEach(function(h) {
        html += '<div><div class="side-lbl">DeckGen [' + h.category + ']</div>';
        html += '<div class="side">' + esc((h.deckgen||[]).join('\\n')) + '</div></div>';
        html += '<div><div class="side-lbl">MCQC</div>';
        html += '<div class="side">' + esc((h.mcqc||[]).join('\\n')) + '</div></div>';
      });
      html += '</div>';
      div.innerHTML = html;
    } else {
      div.innerHTML = '<span style="color:#888;font-size:12px;">No diff hunks stored.</span>';
    }
    td.appendChild(div);
    det.appendChild(td);
    tb.appendChild(det);
  });
}

function toggleDetail(tr, row, idx) {
  var det = document.getElementById('det-' + idx);
  var div = document.getElementById('detdiv-' + idx);
  if (det.style.display === 'none') {
    det.style.display = '';
    div.classList.add('open');
    tr.classList.add('sel');
  } else {
    det.style.display = 'none';
    div.classList.remove('open');
    tr.classList.remove('sel');
  }
}

function applyFilters() {
  var at  = document.getElementById('flt-at').value;
  var lv  = document.getElementById('flt-lv').value;
  var id_ = document.getElementById('flt-id').value.toLowerCase();
  var filtered = allRows.filter(function(r) {
    if (at  && r.arc_type !== at) return false;
    if (lv  && String(r.level) !== lv) return false;
    if (id_ && r.arc_id.toLowerCase().indexOf(id_) === -1) return false;
    return true;
  });
  renderRows(filtered);
}

function clearFilters() {
  document.getElementById('flt-at').value = '';
  document.getElementById('flt-lv').value = '';
  document.getElementById('flt-id').value = '';
  renderRows(allRows);
}

function sortBy(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = true; }
  allRows.sort(function(a, b) {
    var av = a[col] || '', bv = b[col] || '';
    if (av < bv) return sortAsc ? -1 : 1;
    if (av > bv) return sortAsc ?  1 : -1;
    return 0;
  });
  applyFilters();
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

window.addEventListener('load', init);
</script>
</body>
</html>
"""


def _build_html(report):
    data_json = json.dumps(report, ensure_ascii=True)
    return _HTML_TMPL.replace('__DATA__', data_json)


# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------

def write_reports(report, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, 'report.json')
    html_path = os.path.join(output_dir, 'report.html')
    with open(json_path, 'w', encoding='ascii', errors='replace') as f:
        json.dump(report, f, indent=2, ensure_ascii=True)
    html = _build_html(report)
    with open(html_path, 'w', encoding='ascii', errors='replace') as f:
        f.write(html)
    return json_path, html_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Compare DeckGen output against MCQC output.')
    parser.add_argument('--deckgen', required=True,
                        help='DeckGen output root (lib_type/corner level)')
    parser.add_argument('--mcqc', required=True,
                        help='MCQC output root (corresponding level)')
    parser.add_argument('--arc_types', nargs='*', default=None,
                        help='Arc types to compare (default: all subdirs)')
    parser.add_argument('--file', default='nominal_sim.sp',
                        help='File to compare within each arc_id dir')
    parser.add_argument('--output', default='.',
                        help='Directory for report.html + report.json')
    parser.add_argument('--max-detail', type=int, default=100,
                        help='Max diff hunks to store per pair')
    args = parser.parse_args()

    report = validate(
        deckgen_root=args.deckgen,
        mcqc_root=args.mcqc,
        filename=args.file,
        arc_types=args.arc_types,
        max_detail=args.max_detail,
    )

    json_path, html_path = write_reports(report, args.output)

    s = report['summary']
    print(f"Total pairs:  {s['total']}")
    print(f"Identical:    {s['identical']}")
    print(f"Different:    {s['different']}")
    print(f"Report JSON:  {json_path}")
    print(f"Report HTML:  {html_path}")


if __name__ == '__main__':
    main()
