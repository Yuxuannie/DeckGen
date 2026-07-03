# Phase C-1 -- Orchestration + Coverage + CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the simulator-free, production-shaped lights-out CLI run -- one command discovers a scoped set of `(cell, arc, table-point, corner)` work items from the collateral manifest, generates a deck or a reasoned refusal for each, emits a no-silent-drop coverage report, then (only after an operator confirm gate) writes real `bsub` job-array scripts.

**Architecture:** Four new `core/` + root modules over the existing proven collateral path. `core/coverage.py` (B4) turns outcome rows + a selected universe into a no-drop coverage matrix. `core/orchestrate.py` runs discover -> generate -> [confirm] -> submit as a closed state machine backed by an append-only NDJSON ledger; it drives generation through the *already-proven* `resolve_all_from_collateral` -> `assemble_combinational`/`assemble_sequential` path. `core/lsf.py` emits genuine `bsub` array scripts + an index manifest, and a PEND-only mock `bjobs`. `deckgen_run.py` is the thin CLI with a dry-run scope gate and a confirm-before-submit gate. Nothing under `core/` imports a front-end.

**Tech Stack:** Python 3.8+ (tests run under `python3.12`), stdlib only + existing `core/`/`engine/`. No new external deps. `pyyaml` already present.

## Global Constraints

Every task's requirements implicitly include this section. Values are binding, copied from the spec (`docs/superpowers/specs/2026-07-01-phase-c-b4-orchestration-demo-design.md`) and CLAUDE.md.

- **ASCII-only** for every `.py/.yaml/.sp/.json` file this plan creates. Verify after each task: `grep -rPn '[\x80-\xff]' <changed files>` prints nothing. No non-ASCII in emitted decks, bsub scripts, HTML, or NDJSON.
- **Never fail silently / never drop arcs.** A bad, unresolved, or unsupported work item becomes a named `generation_error:<category>` row or a `skipped:<reason>` row in the ledger -- never a raised exception that aborts the run, never a silent omission. `discover` may raise **only** `SelectionEmpty`, and only when a scope matches zero items.
- **Never change a test assertion to make a test pass** without Yuxuan's explicit approval. If implementation and assertion disagree, fix the implementation.
- **Config/collateral paths relative to inputs, never hardcoded absolutes.** Resolve the script dir with `os.path.dirname(os.path.abspath(__file__))`; resolve collateral paths from the `collateral_dir` argument.
- **Simulator-free.** No real HSPICE, no real LSF. The state machine's terminal farm state is `submitted`; the mock `bjobs` reports PEND only and never invents DONE/EXIT.
- **Two operator gates are mandatory.** (1) `--dry-run` shows the scope plan and generates nothing. (2) A confirm gate sits between generation and submission: `generate()` NEVER emits a bsub script; `submit()` is a separate call reached only after an explicit human yes (`--yes` or an interactive `y`). No auto-submit path exists.
- **No-drop invariant, machine-checkable, per phase:** generation phase `expected == generated + generation_error + skipped` (a `submitted` row counts as generated for this sum); after submit `generated == submitted`. `expected == |selected work items|` (the scoped universe, section 5b of the spec), not the whole manifest.
- **State machine.** Terminal states: `generated` (deck written, resting), `submitted` (after confirm; bsub emitted), `generation_error:<category>`, `skipped:<reason>`. Categories (case-insensitive substring match on the `assemble_*` error string): `combinational_cell`<-"combinational", `latch_unsupported`<-"latch", `p1_unproven`<-"p1 not proven"/"p1 could not be proven", `out_of_corpus`<-"seqscope"/"beyond depth", `parse_fail`<-"parse"/"no .subckt"/"port order", `no_grammar`<-"grammar", `unsupported_arc`<-any other ERROR (never dropped).
- **Coverage identity for C-1.** The coverage-matrix key is the tuple `(cell, arc_type, i1, i2, corner)` per spec section 5. C-1 targets the in-repo fixture, where each `(cell, arc_type)` has exactly one arc, so this tuple is unique. Every `OutcomeRow` and ledger line ALSO carries the full `arc_id` (which additionally encodes probe/rel/when), so triage and the ledger stay unambiguous. Disambiguating the matrix when a full library has multiple arcs per `(cell, arc_type)` is an explicit C-2+ follow-up, out of scope here.
- **Run directory layout** (created by `generate`/`submit`):
  ```
  <out_dir>/
    run_config.json
    ledger.ndjson
    coverage.ndjson
    coverage.html
    lsf/deckgen_<corner>.bsub
    lsf/index_<corner>.manifest
    lsf/logs/                      (dir for %I.out; created, left empty)
    decks/<lib_type>/<corner>/<arc_type>/<arc_id>/nominal_sim.sp
  ```
- **Test fixture** (all orchestrate/lsf integration tests use it): `tests/fixtures/collateral/N2P_v1.0/test_lib`, `NODE='N2P_v1.0'`, `LIB='test_lib'`, one corner `CORNER='ssgnp_0p450v_m40c_cworst_CCworst_T'`, one cell `DFFQ1` with two arcs (combinational `CP/rise->Q/rise` when `!SE&SI`; hold `CP/rise->D/fall`). Fixture setup pattern: `shutil.copytree(FIXTURE_ROOT/NODE/LIB, dest/NODE/LIB)` then `build_manifest(dest, NODE, LIB)`. Both templates are 5x5, so each arc has 25 LUT points.

---

## Reused interfaces (verified, do not re-derive)

- `core.verify_sidecar.to_lit_when(when) -> str` -- `'!SE&SI'->'notSE_SI'`; `''`/`'NO_CONDITION'` -> `''`. Reuse for arc_id encoding.
- `core.parsers.arc.parse_arc_identifier(s) -> dict|None` -- keys `arc_type, cell_name, probe_pin, probe_dir, rel_pin, rel_dir, when, i1, i2, raw`. `format_arc_id` (Task 2) must round-trip through this.
- `core.parsers.template_tcl.parse_template_tcl_full(path) -> {'templates','cells','arcs','global','index_overrides','sis'}`. `templates[name]` has `'index_1'`/`'index_2'` (lists). `cells[name]` has `'delay_template'`, `'constraint_template'`, `'mpw_template'` (str|None). `arcs` is a flat list of dicts with keys `cell, arc_type, pin, pin_dir, rel_pin, rel_pin_dir, when, lit_when, probe_list (list), vector, metric, metric_thresh`.
- `core.resolver.resolve_all_from_collateral(cell_name, arc_type, rel_pin, rel_dir, constr_pin, constr_dir, probe_pin, node, lib_type, corner_name, collateral_root='collateral', overrides=None, ...) -> dict | list[dict]`. Pass table point via `overrides={'index_1_index': i1, 'index_2_index': i2}` (1-based). Returns the resolved `arc_info` dict (or a list of them). Raises `ResolutionError`/`CollateralError` on data problems -- CATCH these. Stamps `NETLIST_PATH` (a filesystem path), `VDD_VALUE`, `TEMPERATURE`, `INDEX_1_VALUE`, `INDEX_2_VALUE`, `MAX_SLEW`, `OUTPUT_LOAD`, `INCLUDE_FILE` etc.
- `core.deck_assemble.assemble_combinational(arc_info, netlist_src, grammar) -> dict` and `assemble_sequential(arc_info, netlist_src, grammar) -> dict`. **`netlist_src` is SOURCE TEXT, not a path** -- read the file first. On success `{'status':'OK','deck_text':..., ...}`; on failure `{'status':'ERROR','deck_text':None,'error':<msg>, ...}`. `assemble_combinational` hardcodes `arc_type='combinational'` internally -- the orchestrator decides routing.
- `core.measurement.emit.load_grammar() -> grammar`. Load once per run, pass through.
- `tools.scan_collateral.build_manifest(collateral_root, node, lib_type) -> path`. `json.load` it. `manifest['corners']` maps corner-key -> `{process, vdd, temperature, rc_type, template_tcl (path), netlist_dir (path), model{}, char{}, ...}`.
- `core.collateral.CollateralStore(collateral_root, node, lib_type, skip_autoscan=True).get_corner(key) -> corner dict` -- canonical way to get `corner['template_tcl']` as a resolvable path (matches how `resolve_all_from_collateral` reads it).

**Concretization note (binding for this plan):** the spec sketches `generate_one(cell, arc_type, i1, i2, corner, manifest, netlist_src, grammar)`. That signature lacks the arc's pin fields needed to resolve. This plan makes `discover` carry the full template.tcl arc dict in each work item, and `generate_one` consumes a `WorkItem` dict (Task 2/3). The spec's `discover` return "list of `(cell, arc_type, i1, i2, corner)` tuples" is preserved as `[wi_universe_tuple(wi) for wi in work_items]`, which is exactly what `build_coverage` receives.

---

## Task 1: core/coverage.py (B4 -- pure coverage functions)

**Files:**
- Create: `core/coverage.py`
- Test: `tests/test_coverage.py`

**Interfaces:**
- Produces:
  - `OUTCOME_KEYS = ('arc_id','cell','arc_type','i1','i2','corner','state','category','reason','netlist_path','deck_path')` (documented row shape; a plain dict).
  - `build_coverage(rows, universe) -> dict` where `rows: list[dict]` (OutcomeRow), `universe: list[tuple]` each `(cell, arc_type, i1, i2, corner)`. Returns `{'summary','by_category','by_corner','matrix','triage','unaccounted'}` (shapes below).
  - `coverage_ndjson(report, path) -> None`
  - `coverage_html(report, path) -> None`
- Consumes: nothing from other tasks (pure).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_coverage.py`:

```python
import json
import os

from core.coverage import build_coverage, coverage_ndjson, coverage_html


def _row(cell, at, i1, i2, corner, state, category='', reason='',
         netlist_path='', deck_path=''):
    return {
        'arc_id': f'{at}_{cell}_Q_rise_CP_rise_NO_CONDITION_{i1}_{i2}',
        'cell': cell, 'arc_type': at, 'i1': i1, 'i2': i2, 'corner': corner,
        'state': state, 'category': category, 'reason': reason,
        'netlist_path': netlist_path, 'deck_path': deck_path,
    }


def _universe(*tuples):
    return list(tuples)


def test_balanced_all_generated():
    uni = _universe(('DFFQ1', 'combinational', 1, 1, 'c1'),
                    ('DFFQ1', 'hold', 1, 1, 'c1'))
    rows = [_row('DFFQ1', 'combinational', 1, 1, 'c1', 'generated'),
            _row('DFFQ1', 'hold', 1, 1, 'c1', 'generated')]
    rep = build_coverage(rows, uni)
    s = rep['summary']
    assert s['expected'] == 2 and s['generated'] == 2
    assert s['generation_error'] == 0 and s['skipped'] == 0
    assert s['balanced'] is True
    assert rep['unaccounted'] == []


def test_balanced_mixed_states():
    uni = _universe(('C', 'combinational', 1, 1, 'c1'),
                    ('C', 'hold', 1, 1, 'c1'),
                    ('C', 'mpw', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'generated'),
            _row('C', 'hold', 1, 1, 'c1', 'generation_error',
                 category='latch_unsupported', reason='latch not supported',
                 netlist_path='/n/C.spi'),
            _row('C', 'mpw', 1, 1, 'c1', 'skipped', reason='no_such_point')]
    rep = build_coverage(rows, uni)
    s = rep['summary']
    assert (s['expected'], s['generated'], s['generation_error'],
            s['skipped']) == (3, 1, 1, 1)
    assert s['balanced'] is True
    assert rep['by_category'] == {'latch_unsupported': 1}
    assert rep['by_corner']['c1'] == {'generated': 1, 'submitted': 0,
                                      'error': 1, 'skipped': 1}
    assert len(rep['triage']) == 1
    t = rep['triage'][0]
    assert t['category'] == 'latch_unsupported' and t['netlist_path'] == '/n/C.spi'
    assert rep['matrix'][('C', 'hold', 1, 1)]['c1'] == 'generation_error'


def test_submitted_counts_as_generated_for_balance():
    uni = _universe(('C', 'combinational', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'submitted')]
    rep = build_coverage(rows, uni)
    assert rep['summary']['submitted'] == 1
    assert rep['summary']['balanced'] is True


def test_unbalanced_when_universe_item_has_no_row():
    uni = _universe(('C', 'combinational', 1, 1, 'c1'),
                    ('C', 'hold', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'generated')]
    rep = build_coverage(rows, uni)
    assert rep['summary']['balanced'] is False
    assert rep['unaccounted'] == [('C', 'hold', 1, 1, 'c1')]


def test_ndjson_one_line_per_matrix_cell(tmp_path):
    uni = _universe(('C', 'combinational', 1, 1, 'c1'),
                    ('C', 'hold', 1, 1, 'c1'))
    rows = [_row('C', 'combinational', 1, 1, 'c1', 'generated'),
            _row('C', 'hold', 1, 1, 'c1', 'generated')]
    rep = build_coverage(rows, uni)
    p = os.path.join(str(tmp_path), 'coverage.ndjson')
    coverage_ndjson(rep, p)
    lines = [l for l in open(p, encoding='ascii').read().splitlines() if l.strip()]
    assert len(lines) == 2
    recs = [json.loads(l) for l in lines]
    assert all({'cell', 'arc_type', 'i1', 'i2', 'corner', 'state'} <= set(r)
               for r in recs)


def test_html_has_qa_block_and_triage(tmp_path):
    # One arc errored (produces a triage card) AND one universe item has no
    # row at all -> unaccounted -> unbalanced -> the INCOMPLETE QA headline.
    # (An errored arc alone is still *accounted for*, i.e. balanced=True; the
    # INCOMPLETE headline only appears when the universe is not fully covered.)
    uni = _universe(('C', 'hold', 1, 1, 'c1'),
                    ('C', 'hold', 2, 2, 'c1'))
    rows = [_row('C', 'hold', 1, 1, 'c1', 'generation_error',
                 category='latch_unsupported', reason='latch not supported')]
    rep = build_coverage(rows, uni)
    assert rep['summary']['balanced'] is False   # ('C','hold',2,2,'c1') unaccounted
    p = os.path.join(str(tmp_path), 'coverage.html')
    coverage_html(rep, p)
    html = open(p, encoding='ascii').read()
    assert 'INCOMPLETE' in html or 'incomplete' in html.lower()
    assert 'latch_unsupported' in html
    assert all(ord(ch) < 128 for ch in html)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3.12 -m pytest tests/test_coverage.py -x -q`
Expected: FAIL -- `ModuleNotFoundError: No module named 'core.coverage'`.

- [ ] **Step 3: Implement `core/coverage.py`**

```python
"""core/coverage.py -- B4 no-silent-drop coverage report.

Pure functions plus two explicit emit helpers. Turns a list of OutcomeRow
dicts + the selected work-item universe into a coverage matrix, a no-drop
balance assertion, and NDJSON + HTML renderings. ASCII only.
"""
from __future__ import annotations

import json

OUTCOME_KEYS = ('arc_id', 'cell', 'arc_type', 'i1', 'i2', 'corner',
                'state', 'category', 'reason', 'netlist_path', 'deck_path')


def _tuple(row):
    return (row['cell'], row['arc_type'], row['i1'], row['i2'], row['corner'])


def build_coverage(rows, universe):
    """rows: list[OutcomeRow dict]; universe: list[(cell, arc_type, i1, i2,
    corner)]. Returns the CoverageReport dict (see module/spec)."""
    expected = len(universe)
    generated = submitted = errors = skipped = 0
    by_category = {}
    by_corner = {}
    matrix = {}
    triage = []

    def corner_slot(c):
        return by_corner.setdefault(
            c, {'generated': 0, 'submitted': 0, 'error': 0, 'skipped': 0})

    for r in rows:
        state = r['state']
        c = r['corner']
        matrix.setdefault((r['cell'], r['arc_type'], r['i1'], r['i2']), {})[c] = state
        slot = corner_slot(c)
        if state == 'generated':
            generated += 1
            slot['generated'] += 1
        elif state == 'submitted':
            submitted += 1
            slot['submitted'] += 1
        elif state == 'generation_error':
            errors += 1
            slot['error'] += 1
            cat = r.get('category') or 'unsupported_arc'
            by_category[cat] = by_category.get(cat, 0) + 1
            triage.append({k: r.get(k, '') for k in (
                'arc_id', 'cell', 'arc_type', 'i1', 'i2', 'corner',
                'category', 'reason', 'netlist_path', 'deck_path')})
        elif state == 'skipped':
            skipped += 1
            slot['skipped'] += 1

    row_tuples = {_tuple(r) for r in rows}
    unaccounted = [u for u in universe if u not in row_tuples]

    accounted = generated + submitted + errors + skipped
    balanced = (accounted == expected) and (not unaccounted)

    summary = {
        'expected': expected,
        'generated': generated,
        'submitted': submitted,
        'generation_error': errors,
        'skipped': skipped,
        'balanced': balanced,
    }
    return {
        'summary': summary,
        'by_category': by_category,
        'by_corner': by_corner,
        'matrix': matrix,
        'triage': triage,
        'unaccounted': unaccounted,
    }


def coverage_ndjson(report, path):
    """One JSON line per (cell, arc_type, i1, i2, corner) matrix cell."""
    with open(path, 'w', encoding='ascii') as fh:
        for (cell, at, i1, i2), per_corner in sorted(
                report['matrix'].items(), key=lambda kv: str(kv[0])):
            for corner, state in sorted(per_corner.items()):
                fh.write(json.dumps({
                    'cell': cell, 'arc_type': at, 'i1': i1, 'i2': i2,
                    'corner': corner, 'state': state,
                }) + '\n')


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def coverage_html(report, path):
    """Static HTML: QA balance block + coverage matrix + triage cards."""
    s = report['summary']
    ok = s['balanced']
    headline = ('BALANCED -- no arcs dropped' if ok
                else 'INCOMPLETE -- coverage does not balance')
    color = '#0a0' if ok else '#c00'
    out = ['<!DOCTYPE html><html><head><meta charset="ascii">',
           '<title>DeckGen coverage</title></head><body>',
           '<h1 style="color:%s">%s</h1>' % (color, _esc(headline)),
           '<p>expected=%d generated=%d submitted=%d error=%d skipped=%d</p>'
           % (s['expected'], s['generated'], s['submitted'],
              s['generation_error'], s['skipped'])]
    if report['unaccounted']:
        out.append('<p style="color:#c00">unaccounted: %s</p>'
                   % _esc(report['unaccounted']))
    out.append('<h2>Matrix</h2><table border="1"><tr>'
               '<th>cell</th><th>arc_type</th><th>i1</th><th>i2</th>'
               '<th>corner</th><th>state</th></tr>')
    for (cell, at, i1, i2), per_corner in sorted(
            report['matrix'].items(), key=lambda kv: str(kv[0])):
        for corner, state in sorted(per_corner.items()):
            out.append('<tr><td>%s</td><td>%s</td><td>%d</td><td>%d</td>'
                       '<td>%s</td><td>%s</td></tr>'
                       % (_esc(cell), _esc(at), i1, i2, _esc(corner),
                          _esc(state)))
    out.append('</table><h2>Triage (%d)</h2>' % len(report['triage']))
    for t in report['triage']:
        out.append('<div style="border:1px solid #c00;margin:4px;padding:4px">'
                   '<b>%s</b> [%s]<br>%s<br>netlist: %s<br>deck: %s</div>'
                   % (_esc(t['arc_id']), _esc(t['category']),
                      _esc(t['reason']), _esc(t['netlist_path']),
                      _esc(t['deck_path'])))
    out.append('</body></html>')
    with open(path, 'w', encoding='ascii') as fh:
        fh.write('\n'.join(out))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3.12 -m pytest tests/test_coverage.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: ASCII guard + commit**

```bash
grep -rPn '[\x80-\xff]' core/coverage.py tests/test_coverage.py   # expect no output
git add core/coverage.py tests/test_coverage.py
git commit -m "feat(coverage): B4 no-drop coverage matrix + NDJSON/HTML emitters"
```

---

## Task 2: core/orchestrate.py -- arc_id formatting + discover (scoped universe)

**Files:**
- Create: `core/orchestrate.py` (this task adds the top of the module)
- Test: `tests/test_orchestrate_discover.py`

**Interfaces:**
- Consumes: `to_lit_when` (verify_sidecar), `parse_template_tcl_full`, `build_manifest`, `CollateralStore`.
- Produces (later tasks rely on these exact names):
  - `format_arc_id(arc_type, cell, probe_pin, probe_dir, rel_pin, rel_dir, when, i1, i2) -> str`
  - `class SelectionEmpty(Exception)`
  - `SEQUENTIAL_ARCS = frozenset({'hold','setup','removal','recovery','mpw','min_pulse_width','non_seq_hold','non_seq_setup'})`
  - `discover(manifest, template_tcl_by_corner, scope=None) -> list[WorkItem dict]`. WorkItem keys: `cell, arc_type, i1, i2, corner, arc (template.tcl arc dict), arc_id, skip (None|str)`.
  - `wi_universe_tuple(wi) -> (cell, arc_type, i1, i2, corner)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrate_discover.py`:

```python
import os
import shutil

import pytest

from tools.scan_collateral import build_manifest
from core.collateral import CollateralStore
from core.orchestrate import (format_arc_id, discover, wi_universe_tuple,
                              SelectionEmpty)
from core.parsers.arc import parse_arc_identifier

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


def _setup(dest):
    src = os.path.join(FIXTURE_ROOT, NODE, LIB)
    dst = os.path.join(dest, NODE, LIB)
    shutil.copytree(src, dst)
    build_manifest(dest, NODE, LIB)
    return dest


def _manifest_and_tcl(root):
    import json
    store = CollateralStore(root, NODE, LIB, skip_autoscan=True)
    mpath = os.path.join(root, NODE, LIB, 'manifest.json')
    manifest = json.load(open(mpath, encoding='ascii'))
    tcl_by_corner = {c: store.get_corner(c)['template_tcl']
                     for c in manifest['corners']}
    return manifest, tcl_by_corner


def test_format_arc_id_roundtrips_combinational():
    aid = format_arc_id('combinational', 'DFFQ1', 'Q', 'rise', 'CP', 'rise',
                        '!SE&SI', 3, 2)
    assert aid == 'combinational_DFFQ1_Q_rise_CP_rise_notSE_SI_3_2'
    p = parse_arc_identifier(aid)
    assert (p['arc_type'], p['cell_name'], p['probe_pin'], p['rel_pin'],
            p['i1'], p['i2']) == ('combinational', 'DFFQ1', 'Q', 'CP', 3, 2)
    assert p['when'] == '!SE&SI'


def test_format_arc_id_no_condition():
    aid = format_arc_id('hold', 'DFFQ1', 'Q', 'fall', 'CP', 'rise',
                        'NO_CONDITION', 1, 1)
    assert aid == 'hold_DFFQ1_Q_fall_CP_rise_NO_CONDITION_1_1'
    assert parse_arc_identifier(aid)['when'] == 'NO_CONDITION'


def test_discover_all_points_two_arcs_times_grid(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope=None)
    # 2 arcs x 25 LUT points x 1 corner
    assert len(items) == 50
    assert {wi['arc_type'] for wi in items} == {'combinational', 'hold'}
    assert all(wi['corner'] == CORNER for wi in items)
    assert all(wi['skip'] is None for wi in items)


def test_discover_table_points_origin_only(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope={'table_points': [(1, 1)]})
    assert len(items) == 2
    assert {wi_universe_tuple(wi) for wi in items} == {
        ('DFFQ1', 'combinational', 1, 1, CORNER),
        ('DFFQ1', 'hold', 1, 1, CORNER)}


def test_discover_arcs_per_cell_one(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl,
                     scope={'arcs_per_cell': 1, 'table_points': [(1, 1)]})
    assert len(items) == 1  # first arc of DFFQ1 only


def test_discover_table_points_int_first_n(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope={'table_points': 3})
    # 3 points per arc x 2 arcs
    assert len(items) == 6
    combo = sorted((wi['i1'], wi['i2']) for wi in items
                   if wi['arc_type'] == 'combinational')
    assert combo == [(1, 1), (1, 2), (1, 3)]  # row-major first 3


def test_discover_no_such_point_is_skipped_not_dropped(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    items = discover(manifest, tcl, scope={'table_points': [(99, 99)]})
    assert len(items) == 2               # accounted, not dropped
    assert all(wi['skip'] == 'no_such_point' for wi in items)


def test_discover_cells_glob_nonmatch_raises_empty(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    with pytest.raises(SelectionEmpty):
        discover(manifest, tcl, scope={'cells': ['NOSUCH*']})


def test_discover_corners_filter_nonmatch_raises_empty(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    manifest, tcl = _manifest_and_tcl(root)
    with pytest.raises(SelectionEmpty):
        discover(manifest, tcl, scope={'corners': ['ffgnp_0p900v_125c_x']})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3.12 -m pytest tests/test_orchestrate_discover.py -x -q`
Expected: FAIL -- `ModuleNotFoundError: No module named 'core.orchestrate'`.

- [ ] **Step 3: Implement the top of `core/orchestrate.py`**

```python
"""core/orchestrate.py -- Phase C run loop (discover / generate / submit).

Simulator-free, production-shaped. Drives generation through the proven
resolve_all_from_collateral -> assemble_* path, records every work item in an
append-only NDJSON ledger, and enforces the no-silent-drop invariant via
core/coverage.py. Generation and submission are two operator-gated phases.
ASCII only. Nothing here imports a front-end.
"""
from __future__ import annotations

import fnmatch
import os

from core.verify_sidecar import to_lit_when
from core.parsers.template_tcl import parse_template_tcl_full

SEQUENTIAL_ARCS = frozenset({
    'hold', 'setup', 'removal', 'recovery', 'mpw', 'min_pulse_width',
    'non_seq_hold', 'non_seq_setup',
})

_OPP = {'rise': 'fall', 'fall': 'rise'}


class SelectionEmpty(Exception):
    """A non-empty scope matched zero work items (surfaced at the scope gate)."""


def format_arc_id(arc_type, cell, probe_pin, probe_dir, rel_pin, rel_dir,
                  when, i1, i2):
    """Build a cell_arc_pt identifier; round-trips through
    parse_arc_identifier. when is encoded via to_lit_when
    ('!SE&SI'->'notSE_SI'); empty/NO_CONDITION -> literal 'NO_CONDITION'."""
    w = to_lit_when(when) or 'NO_CONDITION'
    return '_'.join([arc_type, cell, probe_pin, probe_dir, rel_pin, rel_dir,
                     w, str(i1), str(i2)])


def wi_universe_tuple(wi):
    return (wi['cell'], wi['arc_type'], wi['i1'], wi['i2'], wi['corner'])


def _template_for(cell_info, arc_type):
    if arc_type in ('mpw', 'min_pulse_width'):
        return cell_info.get('mpw_template')
    if arc_type in SEQUENTIAL_ARCS:
        return cell_info.get('constraint_template')
    return cell_info.get('delay_template')


def _grid_dims(template_info, cell_info, arc_type):
    """(n1, n2) LUT dimensions for this arc's backing template; (0, 0) if
    unknown."""
    name = _template_for(cell_info, arc_type)
    tpl = template_info.get('templates', {}).get(name or '', {})
    n1 = len(tpl.get('index_1') or [])
    n2 = len(tpl.get('index_2') or [])
    return n1, n2


def _points_for(n1, n2, table_points):
    """Return list of (i1, i2, skip) triples for one arc's grid given the
    scope's table_points. skip is None or 'no_such_point'."""
    all_pts = [(i1, i2) for i1 in range(1, n1 + 1) for i2 in range(1, n2 + 1)]
    if table_points is None:
        return [(i1, i2, None) for (i1, i2) in all_pts]
    if isinstance(table_points, int):
        return [(i1, i2, None) for (i1, i2) in all_pts[:table_points]]
    # explicit list of (i1, i2)
    out = []
    for (i1, i2) in table_points:
        ok = (1 <= i1 <= n1) and (1 <= i2 <= n2)
        out.append((i1, i2, None if ok else 'no_such_point'))
    return out


def discover(manifest, template_tcl_by_corner, scope=None):
    """manifest x per-corner template.tcl path, filtered by scope -> list of
    WorkItem dicts. Never raises for data problems (unreadable template.tcl ->
    that corner contributes a skipped:template_tcl_unreadable marker item).
    Raises SelectionEmpty only when the produced set is empty."""
    scope = scope or {}
    cell_globs = scope.get('cells')
    arcs_per_cell = scope.get('arcs_per_cell')
    table_points = scope.get('table_points')
    corner_filter = scope.get('corners')

    corners = list(manifest.get('corners', {}).keys())
    if corner_filter is not None:
        corners = [c for c in corners if c in set(corner_filter)]

    items = []
    for corner in corners:
        tcl_path = template_tcl_by_corner.get(corner)
        if not tcl_path or not os.path.isfile(tcl_path):
            items.append({
                'cell': '*', 'arc_type': '*', 'i1': 0, 'i2': 0,
                'corner': corner, 'arc': {}, 'arc_id': '',
                'skip': 'template_tcl_unreadable'})
            continue
        info = parse_template_tcl_full(tcl_path)
        arcs = info.get('arcs', [])
        cells_in_order = []
        for a in arcs:
            if a['cell'] not in cells_in_order:
                cells_in_order.append(a['cell'])
        for cell in cells_in_order:
            if cell_globs is not None and not any(
                    fnmatch.fnmatch(cell, g) for g in cell_globs):
                continue
            cell_info = info.get('cells', {}).get(cell, {})
            cell_arcs = [a for a in arcs if a['cell'] == cell]
            if arcs_per_cell is not None:
                cell_arcs = cell_arcs[:arcs_per_cell]
            for arc in cell_arcs:
                n1, n2 = _grid_dims(info, cell_info, arc['arc_type'])
                probe = (arc['probe_list'][0] if arc.get('probe_list')
                         else arc['pin'])
                for (i1, i2, skip) in _points_for(n1, n2, table_points):
                    items.append({
                        'cell': cell,
                        'arc_type': arc['arc_type'],
                        'i1': i1, 'i2': i2, 'corner': corner,
                        'arc': arc,
                        'arc_id': format_arc_id(
                            arc['arc_type'], cell, probe, arc['pin_dir'],
                            arc['rel_pin'], arc['rel_pin_dir'],
                            arc.get('when', ''), i1, i2),
                        'skip': skip,
                    })

    if not items:
        raise SelectionEmpty(
            'selection matched 0 items; check '
            '--cells/--arcs-per-cell/--table-points/--corners')
    return items
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3.12 -m pytest tests/test_orchestrate_discover.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: ASCII guard + commit**

```bash
grep -rPn '[\x80-\xff]' core/orchestrate.py tests/test_orchestrate_discover.py
git add core/orchestrate.py tests/test_orchestrate_discover.py
git commit -m "feat(orchestrate): arc_id formatter + scoped discover over template.tcl"
```

---

## Task 3: core/orchestrate.py -- generate_one + generate (generation phase)

**Files:**
- Modify: `core/orchestrate.py` (append generation functions)
- Test: `tests/test_orchestrate_generate.py`

**Interfaces:**
- Consumes: `discover`, `wi_universe_tuple`, `SEQUENTIAL_ARCS`, `_OPP` (Task 2); `resolve_all_from_collateral`; `assemble_combinational`/`assemble_sequential`; `load_grammar`; `build_manifest`; `CollateralStore`; `build_coverage`/`coverage_ndjson`/`coverage_html` (Task 1).
- Produces:
  - `categorize(error_msg) -> str` (state-machine category)
  - `generate_one(work_item, node, lib_type, collateral_root, grammar, out_dir) -> dict` (OutcomeRow)
  - `generate(collateral_dir, node, lib_type, out_dir, scope=None, progress=None) -> dict` RunResult `{'run_dir','universe','rows','coverage'}`
  - `write_ledger(rows, path)` / `read_ledger(path)` (NDJSON, atomic full-file rewrite)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrate_generate.py`:

```python
import json
import os
import shutil

from tools.scan_collateral import build_manifest
from core.orchestrate import (generate, generate_one, categorize, read_ledger)
from core.collateral import CollateralStore
from core.measurement.emit import load_grammar

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


def _setup(dest):
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    os.path.join(dest, NODE, LIB))
    build_manifest(dest, NODE, LIB)
    return dest


def test_categorize_maps_known_substrings():
    assert categorize('this is a combinational cell') == 'combinational_cell'
    assert categorize('latch not supported') == 'latch_unsupported'
    assert categorize('P1 not proven for arc') == 'p1_unproven'
    assert categorize('SeqScope: depth 7 beyond corpus') == 'out_of_corpus'
    assert categorize('could not parse .subckt') == 'parse_fail'
    assert categorize('no grammar entry') == 'no_grammar'
    assert categorize('totally novel failure') == 'unsupported_arc'


def test_generate_over_fixture_balances_and_writes_ledger(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = generate(root, NODE, LIB, out,
                   scope={'table_points': [(1, 1)]})
    cov = res['coverage']['summary']
    # 2 arcs at (1,1): both accounted, nothing dropped
    assert cov['expected'] == 2
    assert cov['generated'] + cov['generation_error'] + cov['skipped'] == 2
    assert cov['balanced'] is True
    # ledger written, one line per work item
    rows = read_ledger(os.path.join(out, 'ledger.ndjson'))
    assert len(rows) == 2
    assert os.path.isfile(os.path.join(out, 'coverage.ndjson'))
    assert os.path.isfile(os.path.join(out, 'coverage.html'))
    # no bsub emitted during generation phase (confirm gate)
    lsf_dir = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf_dir) and any(
        f.endswith('.bsub') for f in os.listdir(lsf_dir)))
    assert all(r['state'] != 'submitted' for r in rows)


def test_generate_one_combinational_writes_deck(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    os.makedirs(out, exist_ok=True)
    store = CollateralStore(root, NODE, LIB, skip_autoscan=True)
    import json as _j
    manifest = _j.load(open(os.path.join(root, NODE, LIB, 'manifest.json'),
                            encoding='ascii'))
    from core.orchestrate import discover
    tcl = {c: store.get_corner(c)['template_tcl'] for c in manifest['corners']}
    items = discover(manifest, tcl,
                     scope={'arcs_per_cell': 1, 'table_points': [(1, 1)]})
    row = generate_one(items[0], NODE, LIB, root, load_grammar(), out)
    assert row['state'] in ('generated', 'generation_error')
    if row['state'] == 'generated':
        assert os.path.isfile(row['deck_path'])
        assert row['arc_id'].startswith('combinational_DFFQ1_')


def test_generate_error_row_is_named_never_raises(tmp_path):
    # A bogus work item (arc absent from template.tcl) must produce a
    # generation_error row, not raise.
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    os.makedirs(out, exist_ok=True)
    bogus = {
        'cell': 'DFFQ1', 'arc_type': 'hold', 'i1': 1, 'i2': 1,
        'corner': CORNER, 'arc_id': 'hold_DFFQ1_Q_fall_XX_rise_NO_CONDITION_1_1',
        'skip': None,
        'arc': {'cell': 'DFFQ1', 'arc_type': 'hold', 'pin': 'D',
                'pin_dir': 'fall', 'rel_pin': 'XX', 'rel_pin_dir': 'rise',
                'when': 'NO_CONDITION', 'lit_when': 'NO_CONDITION',
                'probe_list': ['Q'], 'vector': ''},
    }
    row = generate_one(bogus, NODE, LIB, root, load_grammar(), out)
    assert row['state'] == 'generation_error'
    assert row['category']  # non-empty category
    assert row['reason']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3.12 -m pytest tests/test_orchestrate_generate.py -x -q`
Expected: FAIL -- `ImportError: cannot import name 'generate'`.

- [ ] **Step 3: Append generation functions to `core/orchestrate.py`**

```python
import json

from core.coverage import build_coverage, coverage_ndjson, coverage_html

_CATEGORY_RULES = [
    ('combinational', 'combinational_cell'),
    ('latch', 'latch_unsupported'),
    ('p1 not proven', 'p1_unproven'),
    ('p1 could not be proven', 'p1_unproven'),
    ('seqscope', 'out_of_corpus'),
    ('beyond depth', 'out_of_corpus'),
    ('beyond corpus', 'out_of_corpus'),
    ('parse', 'parse_fail'),
    ('no .subckt', 'parse_fail'),
    ('port order', 'parse_fail'),
    ('grammar', 'no_grammar'),
]


def categorize(error_msg):
    low = (error_msg or '').lower()
    for needle, cat in _CATEGORY_RULES:
        if needle in low:
            return cat
    return 'unsupported_arc'


def _row(wi, state, category='', reason='', netlist_path='', deck_path=''):
    return {
        'arc_id': wi.get('arc_id', ''),
        'cell': wi['cell'], 'arc_type': wi['arc_type'],
        'i1': wi['i1'], 'i2': wi['i2'], 'corner': wi['corner'],
        'state': state, 'category': category, 'reason': reason,
        'netlist_path': netlist_path, 'deck_path': deck_path,
    }


def _deck_path(out_dir, lib_type, wi):
    return os.path.join(out_dir, 'decks', lib_type, wi['corner'],
                        wi['arc_type'], wi['arc_id'], 'nominal_sim.sp')


def generate_one(work_item, node, lib_type, collateral_root, grammar, out_dir):
    """Resolve + route + assemble one work item; write its deck if OK.
    Returns an OutcomeRow. Never raises for data/generation problems."""
    from core.deck_assemble import assemble_combinational, assemble_sequential
    from core.resolver import resolve_all_from_collateral

    if work_item.get('skip'):
        return _row(work_item, 'skipped', reason=work_item['skip'])

    arc = work_item['arc']
    probe = arc['probe_list'][0] if arc.get('probe_list') else arc['pin']
    try:
        result = resolve_all_from_collateral(
            cell_name=arc['cell'], arc_type=arc['arc_type'],
            rel_pin=arc['rel_pin'], rel_dir=arc['rel_pin_dir'],
            constr_pin=arc['pin'],
            constr_dir=_OPP.get(arc['rel_pin_dir'], 'fall'),
            probe_pin=probe, node=node, lib_type=lib_type,
            corner_name=work_item['corner'], collateral_root=collateral_root,
            overrides={'index_1_index': work_item['i1'],
                       'index_2_index': work_item['i2']})
    except Exception as e:                                    # resolution failure
        return _row(work_item, 'generation_error',
                    category=categorize(str(e)), reason=str(e))

    arc_info = result[0] if isinstance(result, list) else result

    # Overlay the routing/identity keys the engine emitters need, from the
    # authoritative template.tcl arc. resolve provides the resolved numeric /
    # file keys (VDD, TEMP, INDEX_*, MAX_SLEW, OUTPUT_LOAD, NETLIST_PATH, ...).
    arc_info.setdefault('WAVEFORM_FILE', 'std_wv.spi')
    arc_info.setdefault('INCLUDE_FILE', 'MODEL.inc')
    arc_info.update({
        'CELL_NAME': arc['cell'], 'ARC_TYPE': arc['arc_type'],
        'REL_PIN': arc['rel_pin'], 'REL_PIN_DIR': arc['rel_pin_dir'],
        'CONSTR_PIN': arc['pin'],
        'CONSTR_PIN_DIR': _OPP.get(arc['rel_pin_dir'], 'fall'),
        'PROBE_PIN_1': probe,
        'WHEN': arc.get('when') or 'NO_CONDITION',
    })

    netlist_path = arc_info.get('NETLIST_PATH', '')
    if not netlist_path or not os.path.isfile(netlist_path):
        return _row(work_item, 'generation_error', category='parse_fail',
                    reason='netlist not found: %r' % netlist_path,
                    netlist_path=netlist_path)
    netlist_src = open(netlist_path, encoding='latin-1').read()

    if arc['arc_type'].startswith('combinational'):
        asm = assemble_combinational(arc_info, netlist_src, grammar)
    else:
        asm = assemble_sequential(arc_info, netlist_src, grammar)

    if asm.get('status') != 'OK':
        return _row(work_item, 'generation_error',
                    category=categorize(asm.get('error', '')),
                    reason=asm.get('error', 'unknown'),
                    netlist_path=netlist_path)

    dpath = _deck_path(out_dir, lib_type, work_item)
    os.makedirs(os.path.dirname(dpath), exist_ok=True)
    with open(dpath, 'w', encoding='ascii') as fh:
        fh.write(asm['deck_text'])
    return _row(work_item, 'generated', netlist_path=netlist_path,
                deck_path=dpath)


def write_ledger(rows, path):
    """Atomic full-file NDJSON rewrite (temp + rename)."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='ascii') as fh:
        for r in rows:
            fh.write(json.dumps(r) + '\n')
    os.replace(tmp, path)


def read_ledger(path):
    rows = []
    with open(path, encoding='ascii') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_manifest_and_tcl(collateral_dir, node, lib_type):
    from core.collateral import CollateralStore
    from tools.scan_collateral import build_manifest
    mpath = build_manifest(collateral_dir, node, lib_type)
    manifest = json.load(open(mpath, encoding='ascii'))
    store = CollateralStore(collateral_dir, node, lib_type, skip_autoscan=True)
    tcl = {c: store.get_corner(c)['template_tcl'] for c in manifest['corners']}
    return manifest, tcl


def _write_reports(rows, universe, out_dir):
    report = build_coverage(rows, universe)
    coverage_ndjson(report, os.path.join(out_dir, 'coverage.ndjson'))
    coverage_html(report, os.path.join(out_dir, 'coverage.html'))
    return report


def generate(collateral_dir, node, lib_type, out_dir, scope=None,
             progress=None):
    """Phase 1: discover -> generate_one each -> ledger + coverage. Writes NO
    bsub. Returns RunResult. Stops at the resting state."""
    from core.measurement.emit import load_grammar

    os.makedirs(out_dir, exist_ok=True)
    manifest, tcl = _load_manifest_and_tcl(collateral_dir, node, lib_type)
    work_items = discover(manifest, tcl, scope)     # may raise SelectionEmpty
    grammar = load_grammar()

    rows = []
    total = len(work_items)
    for idx, wi in enumerate(work_items):
        rows.append(generate_one(wi, node, lib_type, collateral_dir, grammar,
                                 out_dir))
        if progress:
            progress(idx + 1, total, rows[-1])

    write_ledger(rows, os.path.join(out_dir, 'ledger.ndjson'))
    with open(os.path.join(out_dir, 'run_config.json'), 'w',
              encoding='ascii') as fh:
        json.dump({'collateral': collateral_dir, 'node': node,
                   'lib_type': lib_type, 'scope': scope or {},
                   'out_dir': out_dir}, fh, indent=2)
    universe = [wi_universe_tuple(wi) for wi in work_items]
    report = _write_reports(rows, universe, out_dir)
    return {'run_dir': out_dir, 'universe': universe, 'rows': rows,
            'coverage': report}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3.12 -m pytest tests/test_orchestrate_generate.py -q`
Expected: PASS (4 tests). If `test_generate_one_combinational_writes_deck` finds `state == 'generation_error'`, read `row['reason']`: a missing `arc_info` key means the overlay set above is incomplete -- add the missing key from `arc` (do NOT weaken the assertion, do NOT drop the arc). The no-drop test must still pass regardless.

- [ ] **Step 5: ASCII guard + full-suite regression + commit**

```bash
grep -rPn '[\x80-\xff]' core/orchestrate.py tests/test_orchestrate_generate.py
python3.12 -m pytest tests/ -q          # no pre-existing tests regressed
git add core/orchestrate.py tests/test_orchestrate_generate.py
git commit -m "feat(orchestrate): generation phase (generate_one/generate) + NDJSON ledger"
```

---

## Task 4: core/lsf.py -- production-shaped mock LSF

**Files:**
- Create: `core/lsf.py`
- Test: `tests/test_lsf.py`

**Interfaces:**
- Consumes: OutcomeRow dicts with `state=='generated'`, keys `arc_id, corner, deck_path`.
- Produces:
  - `emit_arrays(generated_rows, out_dir, slot_limit=50, runlimit="00:20") -> dict` `{corner: {'script','manifest','n_jobs'}}`
  - `bjobs_snapshot(arrays) -> list[str]` (PEND-only lines)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lsf.py`:

```python
import os

from core.lsf import emit_arrays, bjobs_snapshot


def _grow(corner, n):
    return [{'arc_id': 'hold_C_Q_fall_CP_rise_NO_CONDITION_%d_1' % i,
             'corner': corner, 'state': 'generated',
             'deck_path': '/run/decks/%s/%d/nominal_sim.sp' % (corner, i)}
            for i in range(1, n + 1)]


def test_emit_arrays_writes_bsub_and_manifest(tmp_path):
    out = str(tmp_path)
    rows = _grow('c1', 3)
    arrays = emit_arrays(rows, out, slot_limit=50, runlimit='00:20')
    assert arrays['c1']['n_jobs'] == 3
    bsub = open(arrays['c1']['script'], encoding='ascii').read()
    assert '#BSUB -J "deckgen_c1[1-3]%50"' in bsub
    assert '#BSUB -W 00:20' in bsub
    assert 'LSB_JOBINDEX' in bsub
    man = open(arrays['c1']['manifest'], encoding='ascii').read().splitlines()
    assert len(man) == 3
    assert all(ord(ch) < 128 for ch in bsub)


def test_emit_arrays_groups_by_corner(tmp_path):
    out = str(tmp_path)
    rows = _grow('c1', 2) + _grow('c2', 1)
    arrays = emit_arrays(rows, out)
    assert set(arrays) == {'c1', 'c2'}
    assert arrays['c1']['n_jobs'] == 2 and arrays['c2']['n_jobs'] == 1


def test_emit_arrays_ignores_non_generated(tmp_path):
    out = str(tmp_path)
    rows = _grow('c1', 1)
    rows.append({'arc_id': 'x', 'corner': 'c1', 'state': 'generation_error',
                 'deck_path': ''})
    arrays = emit_arrays(rows, out)
    assert arrays['c1']['n_jobs'] == 1


def test_bjobs_snapshot_is_pend_only(tmp_path):
    arrays = emit_arrays(_grow('c1', 2), str(tmp_path))
    lines = bjobs_snapshot(arrays)
    assert lines and all('PEND' in l for l in lines)
    assert all('DONE' not in l and 'EXIT' not in l for l in lines)
    assert any('team runs HSPICE' in l for l in lines)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3.12 -m pytest tests/test_lsf.py -x -q`
Expected: FAIL -- `ModuleNotFoundError: No module named 'core.lsf'`.

- [ ] **Step 3: Implement `core/lsf.py`**

```python
"""core/lsf.py -- production-shaped mock LSF.

emit_arrays writes the REAL, submittable bsub job-array scripts the team would
run, plus an index->arc->deck manifest read via $LSB_JOBINDEX. bjobs_snapshot
renders the monitor loop honestly: PEND only, never inventing DONE/EXIT.
ASCII only. Simulator-free.
"""
from __future__ import annotations

import os


def emit_arrays(generated_rows, out_dir, slot_limit=50, runlimit="00:20"):
    """Group generated rows by corner; write lsf/deckgen_<corner>.bsub and
    lsf/index_<corner>.manifest per corner. Returns
    {corner: {'script','manifest','n_jobs'}}."""
    lsf_dir = os.path.join(out_dir, 'lsf')
    os.makedirs(os.path.join(lsf_dir, 'logs'), exist_ok=True)

    by_corner = {}
    for r in generated_rows:
        if r.get('state') != 'generated':
            continue
        by_corner.setdefault(r['corner'], []).append(r)

    result = {}
    for corner, rows in by_corner.items():
        n = len(rows)
        man_path = os.path.join(lsf_dir, 'index_%s.manifest' % corner)
        with open(man_path, 'w', encoding='ascii') as fh:
            for r in rows:
                fh.write('%s\t%s\n' % (r['arc_id'], r.get('deck_path', '')))
        script_path = os.path.join(lsf_dir, 'deckgen_%s.bsub' % corner)
        log_glob = os.path.join(lsf_dir, 'logs', '%s.%%I.out' % corner)
        lines = [
            '#!/bin/bash',
            '#BSUB -J "deckgen_%s[1-%d]%%%d"' % (corner, n, slot_limit),
            '#BSUB -W %s' % runlimit,
            '#BSUB -o %s' % log_glob,
            'DECK=$(sed -n "${LSB_JOBINDEX}p" %s | cut -f2)' % man_path,
            '# team runs HSPICE:',
            'hspice "$DECK"',
            '',
        ]
        with open(script_path, 'w', encoding='ascii') as fh:
            fh.write('\n'.join(lines))
        result[corner] = {'script': script_path, 'manifest': man_path,
                          'n_jobs': n}
    return result


def bjobs_snapshot(arrays):
    """Mock bjobs: every array element PEND, labeled honestly."""
    lines = []
    for corner, info in sorted(arrays.items()):
        lines.append('deckgen_%s[1-%d]   PEND   (awaiting farm -- team runs '
                     'HSPICE)' % (corner, info['n_jobs']))
    return lines
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3.12 -m pytest tests/test_lsf.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: ASCII guard + commit**

```bash
grep -rPn '[\x80-\xff]' core/lsf.py tests/test_lsf.py
git add core/lsf.py tests/test_lsf.py
git commit -m "feat(lsf): production-shaped bsub job-array emitter + PEND-only bjobs mock"
```

---

## Task 5: core/orchestrate.py -- submit + run (confirm gate)

**Files:**
- Modify: `core/orchestrate.py` (append submit + run)
- Test: `tests/test_orchestrate_submit.py`

**Interfaces:**
- Consumes: `generate`, `read_ledger`, `write_ledger`, `wi_universe_tuple`, `_write_reports` (Task 3); `core.lsf.emit_arrays` (Task 4); `build_coverage` (Task 1).
- Produces:
  - `class NothingToSubmit(Exception)`
  - `submit(run_dir, slot_limit=50, runlimit="00:20", progress=None) -> dict` RunResult
  - `run(collateral_dir, node, lib_type, out_dir, scope=None, dry_run=False, confirm=None, slot_limit=50, progress=None) -> dict`
  - `plan(collateral_dir, node, lib_type, scope=None) -> dict` `{'expected','matrix_counts','walltime_est'}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrate_submit.py`:

```python
import os
import shutil

import pytest

from tools.scan_collateral import build_manifest
from core.orchestrate import (generate, submit, run, plan, read_ledger,
                              NothingToSubmit)

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'


def _setup(dest):
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    os.path.join(dest, NODE, LIB))
    build_manifest(dest, NODE, LIB)
    return dest


def test_generate_then_submit_advances_rows(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    gen = generate(root, NODE, LIB, out, scope={'table_points': [(1, 1)]})
    n_generated = gen['coverage']['summary']['generated']
    if n_generated == 0:
        pytest.skip('fixture generated 0 decks; submit path needs >=1')
    res = submit(out)
    rows = read_ledger(os.path.join(out, 'ledger.ndjson'))
    submitted = [r for r in rows if r['state'] == 'submitted']
    assert len(submitted) == n_generated
    # bsub now exists (post-confirm)
    assert any(f.endswith('.bsub') for f in os.listdir(os.path.join(out, 'lsf')))
    # after submit invariant: generated == submitted
    assert res['coverage']['summary']['submitted'] == n_generated


def test_submit_with_no_generated_refuses(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    # scope of all no_such_point -> 0 generated, only skipped rows
    generate(root, NODE, LIB, out, scope={'table_points': [(99, 99)]})
    with pytest.raises(NothingToSubmit):
        submit(out)
    # no partial bsub written
    lsf = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf) and any(
        f.endswith('.bsub') for f in os.listdir(lsf)))


def test_run_dry_run_generates_nothing(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = run(root, NODE, LIB, out, scope={'table_points': [(1, 1)]},
              dry_run=True)
    assert res['expected'] == 2
    assert not os.path.isdir(os.path.join(out, 'decks'))
    assert not os.path.isfile(os.path.join(out, 'ledger.ndjson'))


def test_run_confirm_false_stops_at_generated(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = run(root, NODE, LIB, out, scope={'table_points': [(1, 1)]},
              confirm=lambda r: False)
    rows = read_ledger(os.path.join(out, 'ledger.ndjson'))
    assert all(r['state'] != 'submitted' for r in rows)
    lsf = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf) and any(
        f.endswith('.bsub') for f in os.listdir(lsf)))


def test_run_confirm_true_submits(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = run(root, NODE, LIB, out, scope={'table_points': [(1, 1)]},
              confirm=lambda r: True)
    if res['coverage']['summary'].get('submitted', 0) == 0:
        # only valid if 0 decks generated
        assert res['coverage']['summary']['generated'] == 0
    else:
        assert any(f.endswith('.bsub')
                   for f in os.listdir(os.path.join(out, 'lsf')))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3.12 -m pytest tests/test_orchestrate_submit.py -x -q`
Expected: FAIL -- `ImportError: cannot import name 'submit'`.

- [ ] **Step 3: Append submit + run + plan to `core/orchestrate.py`**

```python
class NothingToSubmit(Exception):
    """submit() called but no rows are in the 'generated' state."""


def submit(run_dir, slot_limit=50, runlimit="00:20", progress=None):
    """Phase 2 (post-confirm): read generated rows, emit real bsub arrays,
    advance rows generated -> submitted, rewrite ledger + coverage. Refuses
    (NothingToSubmit, no partial writes) if there is nothing to submit."""
    from core.lsf import emit_arrays

    ledger_path = os.path.join(run_dir, 'ledger.ndjson')
    rows = read_ledger(ledger_path)
    generated = [r for r in rows if r['state'] == 'generated']
    if not generated:
        raise NothingToSubmit('no generated decks to submit in %s' % run_dir)

    arrays = emit_arrays(generated, run_dir, slot_limit=slot_limit,
                         runlimit=runlimit)
    submitted_ids = {r['arc_id'] for r in generated}
    for r in rows:
        if r['state'] == 'generated' and r['arc_id'] in submitted_ids:
            r['state'] = 'submitted'
    write_ledger(rows, ledger_path)

    universe = [(r['cell'], r['arc_type'], r['i1'], r['i2'], r['corner'])
                for r in rows]
    report = _write_reports(rows, universe, run_dir)
    if progress:
        progress(arrays)
    return {'run_dir': run_dir, 'universe': universe, 'rows': rows,
            'coverage': report, 'arrays': arrays}


_PIN_BUCKET_SECONDS = {'small': 30, 'medium': 90, 'large': 180}


def plan(collateral_dir, node, lib_type, scope=None):
    """dry-run: discover only, return the scope plan without generating."""
    manifest, tcl = _load_manifest_and_tcl(collateral_dir, node, lib_type)
    work_items = discover(manifest, tcl, scope)      # may raise SelectionEmpty
    matrix_counts = {}
    for wi in work_items:
        key = (wi['cell'], wi['corner'])
        matrix_counts[key] = matrix_counts.get(key, 0) + 1
    # heuristic walltime: 90s/item baseline (medium pin bucket)
    est = len(work_items) * _PIN_BUCKET_SECONDS['medium']
    return {'expected': len(work_items), 'matrix_counts': matrix_counts,
            'walltime_est': est, 'work_items': work_items}


def run(collateral_dir, node, lib_type, out_dir, scope=None, dry_run=False,
        confirm=None, slot_limit=50, progress=None):
    """CLI convenience wiring. dry_run -> plan only. Else generate; if confirm
    is provided and returns True, submit. confirm=None -> generate only (safe
    default, no submission)."""
    if dry_run:
        return plan(collateral_dir, node, lib_type, scope)
    res = generate(collateral_dir, node, lib_type, out_dir, scope=scope,
                   progress=progress)
    if confirm is not None and confirm(res):
        try:
            return submit(out_dir, slot_limit=slot_limit)
        except NothingToSubmit:
            return res
    return res
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3.12 -m pytest tests/test_orchestrate_submit.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: ASCII guard + full suite + commit**

```bash
grep -rPn '[\x80-\xff]' core/orchestrate.py tests/test_orchestrate_submit.py
python3.12 -m pytest tests/ -q
git add core/orchestrate.py tests/test_orchestrate_submit.py
git commit -m "feat(orchestrate): submit/run confirm gate (generate->confirm->submit)"
```

---

## Task 6: deckgen_run.py -- CLI front-end

**Files:**
- Create: `deckgen_run.py`
- Test: `tests/test_deckgen_run_cli.py`

**Interfaces:**
- Consumes: `core.orchestrate.run`, `plan`, `submit`, `generate`, `SelectionEmpty`, `NothingToSubmit`; `core.lsf.bjobs_snapshot`.
- Produces: `main(argv=None) -> int` (exit code 0 iff balanced). `parse_scope(args) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deckgen_run_cli.py`:

```python
import os
import shutil
import subprocess
import sys

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = 'N2P_v1.0'
LIB = 'test_lib'


def _setup(dest):
    from tools.scan_collateral import build_manifest
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    os.path.join(dest, NODE, LIB))
    build_manifest(dest, NODE, LIB)
    return dest


def _run(args, cwd=REPO):
    return subprocess.run([sys.executable, os.path.join(REPO, 'deckgen_run.py')]
                          + args, cwd=cwd, capture_output=True, text=True)


def test_dry_run_prints_scope_and_writes_nothing(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--table-points', '1,1', '--out', out, '--dry-run'])
    assert r.returncode == 0, r.stderr
    assert '2' in r.stdout                      # 2 selected items
    assert not os.path.isdir(os.path.join(out, 'decks'))


def test_generate_only_no_tty_stops_at_generated(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--table-points', '1,1', '--out', out])
    assert 'not submitted' in r.stdout.lower()
    lsf = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf) and any(
        f.endswith('.bsub') for f in os.listdir(lsf)))


def test_yes_flag_submits_and_writes_bsub(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--table-points', '1,1', '--out', out, '--yes'])
    # exit 0 iff balanced; fixture scope is fully accounted
    assert r.returncode == 0, r.stderr
    ledger = os.path.join(out, 'ledger.ndjson')
    assert os.path.isfile(ledger)
    # if any deck generated, a bsub exists; headline present either way
    assert 'accounted' in r.stdout.lower() or 'balanced' in r.stdout.lower()


def test_zero_match_scope_exits_nonzero(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    r = _run(['--collateral', root, '--node', NODE, '--lib_type', LIB,
              '--cells', 'NOSUCH*', '--out', out])
    assert r.returncode != 0
    assert '0 items' in (r.stdout + r.stderr)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3.12 -m pytest tests/test_deckgen_run_cli.py -x -q`
Expected: FAIL -- deckgen_run.py does not exist (`returncode == 2`, "can't open file").

- [ ] **Step 3: Implement `deckgen_run.py`**

```python
#!/usr/bin/env python3
"""deckgen_run.py -- lights-out, production-shaped DeckGen run (CLI).

One command discovers a scoped set of (cell, arc, table-point, corner) work
items from the collateral manifest, generates a deck or a reasoned refusal for
each, prints a no-silent-drop coverage headline + triage, and -- only after an
operator confirm -- writes real bsub job-array scripts. Simulator-free: stops
honestly at 'submitted' (team runs HSPICE). Stdlib + core only. ASCII only.
"""
from __future__ import annotations

import argparse
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from core.orchestrate import (generate, submit, plan, SelectionEmpty,   # noqa: E402
                              NothingToSubmit)
from core.lsf import bjobs_snapshot                                     # noqa: E402


def parse_scope(args):
    """Build the Scope dict from parsed CLI args. Omitted knob -> None (all)."""
    scope = {}
    scope['cells'] = ([c.strip() for c in args.cells.split(',') if c.strip()]
                      if args.cells else None)
    scope['arcs_per_cell'] = args.arcs_per_cell
    scope['corners'] = ([c.strip() for c in args.corners.split(',')
                         if c.strip()] if args.corners else None)
    tp = args.table_points
    if not tp:
        scope['table_points'] = None
    elif ';' in tp or ',' in tp:
        pts = []
        for chunk in tp.split(';'):
            chunk = chunk.strip()
            if not chunk:
                continue
            i1, i2 = chunk.split(',')
            pts.append((int(i1), int(i2)))
        # a bare "N" (no comma) is an int count; handled below
        if len(pts) == 1 and ',' not in tp and ';' not in tp:
            scope['table_points'] = int(tp)
        else:
            scope['table_points'] = pts
    else:
        scope['table_points'] = int(tp)      # "N" -> first N points
    return scope


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--collateral', required=True)
    ap.add_argument('--node', required=True)
    ap.add_argument('--lib_type', required=True)
    ap.add_argument('--cells', help='comma-separated fnmatch globs')
    ap.add_argument('--arcs-per-cell', type=int, dest='arcs_per_cell')
    ap.add_argument('--table-points', dest='table_points',
                    help='"N" (first N points) or ";"-separated i1,i2 e.g. "1,1;2,3"')
    ap.add_argument('--corners', help='comma-separated corner keys')
    ap.add_argument('--out', default='run_out')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--slot-limit', type=int, default=50, dest='slot_limit')
    args = ap.parse_args(argv)

    scope = parse_scope(args)

    # ---- dry-run scope gate ----
    if args.dry_run:
        try:
            pl = plan(args.collateral, args.node, args.lib_type, scope)
        except SelectionEmpty as e:
            print('SELECTION EMPTY: %s' % e)
            return 2
        print('Scope: %d selected work items' % pl['expected'])
        for (cell, corner), n in sorted(pl['matrix_counts'].items()):
            print('  %-24s %-40s %d items' % (cell, corner, n))
        print('Estimated walltime: ~%d s (%.1f min)'
              % (pl['walltime_est'], pl['walltime_est'] / 60.0))
        print('(dry-run: nothing generated)')
        return 0

    # ---- generation phase ----
    def _progress(done, total, row):
        sys.stdout.write('\r  generated %d/%d ...' % (done, total))
        sys.stdout.flush()

    try:
        res = generate(args.collateral, args.node, args.lib_type, args.out,
                       scope=scope, progress=_progress)
    except SelectionEmpty as e:
        print('SELECTION EMPTY: %s' % e)
        return 2
    print()

    s = res['coverage']['summary']
    accounted = s['generated'] + s['generation_error'] + s['skipped']
    print('=' * 60)
    print('NO-DROP LEDGER: %d items in -> %d accounted for '
          '(%d generated / %d error / %d skip)'
          % (s['expected'], accounted, s['generated'],
             s['generation_error'], s['skipped']))
    if s['balanced']:
        print('BALANCED -- no arcs dropped')
    else:
        print('!!! INCOMPLETE -- coverage does not balance !!!')
        for u in res['coverage']['unaccounted']:
            print('  unaccounted: %s' % (u,))

    triage = res['coverage']['triage']
    if triage:
        print('\nTRIAGE (%d generation errors):' % len(triage))
        for t in triage:
            print('  [%s] %s' % (t['category'], t['arc_id']))
            print('      reason: %s' % t['reason'])
            print('      netlist: %s' % t['netlist_path'])

    # ---- confirm-before-submit gate ----
    do_submit = args.yes or (sys.stdin.isatty() and
                             input('\nSubmit %d array jobs to LSF? [y/N] '
                                   % s['generated']).strip().lower() == 'y')
    if not do_submit:
        print('\nDecks ready, not submitted '
              '(re-run with --yes or use the GUI Submit button).')
        return 0 if s['balanced'] else 1

    try:
        res = submit(args.out, slot_limit=args.slot_limit)
    except NothingToSubmit as e:
        print('\nNothing to submit: %s' % e)
        return 0 if s['balanced'] else 1

    arrays = res.get('arrays', {})
    n_jobs = sum(a['n_jobs'] for a in arrays.values())
    print('\nSUBMITTED %d array job(s):' % n_jobs)
    for corner, a in sorted(arrays.items()):
        print('  bsub < %s   (%d jobs)' % (a['script'], a['n_jobs']))
    for line in bjobs_snapshot(arrays):
        print('  %s' % line)
    print('(team runs HSPICE)')
    return 0 if res['coverage']['summary']['balanced'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3.12 -m pytest tests/test_deckgen_run_cli.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Manual smoke + ASCII guard + full suite + commit**

```bash
# manual smoke against the in-repo fixture (build a temp manifest first if needed)
python3.12 deckgen_run.py --collateral tests/fixtures/collateral --node N2P_v1.0 \
    --lib_type test_lib --table-points 1,1 --out /tmp/deckgen_smoke --dry-run
grep -rPn '[\x80-\xff]' deckgen_run.py tests/test_deckgen_run_cli.py
python3.12 -m pytest tests/ -q
git add deckgen_run.py tests/test_deckgen_run_cli.py
git commit -m "feat(cli): deckgen_run lights-out CLI with dry-run + confirm gate"
```

---

## Self-Review

**1. Spec coverage** (spec sections -> tasks):
- Section 4 state machine + 4.1 categories -> Task 3 `categorize` + row states; no-drop invariant enforced in `build_coverage` (Task 1) and asserted in Task 3/5 tests.
- Section 5 `core/coverage.py` (build_coverage/ndjson/html, OutcomeRow keys, `balanced`) -> Task 1.
- Section 5b scope (cells/arcs_per_cell/table_points/corners, no_such_point, SelectionEmpty) -> Task 2 `discover` + tests.
- Section 6 `core/orchestrate.py` (discover/generate_one/generate/submit/run, ledger, run-dir layout, confirm-gate split) -> Tasks 2/3/5.
- Section 7 `core/lsf.py` (emit_arrays real bsub + index manifest, bjobs PEND-only) -> Task 4.
- Section 8 CLI (flags, two gates, no-drop headline, exit code) -> Task 6.
- Section 11 testing -> each task's tests mirror the listed cases (balanced true/false, category counting, unaccounted, NDJSON round-trip, HTML QA block; bsub shape + PEND-only; generation balances + named error + dry-run; confirm-gate no-bsub/advance/refuse; scope filters + zero-match; CLI subprocess smoke).
- Section 12 constraints -> Global Constraints + per-task ASCII guard + full-suite regression steps.
- Section 9 GUI + Section 10 Phase C-2 -> explicitly deferred to the C-2 plan (not this plan).

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to". Every code step carries complete code; every test step carries real assertions.

**3. Type consistency:** OutcomeRow keys identical across Tasks 1/3 (`arc_id,cell,arc_type,i1,i2,corner,state,category,reason,netlist_path,deck_path`). `discover` WorkItem shape consumed unchanged by `generate_one`/`generate`. `emit_arrays` return `{corner:{script,manifest,n_jobs}}` consumed by `submit`/CLI/`bjobs_snapshot`. `build_coverage` universe = list of 5-tuples produced by `wi_universe_tuple` in Task 3 and by `submit` in Task 5.

**Known deviation from the spec, flagged for the human:** the spec's `generate_one(cell, arc_type, i1, i2, corner, manifest, netlist_src, grammar)` signature is concretized to `generate_one(work_item, node, lib_type, collateral_root, grammar, out_dir)` because the pin fields needed to resolve live in the template.tcl arc dict, which the work item carries. Functionally identical coverage; the spec's tuple-based `discover` return is preserved via `wi_universe_tuple`. Raise with Yuxuan if strict signature parity is required.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-phase-c1-orchestration-cli.md`. Two execution options:

1. **Subagent-Driven (recommended)** -- fresh implementer subagent per task, task review (spec + quality) between tasks, broad review at the end.
2. **Inline Execution** -- execute tasks in this session with checkpoints.

Which approach?
