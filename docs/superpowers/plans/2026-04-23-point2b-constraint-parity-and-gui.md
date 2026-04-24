# Point 2b (Constraint Parity) + Point 5 (GUI Polish) -- Combined Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** Finish MCQC parity for constraint arcs (hold/setup/removal/recovery/mpw/si_immunity) and redesign the GUI to expose the new `(node, lib_type, corner)` workflow from Point 2a. After this, DeckGen covers all MCQC arc types and has a usable GUI for batch validation.

**Architecture:**
- Part A (2b Constraint Parity): extend `core/parsers/template_tcl.py`, `core/arc_info_builder.py`, `core/resolver.py`, `core/batch.py`, `core/deck_builder.py` with: 3D constraint expansion, `define_index` overrides, SIS template parser, per-arc `metric`/`metric_thresh`, MPW skip logic.
- Part B (GUI Polish): rebuild `gui.py` with a two-column layout, node/lib_type dropdowns populated from collateral manifests, batch + single modes, live preview, corner autofill, and a collateral status panel.

**Scope (in):** constraint-arc parity, 3D->3-deck expansion, SIS glitch thresholds, per-arc metrics, MPW skip rules (minimum SYNC/MB set), GUI redesign, collateral dropdown navigation.

**Scope (out):** LLM assistant (Point 3), FMC run integration (Point 4), design-system framework rewrite.

**Tech Stack:** Python 3.8+, pytest, pyyaml, stdlib `http.server` + vanilla HTML/CSS/JS (no frontend framework).

---

## File Structure

**Modified:**
- `core/parsers/template_tcl.py` -- add `define_index` parsing, SIS sidecar parser, metric fields on arcs
- `core/arc_info_builder.py` -- 3D expansion, `define_index` honoring, SIS field injection, metric_thresh precedence, MPW skip callback
- `core/resolver.py` -- `resolve_all_from_collateral` returns list (for 3D), propagates metrics
- `core/batch.py` -- handle list-returning resolver (flatten into multiple jobs with `-2/-3/-4` suffixes)
- `core/deck_builder.py` -- extend `$VAR` list with SIS pintype thresholds, metric_thresh, 3D suffix
- `gui.py` -- full redesign (see Part B)

**Created:**
- `core/mpw_skip.py` -- faithful port of MCQC skip_this_arc (0-mpw/qaTemplateMaker/funcs.py 168-223)
- `tests/fixtures/template_tcl/constraint_5x5x5.tcl` -- 3D constraint fixture
- `tests/fixtures/template_tcl/define_index_override.tcl` -- define_index override fixture
- `tests/fixtures/template_tcl/sis_sidecar.tcl` + matching `.sis` file
- `tests/test_template_tcl_define_index.py`
- `tests/test_template_tcl_sis.py`
- `tests/test_3d_expansion.py`
- `tests/test_mpw_skip.py`
- `tests/test_gui_api.py`

**Not touched:** existing MPW templates at `templates/N2P_v1.0/mpw/`, existing 177 tests must keep passing.

---

## Part A: Point 2b -- Constraint Parity

### Task 1: define_index fixture + test

**Files:** Create `tests/fixtures/template_tcl/define_index_override.tcl` and `tests/test_template_tcl_define_index.py`.

- [ ] **Step 1:** Create fixture `tests/fixtures/template_tcl/define_index_override.tcl`:

```tcl
lu_table_template "hold_template_5x5" {
  variable_1 : constrained_pin_transition;
  variable_2 : related_pin_transition;
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
}

define_cell "DFFQ1" {
  pinlist { VDD VSS CP D Q }
  output_pins { Q }
  constraint_template : hold_template_5x5;
}

define_arc {
  cell         : DFFQ1;
  arc_type     : hold;
  pin          : D;
  pin_dir      : fall;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "NO_CONDITION";
  lit_when     : "NO_CONDITION";
  probe_list   : { Q };
  vector       : "xxRxFxx";
}

define_index {
  cell         : DFFQ1;
  pin          : D;
  rel_pin      : CP;
  when         : "NO_CONDITION";
  index_1      ("0.3 0.6 0.9 1.2 1.5");
  index_2      ("0.08 0.12 0.16 0.20 0.24");
}
```

- [ ] **Step 2:** Create `tests/test_template_tcl_define_index.py`:

```python
"""Tests for define_index override parsing."""
import os
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


def test_define_index_parsed():
    info = parse_template_tcl_full(os.path.join(FIX, 'define_index_override.tcl'))
    assert 'index_overrides' in info
    assert len(info['index_overrides']) == 1
    o = info['index_overrides'][0]
    assert o['cell']     == 'DFFQ1'
    assert o['pin']      == 'D'
    assert o['rel_pin']  == 'CP'
    assert o['when']     == 'NO_CONDITION'
    assert o['index_1']  == [0.3, 0.6, 0.9, 1.2, 1.5]
    assert o['index_2']  == [0.08, 0.12, 0.16, 0.20, 0.24]


def test_find_define_index_override_helper():
    from core.parsers.template_tcl import find_define_index_override
    info = parse_template_tcl_full(os.path.join(FIX, 'define_index_override.tcl'))
    # matching lookup
    o = find_define_index_override(info['index_overrides'],
                                    cell='DFFQ1', pin='D',
                                    rel_pin='CP', when='NO_CONDITION')
    assert o is not None
    assert o['index_1'] == [0.3, 0.6, 0.9, 1.2, 1.5]

    # miss
    miss = find_define_index_override(info['index_overrides'],
                                       cell='DFFQ1', pin='Q',
                                       rel_pin='CP', when='NO_CONDITION')
    assert miss is None
```

- [ ] **Step 3:** Run tests -- expected FAIL (no `index_overrides` key yet).

- [ ] **Step 4:** Modify `core/parsers/template_tcl.py`. Append after `_DEFINE_ARC_RE`:

```python
_DEFINE_INDEX_RE = re.compile(
    r'define_index\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
    flags=re.DOTALL)


def find_define_index_override(overrides, cell, pin, rel_pin, when):
    """Return the first matching define_index entry, or None.

    Matching (MCQC parity): exact cell, exact pin, rel_pin match (or '*'),
    when fnmatch.
    """
    import fnmatch as _fn
    for o in overrides:
        if o.get('cell') != cell:
            continue
        if o.get('pin') != pin and o.get('pin') != '*':
            continue
        rp = o.get('rel_pin')
        if rp and rp != '*' and not _fn.fnmatch(rel_pin or '', rp):
            continue
        w = o.get('when')
        if w and not _fn.fnmatch(when or '', w):
            continue
        return o
    return None
```

In `parse_template_tcl_full`, add parsing. Just before the `return` statement:

```python
    index_overrides = []
    for m in _DEFINE_INDEX_RE.finditer(content):
        body = m.group(1)
        f = _parse_block_fields(body)
        def _floats(s):
            s = (s or '').replace('"', '').strip()
            try:
                return [float(x) for x in s.split()]
            except ValueError:
                return []
        index_overrides.append({
            'cell':    f.get('cell', ''),
            'pin':     f.get('pin', ''),
            'rel_pin': f.get('rel_pin', ''),
            'when':    f.get('when', ''),
            'index_1': _floats(f.get('index_1', '')),
            'index_2': _floats(f.get('index_2', '')),
            'index_3': _floats(f.get('index_3', '')),
        })
```

And add `'index_overrides': index_overrides,` to the returned dict.

Note: `index_1`/`index_2` values inside `define_index` use `( "0.3 0.6 ..." )` syntax, NOT `key : "value";`. The existing `_FIELD_RE` / `_FIELD_BRACE_RE` may not catch this. If tests fail, inspect the raw body and add a targeted regex:

```python
_INDEX_N_RE = re.compile(r'index_(\d)\s*\(\s*"([^"]*)"\s*\)\s*;?')
```

Then inside the `define_index` loop extract indices via this regex before calling `_parse_block_fields`.

- [ ] **Step 5:** Run tests -- expected all PASS. Fix regex if needed.

- [ ] **Step 6:** Full suite regression: `python -m pytest tests/ -q 2>&1 | tail -3`.

- [ ] **Step 7:** Non-ASCII + commit:

```bash
python3 -c "open('core/parsers/template_tcl.py','rb').read().decode('ascii'); open('tests/fixtures/template_tcl/define_index_override.tcl','rb').read().decode('ascii'); open('tests/test_template_tcl_define_index.py','rb').read().decode('ascii'); print('OK')"
git add core/parsers/template_tcl.py tests/fixtures/template_tcl/ tests/test_template_tcl_define_index.py
git commit -m "feat(template_tcl): parse define_index overrides + finder helper"
```

---

### Task 2: 5x5x5 constraint fixture + 3D expansion in arc_info_builder

**Files:** Create `tests/fixtures/template_tcl/constraint_5x5x5.tcl` and `tests/test_3d_expansion.py`; modify `core/arc_info_builder.py`.

- [ ] **Step 1:** Create fixture `tests/fixtures/template_tcl/constraint_5x5x5.tcl`:

```tcl
lu_table_template "constraint_5x5x5" {
  variable_1 : constrained_pin_transition;
  variable_2 : related_pin_transition;
  variable_3 : total_output_net_capacitance;
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
  index_3 ("0.0005 0.001 0.005 0.01 0.05");
}

define_cell "DFFQ1_3D" {
  pinlist { VDD VSS CP D Q }
  output_pins { Q }
  constraint_template : constraint_5x5x5;
}

define_arc {
  cell         : DFFQ1_3D;
  arc_type     : hold;
  pin          : D;
  pin_dir      : fall;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "NO_CONDITION";
  lit_when     : "NO_CONDITION";
  probe_list   : { Q };
  vector       : "xxRxFxx";
}
```

- [ ] **Step 2:** Create `tests/test_3d_expansion.py`:

```python
"""Tests for 3D constraint expansion (5x5x5 -> 3 arc_info entries)."""
import os
from core.parsers.template_tcl import parse_template_tcl_full
from core.arc_info_builder import build_arc_infos

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


def _setup():
    info = parse_template_tcl_full(os.path.join(FIX, 'constraint_5x5x5.tcl'))
    arc = info['arcs'][0]
    cell = info['cells']['DFFQ1_3D']
    corner = {'process': 'ssgnp', 'vdd': '0.450',
              'temperature': '-40', 'rc_type': 'cworst_CCworst_T',
              'netlist_dir': '/fake'}
    return arc, cell, info, corner


def test_3d_yields_three_arc_infos():
    arc, cell, info, corner = _setup()
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    # MCQC: skip endpoints (0 and 4), keep indices 1, 2, 3 of index_3
    assert len(results) == 3


def test_3d_index_3_values():
    arc, cell, info, corner = _setup()
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    idx3_set = {r['INDEX_3_INDEX'] for r in results}
    assert idx3_set == {'1', '2', '3'}


def test_3d_deck_suffix():
    arc, cell, info, corner = _setup()
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    # Each result has _deck_suffix '-2', '-3', '-4' (MCQC: INDEX_3_INDEX+1)
    suffixes = {r.get('_deck_suffix') for r in results}
    assert suffixes == {'-2', '-3', '-4'}


def test_non_3d_returns_single_result():
    info = parse_template_tcl_full(
        os.path.join(FIX, 'non_cons_full.tcl'))
    arc = info['arcs'][0]
    cell = info['cells']['DFFQ1']
    corner = {'process':'ssgnp','vdd':'0.450','temperature':'-40',
              'rc_type':'cworst_CCworst_T','netlist_dir':'/fake'}
    results = build_arc_infos(
        arc=arc, cell_info=cell, template_info=info, chartcl=None,
        corner=corner, netlist_path='', netlist_pins='',
        include_file='', waveform_file='',
        overrides={'index_1_index': 1, 'index_2_index': 1})
    assert len(results) == 1
    assert results[0].get('_deck_suffix') in ('', None)
```

- [ ] **Step 3:** Run -- expected FAIL (`build_arc_infos` doesn't exist).

- [ ] **Step 4:** Modify `core/arc_info_builder.py`. Add a new function `build_arc_infos` (note plural) that wraps the existing `build_arc_info` and handles 3D expansion:

```python
import re as _re


def _is_3d_template(template_name):
    """MCQC parity: template name matches regex '5x5x5'."""
    return bool(template_name and _re.search(r'5x5x5', template_name))


def build_arc_infos(arc, cell_info, template_info, chartcl, corner,
                    netlist_path, netlist_pins, include_file, waveform_file,
                    overrides=None):
    """Build one or more arc_info dicts. Returns a LIST.

    For 3D constraint arcs (template matches '5x5x5'), returns 3 entries
    (indices 1, 2, 3 of index_3 -- endpoints skipped per MCQC).
    For all other arcs, returns a single entry.
    """
    overrides = overrides or {}
    arc_type = arc.get('arc_type', '')

    # Determine if this is a 3D constraint arc
    tpl_name = _pick_template_for_arc(cell_info, arc_type)
    tpl = template_info['templates'].get(tpl_name, {}) if tpl_name else {}
    index_3_list = tpl.get('index_3', [])

    if _is_3d_template(tpl_name) and len(index_3_list) == 5:
        results = []
        for idx3 in (2, 3, 4):  # 1-based indices 2,3,4 => skip 1 and 5
            ov = dict(overrides)
            ov['index_3_index'] = idx3
            info = build_arc_info(
                arc=arc, cell_info=cell_info,
                template_info=template_info, chartcl=chartcl,
                corner=corner,
                netlist_path=netlist_path, netlist_pins=netlist_pins,
                include_file=include_file, waveform_file=waveform_file,
                overrides=ov)
            info['INDEX_3_INDEX'] = str(idx3 - 1)   # MCQC: index at 1,2,3
            info['_deck_suffix']  = f"-{idx3}"
            info['_constraint_is_3d'] = True
            # OUTPUT_LOAD comes from index_3[idx3-1] for 3D
            if 0 < (idx3 - 1) < len(index_3_list):
                info['OUTPUT_LOAD'] = format_index_value(
                    index_3_list[idx3 - 1], 'p')
            results.append(info)
        return results

    # Non-3D: single result
    info = build_arc_info(
        arc=arc, cell_info=cell_info,
        template_info=template_info, chartcl=chartcl,
        corner=corner,
        netlist_path=netlist_path, netlist_pins=netlist_pins,
        include_file=include_file, waveform_file=waveform_file,
        overrides=overrides)
    info['_deck_suffix'] = ''
    return [info]
```

- [ ] **Step 5:** Run `python -m pytest tests/test_3d_expansion.py -v`. Expected: all PASS.

- [ ] **Step 6:** Verify no regression: `python -m pytest tests/ -q 2>&1 | tail -3`.

- [ ] **Step 7:** Commit:

```bash
git add core/arc_info_builder.py tests/fixtures/template_tcl/constraint_5x5x5.tcl tests/test_3d_expansion.py
git commit -m "feat(arc_info): add build_arc_infos with 3D constraint expansion"
```

---

### Task 3: define_index honoring in build_arc_info

**Files:** Modify `core/arc_info_builder.py`, append tests to `tests/test_arc_info_builder.py`.

- [ ] **Step 1:** Append tests to `tests/test_arc_info_builder.py`:

```python
class TestDefineIndexOverride:
    def test_define_index_overrides_template_indices(self):
        from core.parsers.template_tcl import parse_template_tcl_full
        from core.arc_info_builder import build_arc_info
        import os
        FIX2 = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')
        info = parse_template_tcl_full(os.path.join(FIX2, 'define_index_override.tcl'))
        arc = info['arcs'][0]
        cell = info['cells']['DFFQ1']
        corner = {'process':'ssgnp','vdd':'0.450','temperature':'-40',
                  'rc_type':'cworst_CCworst_T','netlist_dir':'/fake'}
        # With override, index_1[0] should be 0.3 (from define_index), NOT 0.1 (from template)
        result = build_arc_info(arc, cell, info, None, corner,
                                netlist_path='', netlist_pins='',
                                include_file='', waveform_file='',
                                overrides={'index_1_index': 1, 'index_2_index': 1})
        assert result['INDEX_1_VALUE'] == '0.3n'
        # index_2[0] overridden: 0.08; suffix 'n' for hold
        assert result['INDEX_2_VALUE'] == '0.08n'
```

- [ ] **Step 2:** Run tests -- expected FAIL (override not honored).

- [ ] **Step 3:** Modify `build_arc_info` in `core/arc_info_builder.py`. Near the top of the function (after computing `template_name` / `tpl`), insert:

```python
    # Honor define_index override if one matches this (cell, pin, rel_pin, when)
    from core.parsers.template_tcl import find_define_index_override
    override = find_define_index_override(
        template_info.get('index_overrides', []),
        cell=cell_name,
        pin=arc.get('pin', ''),
        rel_pin=arc.get('rel_pin', ''),
        when=arc.get('when', ''),
    )
    if override:
        if override.get('index_1'):
            index_1_list = override['index_1']
        if override.get('index_2'):
            index_2_list = override['index_2']
```

(Place this block right after `index_1_list = tpl.get(...)` and `index_2_list = tpl.get(...)` lines so overrides replace template defaults.)

- [ ] **Step 4:** Run tests -- expected PASS.

- [ ] **Step 5:** Full regression: `python -m pytest tests/ -q 2>&1 | tail -3`.

- [ ] **Step 6:** Commit:

```bash
git add core/arc_info_builder.py tests/test_arc_info_builder.py
git commit -m "feat(arc_info): honor define_index overrides for index_1 / index_2"
```

---

### Task 4: SIS template sidecar parser

**Files:** Create `tests/fixtures/template_tcl/sis_sidecar.tcl`, `tests/fixtures/template_tcl/Template_sis/sis_sidecar.sis`, `tests/test_template_tcl_sis.py`; modify `core/parsers/template_tcl.py` and `core/arc_info_builder.py`.

- [ ] **Step 1:** Create `tests/fixtures/template_tcl/Template_sis/sis_sidecar.sis`:

```tcl
define_pintype "O" {
  glitch_high_threshold : 0.35;
  glitch_low_threshold  : 0.1;
}

define_pintype "I" {
  glitch_high_threshold : 0.40;
  glitch_low_threshold  : 0.12;
}
```

- [ ] **Step 2:** Create `tests/fixtures/template_tcl/sis_sidecar.tcl` (mirrors non_cons_full.tcl but with a distinct filename so sidecar lookup pairs correctly):

```tcl
lu_table_template "delay_template_5x5" {
  index_1 ("0.05 0.1 0.2 0.5 1.0");
  index_2 ("0.0005 0.001 0.005 0.01 0.05");
}

define_cell "DFFQ1" {
  pinlist { VDD VSS CP D Q }
  output_pins { Q }
  delay_template : delay_template_5x5;
}

define_arc {
  cell : DFFQ1; arc_type : combinational;
  pin : Q; pin_dir : rise;
  rel_pin : CP; rel_pin_dir : rise;
  when : "NO_CONDITION"; lit_when : "NO_CONDITION";
  probe_list : { Q };
  vector : "RxxRxx";
}
```

- [ ] **Step 3:** Create `tests/test_template_tcl_sis.py`:

```python
"""Tests for SIS template sidecar parsing."""
import os
from core.parsers.template_tcl import parse_template_tcl_full

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')


def test_sis_sidecar_parsed():
    info = parse_template_tcl_full(os.path.join(FIX, 'sis_sidecar.tcl'))
    assert 'sis' in info
    sis = info['sis']
    assert 'O' in sis
    assert sis['O']['glitch_high_threshold'] == '0.35'
    assert sis['O']['glitch_low_threshold']  == '0.1'
    assert sis['I']['glitch_high_threshold'] == '0.40'


def test_sis_sidecar_missing_ok():
    info = parse_template_tcl_full(os.path.join(FIX, 'non_cons_full.tcl'))
    # non_cons_full.tcl has no matching .sis file -> 'sis' key absent or empty
    assert info.get('sis', {}) == {}


def test_sis_fields_in_arc_info():
    """When a cell has output pins, their pintype glitch thresholds flow into arc_info."""
    from core.arc_info_builder import build_arc_info
    info = parse_template_tcl_full(os.path.join(FIX, 'sis_sidecar.tcl'))
    arc = info['arcs'][0]
    cell = info['cells']['DFFQ1']
    corner = {'process':'ssgnp','vdd':'0.450','temperature':'-40',
              'rc_type':'cworst_CCworst_T','netlist_dir':'/fake'}
    ai = build_arc_info(arc, cell, info, None, corner,
                        netlist_path='', netlist_pins='',
                        include_file='', waveform_file='',
                        overrides={'index_1_index': 1, 'index_2_index': 1})
    # 'Q' is output -> pintype 'O' -> injected as O_GLITCH_HIGH_THRESHOLD
    assert ai.get('O_GLITCH_HIGH_THRESHOLD') == '0.35'
    assert ai.get('O_GLITCH_LOW_THRESHOLD')  == '0.1'
```

- [ ] **Step 4:** Run -- expected FAIL (no `sis` key).

- [ ] **Step 5:** Modify `core/parsers/template_tcl.py`. Append:

```python
_DEFINE_PINTYPE_RE = re.compile(
    r'define_pintype\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
    flags=re.DOTALL)


def _parse_sis_sidecar(tcl_path):
    """If a <stem>.sis file exists alongside tcl_path in a Template_sis/
    directory, parse it and return {pintype: {key: value}}.
    """
    stem = os.path.splitext(os.path.basename(tcl_path))[0]
    dirname = os.path.dirname(tcl_path)
    sis_path = os.path.join(dirname, 'Template_sis', stem + '.sis')
    if not os.path.isfile(sis_path):
        return {}
    with open(sis_path, 'r') as f:
        content = f.read()
    result = {}
    for m in _DEFINE_PINTYPE_RE.finditer(content):
        name = m.group(1)
        fields = _parse_block_fields(m.group(2))
        result[name] = fields
    return result
```

(Make sure `import os` is already at the top of the file -- it is.)

In `parse_template_tcl_full`, add before `return`:

```python
    sis = _parse_sis_sidecar(path)
```

And add `'sis': sis,` to the returned dict.

- [ ] **Step 6:** Modify `core/arc_info_builder.py`. In `build_arc_info`, before the final `return info`:

```python
    # Inject SIS pintype glitch thresholds if the template has a sidecar.
    # Rule (MCQC): for each pin in OUTPUT_PINS, classify as 'O'; for each
    # other pin in TEMPLATE_PINLIST, classify as 'I'. Thresholds from the
    # first matching pintype block go into {PINTYPE}_GLITCH_HIGH/LOW_THRESHOLD.
    sis = template_info.get('sis', {})
    if sis:
        output_pins_list = cell_info.get('output_pins', [])
        if output_pins_list and 'O' in sis:
            info['O_GLITCH_HIGH_THRESHOLD'] = str(sis['O'].get('glitch_high_threshold', ''))
            info['O_GLITCH_LOW_THRESHOLD']  = str(sis['O'].get('glitch_low_threshold',  ''))
        if 'I' in sis:
            info['I_GLITCH_HIGH_THRESHOLD'] = str(sis['I'].get('glitch_high_threshold', ''))
            info['I_GLITCH_LOW_THRESHOLD']  = str(sis['I'].get('glitch_low_threshold',  ''))
```

- [ ] **Step 7:** Run tests -- expected all PASS.

- [ ] **Step 8:** Full regression: `python -m pytest tests/ -q 2>&1 | tail -3`.

- [ ] **Step 9:** Commit:

```bash
git add core/parsers/template_tcl.py core/arc_info_builder.py tests/fixtures/template_tcl/sis_sidecar.tcl tests/fixtures/template_tcl/Template_sis/ tests/test_template_tcl_sis.py
git commit -m "feat(sis): parse Template_sis sidecar + inject pintype glitch thresholds"
```

---

### Task 5: Per-arc metric / metric_thresh extraction + precedence

**Files:** Modify `core/parsers/template_tcl.py` (already captures `metric`/`metric_thresh` fields from define_arc but as empty strings when not in the TCL -- verify); modify `core/arc_info_builder.py` to honor precedence; append a test to `tests/test_arc_info_builder.py`.

- [ ] **Step 1:** Append fixture content to `tests/fixtures/template_tcl/non_cons_full.tcl` -- add a 3rd define_arc block at end of file:

```tcl

define_arc {
  cell         : DFFQ1;
  arc_type     : setup;
  pin          : D;
  pin_dir      : rise;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "NO_CONDITION";
  lit_when     : "NO_CONDITION";
  probe_list   : { Q };
  vector       : "xxRxFxx";
  metric       : glitch;
  metric_thresh : "0.55";
}
```

(Note: if modifying this file breaks existing tests, instead create `tests/fixtures/template_tcl/with_metric.tcl` and use that -- safer approach.)

Use the **safer approach**: create `tests/fixtures/template_tcl/with_metric.tcl`:

```tcl
lu_table_template "hold_template_5x5" {
  index_1 ("0.1 0.2 0.5 1.0 2.0");
  index_2 ("0.05 0.1 0.2 0.5 1.0");
}

define_cell "DFFQ1" {
  pinlist { VDD VSS CP D Q }
  output_pins { Q }
  constraint_template : hold_template_5x5;
}

define_arc {
  cell         : DFFQ1;
  arc_type     : setup;
  pin          : D;
  pin_dir      : rise;
  rel_pin      : CP;
  rel_pin_dir  : rise;
  when         : "NO_CONDITION";
  lit_when     : "NO_CONDITION";
  probe_list   : { Q };
  vector       : "xxRxFxx";
  metric       : glitch;
  metric_thresh : "0.55";
}
```

- [ ] **Step 2:** Append test to `tests/test_arc_info_builder.py`:

```python
class TestMetricPrecedence:
    def test_metric_thresh_overrides_chartcl_glitch(self):
        from core.parsers.template_tcl import parse_template_tcl_full
        from core.arc_info_builder import build_arc_info
        from core.parsers.chartcl import ChartclParser
        import os
        FIX3 = os.path.join(os.path.dirname(__file__), 'fixtures', 'template_tcl')
        info = parse_template_tcl_full(os.path.join(FIX3, 'with_metric.tcl'))
        arc = info['arcs'][0]
        cell = info['cells']['DFFQ1']

        # Build a chartcl parser with a conflicting global glitch
        class _fake_chartcl:
            vars = {'constraint_glitch_peak': '0.1'}
            conditions = {}

        corner = {'process':'ssgnp','vdd':'0.450','temperature':'-40',
                  'rc_type':'cworst_CCworst_T','netlist_dir':'/fake'}
        ai = build_arc_info(arc, cell, info, _fake_chartcl(), corner,
                            netlist_path='', netlist_pins='',
                            include_file='', waveform_file='',
                            overrides={'index_1_index': 1, 'index_2_index': 1})
        # MCQC precedence: per-arc metric_thresh (0.55) wins over chartcl (0.1)
        assert ai['GLITCH'] == '0.55'
```

- [ ] **Step 3:** Run -- expected FAIL (metric not honored).

- [ ] **Step 4:** Modify `core/arc_info_builder.py`. After the GLITCH assignment block, add:

```python
    # MCQC parity: per-arc metric_thresh overrides all (highest precedence)
    if arc.get('metric') == 'glitch' and arc.get('metric_thresh'):
        info['GLITCH'] = str(arc['metric_thresh']).strip('"')
```

(Place this AFTER `info['GLITCH']` is set, just before the probe_fields block.)

- [ ] **Step 5:** Run tests -- expected PASS.

- [ ] **Step 6:** Full regression: `python -m pytest tests/ -q 2>&1 | tail -3`.

- [ ] **Step 7:** Commit:

```bash
git add core/arc_info_builder.py tests/fixtures/template_tcl/with_metric.tcl tests/test_arc_info_builder.py
git commit -m "feat(arc_info): honor per-arc metric_thresh (highest glitch precedence)"
```

---

### Task 6: MPW skip logic (SYNC subset)

**Files:** Create `core/mpw_skip.py` and `tests/test_mpw_skip.py`; wire into `core/batch.py`.

- [ ] **Step 1:** Create `tests/test_mpw_skip.py`:

```python
"""Tests for MPW skip_this_arc logic (MCQC 0-mpw/qaTemplateMaker port)."""
import pytest
from core.mpw_skip import skip_this_arc


class TestSync2Removal:
    def test_sync2_q_removal_skipped(self):
        assert skip_this_arc(
            cell_name='SYNC2DFF',
            arc_type='removal',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])

    def test_sync2_q_hold_not_skipped(self):
        assert not skip_this_arc(
            cell_name='SYNC2DFF',
            arc_type='hold',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])


class TestSync3Removal:
    def test_sync3_q_removal_skipped(self):
        assert skip_this_arc(
            cell_name='SYNC3DFF',
            arc_type='removal',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])


class TestSync4Removal:
    def test_sync4_q_removal_skipped(self):
        assert skip_this_arc(
            cell_name='SYNC4DFF',
            arc_type='removal',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])


class TestNormalCells:
    def test_regular_dff_not_skipped(self):
        assert not skip_this_arc(
            cell_name='DFFQ1',
            arc_type='hold',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])

    def test_regular_combinational_not_skipped(self):
        assert not skip_this_arc(
            cell_name='AND2X1',
            arc_type='combinational',
            rel_pin='A', rel_pin_dir='rise',
            pin='Y', pin_dir='rise',
            when='NO_CONDITION',
            probe_list=['Y'])
```

- [ ] **Step 2:** Run -- expected FAIL.

- [ ] **Step 3:** Create `core/mpw_skip.py`:

```python
"""mpw_skip.py - Arc skip logic (MCQC 0-mpw/qaTemplateMaker port).

Subset: SYNC2/3/4 removal arcs with Q probe are skipped.
Additional rules (MB, CKLNQR/HQR, RSDF) may be added if validation exposes them.
"""

import fnmatch


def skip_this_arc(cell_name, arc_type, rel_pin, rel_pin_dir,
                  pin, pin_dir, when, probe_list):
    """Return True if this arc should be skipped (MCQC parity).

    Mirrors the if-chain in MCQC 0-mpw/qaTemplateMaker/funcs.py:168-223.
    """
    probe_list = probe_list or []

    # SYNC2 Q removal
    if arc_type == 'removal' and fnmatch.fnmatch(cell_name, '*SYNC2*'):
        if any(p == 'Q' or 'Q' in p for p in probe_list):
            return True

    # SYNC3 Q removal
    if arc_type == 'removal' and fnmatch.fnmatch(cell_name, '*SYNC3*'):
        if any(p == 'Q' or 'Q' in p for p in probe_list):
            return True

    # SYNC4 Q removal
    if arc_type == 'removal' and fnmatch.fnmatch(cell_name, '*SYNC4*'):
        if any(p == 'Q' or 'Q' in p for p in probe_list):
            return True

    # TODO port remaining rules from 0-mpw/qaTemplateMaker/funcs.py:
    #   - CKLNQR/CKLHQR: skip if 'OV' in when
    #   - MB cells with ICG: skip if unbalanced vector after CP
    #   - MB cells with clkb probe: skip
    #   - RSDF: skip some arcs

    return False
```

- [ ] **Step 4:** Run tests -- expected PASS.

- [ ] **Step 5:** Wire into `core/batch._plan_jobs_from_collateral`. After `arc = parse_arc_identifier(arc_id)`, add:

```python
        # MPW skip check
        from core.mpw_skip import skip_this_arc
        if skip_this_arc(
                cell_name=arc['cell_name'],
                arc_type=arc['arc_type'],
                rel_pin=arc['rel_pin'],
                rel_pin_dir=arc['rel_dir'],
                pin=arc.get('probe_pin', ''),
                pin_dir=arc.get('probe_dir', ''),
                when=arc.get('when', ''),
                probe_list=[arc.get('probe_pin', '')]):
            continue
```

(Place it inside the `for arc_id in arc_ids:` loop, BEFORE the `for corner_name` loop so the arc is skipped for all corners.)

- [ ] **Step 6:** Run full suite: `python -m pytest tests/ -q 2>&1 | tail -3`. Expected: no regression.

- [ ] **Step 7:** Commit:

```bash
git add core/mpw_skip.py core/batch.py tests/test_mpw_skip.py
git commit -m "feat(mpw): add skip_this_arc for SYNC2/3/4 Q removal arcs"
```

---

### Task 7: Batch/resolver wiring for list-returning build_arc_infos

**Files:** Modify `core/resolver.py`, `core/batch.py`, `core/writer.py`.

- [ ] **Step 1:** Modify `core/resolver.py::resolve_all_from_collateral`. Change the final line from:

```python
    return build_arc_info(
        arc=arc, cell_info=cell_info,
        ...)
```

To:

```python
    from core.arc_info_builder import build_arc_infos
    return build_arc_infos(
        arc=arc, cell_info=cell_info,
        template_info=template_info, chartcl=chartcl,
        corner=corner,
        netlist_path=netlist_path, netlist_pins=netlist_pins,
        include_file=include_file, waveform_file=waveform_file,
        overrides=overrides)
```

This now returns a LIST. Existing tests that use `resolve_all_from_collateral` will break -- update them (or keep backward compat by adding a flag). Prefer keeping backward compat:

```python
    from core.arc_info_builder import build_arc_infos
    results = build_arc_infos(
        arc=arc, cell_info=cell_info,
        ...)
    # Back-compat: if single result (non-3D), return the dict directly
    if len(results) == 1:
        return results[0]
    return results
```

- [ ] **Step 2:** Modify `core/batch.py::_plan_jobs_from_collateral`. Wrap the resolver call:

```python
            try:
                arc_info_or_list = resolve_all_from_collateral(...)
                # Normalize to list
                if isinstance(arc_info_or_list, list):
                    infos = arc_info_or_list
                else:
                    infos = [arc_info_or_list]

                for sub_idx, arc_info in enumerate(infos):
                    job_id += 1
                    jobs.append({
                        'id': job_id,
                        ...
                        'arc_info': arc_info,
                        '_deck_suffix': arc_info.get('_deck_suffix', ''),
                        ...
                    })
```

Adjust the outer `job_id += 1` logic to increment per emitted job, not per arc x corner.

- [ ] **Step 3:** Modify `core/writer.py::get_deck_dirname` (or the corresponding function) to append `_deck_suffix` to the directory name when present.

If `writer.py` is not readily modified, handle the suffix in `batch.execute_jobs` when constructing the output path:

```python
        deck_dir = os.path.join(
            output_dir,
            get_deck_dirname(arc_info, when)
              + corner_suffix
              + job.get('_deck_suffix', ''))
```

- [ ] **Step 4:** Run regression: `python -m pytest tests/ -q 2>&1 | tail -5`. Expected: all pass.

- [ ] **Step 5:** Commit:

```bash
git add core/resolver.py core/batch.py core/writer.py
git commit -m "feat(batch): support list-returning resolver + 3D deck dir suffixes"
```

---

## Part B: Point 5 -- GUI Polish

### Task 8: GUI backend APIs for collateral

**Files:** Modify `gui.py` to add `/api/nodes`, `/api/lib_types`, `/api/corners`, `/api/cells` endpoints.

- [ ] **Step 1:** Read current `gui.py` to understand the existing `DeckgenHandler` pattern.

- [ ] **Step 2:** Create `tests/test_gui_api.py`:

```python
"""Tests for new GUI collateral APIs."""
import json
import os
import pytest
from gui import _api_list_nodes, _api_list_lib_types, _api_list_corners, _api_list_cells

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')


def test_list_nodes(tmp_path, monkeypatch):
    import shutil
    dest = tmp_path / 'collateral'
    shutil.copytree(FIXTURE_ROOT, str(dest))
    # Point gui's COLLATERAL_ROOT at tmp
    from gui import DeckgenHandler
    monkeypatch.setattr(DeckgenHandler, 'COLLATERAL_ROOT', str(dest))
    nodes = _api_list_nodes()
    assert 'N2P_v1.0' in nodes


def test_list_lib_types(tmp_path, monkeypatch):
    import shutil
    dest = tmp_path / 'collateral'
    shutil.copytree(FIXTURE_ROOT, str(dest))
    from gui import DeckgenHandler
    monkeypatch.setattr(DeckgenHandler, 'COLLATERAL_ROOT', str(dest))
    libs = _api_list_lib_types('N2P_v1.0')
    assert 'test_lib' in libs


def test_list_corners(tmp_path, monkeypatch):
    import shutil
    from tools.scan_collateral import build_manifest
    dest = tmp_path / 'collateral'
    shutil.copytree(FIXTURE_ROOT, str(dest))
    build_manifest(str(dest), 'N2P_v1.0', 'test_lib')
    from gui import DeckgenHandler
    monkeypatch.setattr(DeckgenHandler, 'COLLATERAL_ROOT', str(dest))
    corners = _api_list_corners('N2P_v1.0', 'test_lib')
    assert 'ssgnp_0p450v_m40c_cworst_CCworst_T' in corners
```

- [ ] **Step 3:** Run -- expected FAIL.

- [ ] **Step 4:** Modify `gui.py`. Add module-level helpers:

```python
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_COLLATERAL_ROOT = os.path.join(_SCRIPT_DIR, 'collateral')


def _api_list_nodes():
    """Scan collateral/ for node subdirs."""
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    if not os.path.isdir(root):
        return []
    return sorted([d for d in os.listdir(root)
                   if os.path.isdir(os.path.join(root, d))])


def _api_list_lib_types(node):
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    node_dir = os.path.join(root, node)
    if not os.path.isdir(node_dir):
        return []
    return sorted([d for d in os.listdir(node_dir)
                   if os.path.isdir(os.path.join(node_dir, d))])


def _api_list_corners(node, lib_type):
    from core.collateral import CollateralStore, CollateralError
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    try:
        store = CollateralStore(root, node, lib_type)
        return store.list_corners()
    except CollateralError:
        return []


def _api_list_cells(node, lib_type):
    from core.collateral import CollateralStore, CollateralError
    root = getattr(DeckgenHandler, 'COLLATERAL_ROOT', _DEFAULT_COLLATERAL_ROOT)
    try:
        store = CollateralStore(root, node, lib_type)
        return store.list_cells()
    except CollateralError:
        return []
```

Add `COLLATERAL_ROOT = _DEFAULT_COLLATERAL_ROOT` as a class attribute on `DeckgenHandler`.

Add route handlers inside `DeckgenHandler.do_POST` (or do_GET for these GET-semantic endpoints):

```python
        if self.path == '/api/nodes':
            self._send_json({'nodes': _api_list_nodes()})
            return
        if self.path.startswith('/api/lib_types'):
            # Expect JSON body: {"node": "N2P_v1.0"}
            data = self._read_json_body()
            self._send_json({'lib_types': _api_list_lib_types(data.get('node', ''))})
            return
        if self.path.startswith('/api/corners'):
            data = self._read_json_body()
            self._send_json({'corners': _api_list_corners(
                data.get('node', ''), data.get('lib_type', ''))})
            return
        if self.path.startswith('/api/cells'):
            data = self._read_json_body()
            self._send_json({'cells': _api_list_cells(
                data.get('node', ''), data.get('lib_type', ''))})
            return
```

(Match the existing `_send_json` / `_read_json_body` helpers; if they don't exist, copy the pattern from existing endpoints.)

- [ ] **Step 5:** Run tests -- expected PASS.

- [ ] **Step 6:** Commit:

```bash
git add gui.py tests/test_gui_api.py
git commit -m "feat(gui): add collateral list APIs (nodes, lib_types, corners, cells)"
```

---

### Task 9: GUI frontend -- dropdowns + collateral status panel

**Files:** Modify `gui.py` (inline HTML/CSS/JS).

**Goal:** Replace the existing single-arc-form layout with a two-column layout:
- Left: collateral selector (node dropdown -> lib_type dropdown -> corners multi-select + cells list) + mode toggle (Single Arc / Batch)
- Right: arc inputs (single mode) OR arc_ids textarea (batch mode), plus generated output panel

- [ ] **Step 1:** Read the existing `gui.py` HTML string (the `_PAGE_HTML` or equivalent) to identify what's currently rendered.

- [ ] **Step 2:** Replace the HTML with a new two-column layout. Use this skeleton, adapted to the existing `_send_html`/`_send_json` methods:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="US-ASCII">
<title>DeckGen</title>
<style>
  :root {
    --primary: #2563eb; --success: #10b981; --error: #ef4444;
    --bg: #f8fafc;     --panel: #ffffff;  --border: #e2e8f0;
    --text: #0f172a;
  }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
    Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); }
  .topbar { background: var(--panel); border-bottom: 1px solid var(--border);
    padding: 12px 20px; display: flex; gap: 12px; align-items: center; }
  .topbar h1 { margin: 0; font-size: 18px; }
  .topbar .spacer { flex: 1; }
  .topbar button { padding: 6px 14px; border: 1px solid var(--border);
    background: var(--panel); border-radius: 4px; cursor: pointer; }
  .topbar button.primary { background: var(--primary); color: white; border-color: var(--primary); }
  .main { display: grid; grid-template-columns: 380px 1fr; gap: 16px;
    padding: 16px; height: calc(100vh - 65px); box-sizing: border-box; }
  .panel { background: var(--panel); border: 1px solid var(--border);
    border-radius: 6px; padding: 16px; overflow-y: auto; }
  .panel h2 { margin: 0 0 12px; font-size: 14px; text-transform: uppercase;
    letter-spacing: 0.5px; color: #64748b; }
  label { display: block; margin-bottom: 12px; font-size: 13px; font-weight: 500; }
  label span { display: block; margin-bottom: 4px; color: #475569; }
  select, input[type=text], textarea { width: 100%; padding: 6px 8px;
    border: 1px solid var(--border); border-radius: 4px; font-size: 13px;
    font-family: inherit; box-sizing: border-box; }
  textarea { font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace;
    font-size: 12px; min-height: 100px; resize: vertical; }
  .mode-toggle { display: flex; gap: 8px; margin-bottom: 16px; }
  .mode-toggle button { flex: 1; padding: 8px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 4px; cursor: pointer; }
  .mode-toggle button.active { background: var(--primary); color: white;
    border-color: var(--primary); }
  .status { font-size: 12px; color: #64748b; margin-top: 8px; }
  .status.error { color: var(--error); }
  .status.ok { color: var(--success); }
  pre { background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 4px;
    overflow-x: auto; font-size: 12px; }
</style>
</head>
<body>

<div class="topbar">
  <h1>DeckGen</h1>
  <span id="status" class="status"></span>
  <div class="spacer"></div>
  <button id="btn-rescan">Rescan Collateral</button>
  <button id="btn-preview">Preview</button>
  <button id="btn-generate" class="primary">Generate</button>
</div>

<div class="main">
  <div class="panel" id="panel-left">
    <h2>Collateral</h2>
    <label><span>Node</span><select id="sel-node"></select></label>
    <label><span>Library Type</span><select id="sel-lib"></select></label>
    <label><span>Corners (ctrl/cmd-click for multi)</span>
      <select id="sel-corners" multiple size="6"></select></label>
    <div class="status" id="cells-status"></div>

    <h2 style="margin-top: 20px;">Mode</h2>
    <div class="mode-toggle">
      <button id="mode-single" class="active">Single Arc</button>
      <button id="mode-batch">Batch</button>
    </div>

    <div id="single-form">
      <label><span>Cell</span><input type="text" id="in-cell" placeholder="DFFQ1"></label>
      <label><span>Arc Type</span>
        <select id="in-arc-type">
          <option>combinational</option><option>hold</option>
          <option>setup</option><option>removal</option>
          <option>recovery</option><option>mpw</option>
        </select></label>
      <label><span>Related Pin</span><input type="text" id="in-rel-pin" placeholder="CP"></label>
      <label><span>Rel Dir</span>
        <select id="in-rel-dir"><option>rise</option><option>fall</option></select></label>
      <label><span>Probe Pin</span><input type="text" id="in-probe" placeholder="Q"></label>
    </div>

    <div id="batch-form" style="display:none;">
      <label><span>Arc Identifiers (one per line)</span>
        <textarea id="in-arc-ids" placeholder="hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1"></textarea></label>
    </div>

    <h2 style="margin-top: 20px;">Output</h2>
    <label><span>Output Dir</span><input type="text" id="in-output" value="./output"></label>
  </div>

  <div class="panel" id="panel-right">
    <h2>Results</h2>
    <div id="results"></div>
    <pre id="preview" style="display:none;"></pre>
  </div>
</div>

<script>
async function postJSON(path, body) {
  const r = await fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body) });
  return r.json();
}

async function refreshNodes() {
  const r = await postJSON('/api/nodes', {});
  const sel = document.getElementById('sel-node');
  sel.innerHTML = '';
  for (const n of r.nodes) {
    const o = document.createElement('option');
    o.value = o.textContent = n; sel.appendChild(o);
  }
  if (r.nodes.length) { sel.value = r.nodes[0]; refreshLibs(); }
}

async function refreshLibs() {
  const node = document.getElementById('sel-node').value;
  const r = await postJSON('/api/lib_types', { node });
  const sel = document.getElementById('sel-lib');
  sel.innerHTML = '';
  for (const l of r.lib_types) {
    const o = document.createElement('option');
    o.value = o.textContent = l; sel.appendChild(o);
  }
  if (r.lib_types.length) { sel.value = r.lib_types[0]; refreshCorners(); }
}

async function refreshCorners() {
  const node = document.getElementById('sel-node').value;
  const lib_type = document.getElementById('sel-lib').value;
  const rc = await postJSON('/api/corners', { node, lib_type });
  const rk = await postJSON('/api/cells', { node, lib_type });
  const sel = document.getElementById('sel-corners');
  sel.innerHTML = '';
  for (const c of rc.corners) {
    const o = document.createElement('option');
    o.value = o.textContent = c; sel.appendChild(o);
  }
  document.getElementById('cells-status').textContent =
    `${rc.corners.length} corners / ${rk.cells.length} cells`;
}

document.getElementById('sel-node').addEventListener('change', refreshLibs);
document.getElementById('sel-lib').addEventListener('change', refreshCorners);

document.getElementById('mode-single').addEventListener('click', () => {
  document.getElementById('single-form').style.display = 'block';
  document.getElementById('batch-form').style.display  = 'none';
  document.getElementById('mode-single').classList.add('active');
  document.getElementById('mode-batch').classList.remove('active');
});
document.getElementById('mode-batch').addEventListener('click', () => {
  document.getElementById('single-form').style.display = 'none';
  document.getElementById('batch-form').style.display  = 'block';
  document.getElementById('mode-batch').classList.add('active');
  document.getElementById('mode-single').classList.remove('active');
});

document.getElementById('btn-rescan').addEventListener('click', async () => {
  document.getElementById('status').textContent = 'Rescanning...';
  const node = document.getElementById('sel-node').value;
  const lib_type = document.getElementById('sel-lib').value;
  await postJSON('/api/rescan', { node, lib_type });
  document.getElementById('status').textContent = 'Rescan complete';
  refreshCorners();
});

function collectInputs() {
  const node = document.getElementById('sel-node').value;
  const lib_type = document.getElementById('sel-lib').value;
  const corners = Array.from(document.getElementById('sel-corners').selectedOptions)
    .map(o => o.value);
  const output = document.getElementById('in-output').value;
  const isBatch = document.getElementById('mode-batch').classList.contains('active');

  if (isBatch) {
    const arc_ids = document.getElementById('in-arc-ids').value
      .split('\n').map(s => s.trim()).filter(Boolean);
    return { mode: 'batch', node, lib_type, corners, arc_ids, output };
  } else {
    return {
      mode: 'single', node, lib_type, corners, output,
      cell:     document.getElementById('in-cell').value,
      arc_type: document.getElementById('in-arc-type').value,
      rel_pin:  document.getElementById('in-rel-pin').value,
      rel_dir:  document.getElementById('in-rel-dir').value,
      probe:    document.getElementById('in-probe').value,
    };
  }
}

document.getElementById('btn-preview').addEventListener('click', async () => {
  document.getElementById('status').textContent = 'Previewing...';
  const r = await postJSON('/api/preview_v2', collectInputs());
  document.getElementById('results').innerHTML =
    '<pre>' + JSON.stringify(r, null, 2) + '</pre>';
  document.getElementById('status').textContent = 'Preview ready';
});

document.getElementById('btn-generate').addEventListener('click', async () => {
  document.getElementById('status').textContent = 'Generating...';
  const r = await postJSON('/api/generate_v2', collectInputs());
  document.getElementById('results').innerHTML =
    '<pre>' + JSON.stringify(r, null, 2) + '</pre>';
  document.getElementById('status').textContent = 'Generation complete';
});

refreshNodes();
</script>

</body>
</html>
```

- [ ] **Step 3:** Add backend endpoints `/api/rescan`, `/api/preview_v2`, `/api/generate_v2` in `DeckgenHandler.do_POST`:

```python
        if self.path == '/api/rescan':
            data = self._read_json_body()
            from tools.scan_collateral import build_manifest
            try:
                build_manifest(DeckgenHandler.COLLATERAL_ROOT,
                               data.get('node', ''), data.get('lib_type', ''))
                self._send_json({'ok': True})
            except Exception as e:
                self._send_json({'ok': False, 'error': str(e)})
            return

        if self.path == '/api/preview_v2':
            data = self._read_json_body()
            # Build jobs without writing files
            from core.batch import plan_jobs
            try:
                arc_ids = data.get('arc_ids', [])
                if data.get('mode') == 'single':
                    arc_ids = [self._build_arc_id_from_single(data)]
                jobs, errors = plan_jobs(
                    arc_ids=arc_ids,
                    corner_names=data.get('corners', []),
                    files={},
                    node=data.get('node'),
                    lib_type=data.get('lib_type'),
                    collateral_root=DeckgenHandler.COLLATERAL_ROOT)
                self._send_json({'jobs': [
                    {k: v for k, v in j.items() if k != 'arc_info'}
                    for j in jobs
                ], 'errors': errors})
            except Exception as e:
                self._send_json({'error': str(e)})
            return

        if self.path == '/api/generate_v2':
            data = self._read_json_body()
            from core.batch import run_batch
            try:
                arc_ids = data.get('arc_ids', [])
                if data.get('mode') == 'single':
                    arc_ids = [self._build_arc_id_from_single(data)]
                jobs, results, errors = run_batch(
                    arc_ids=arc_ids,
                    corner_names=data.get('corners', []),
                    files={},
                    output_dir=data.get('output', './output'),
                    node=data.get('node'),
                    lib_type=data.get('lib_type'),
                    collateral_root=DeckgenHandler.COLLATERAL_ROOT)
                self._send_json({
                    'results': results,
                    'errors': errors,
                    'job_count': len(jobs),
                })
            except Exception as e:
                self._send_json({'error': str(e)})
            return
```

Add the helper method:

```python
    def _build_arc_id_from_single(self, data):
        """Build a synthetic arc_id string from single-mode inputs."""
        return f"{data.get('arc_type','')}_{data.get('cell','')}_{data.get('probe','Q')}_rise_{data.get('rel_pin','')}_{data.get('rel_dir','rise')}_NO_CONDITION_1_1"
```

- [ ] **Step 4:** Non-ASCII check on gui.py (the whole file):

```bash
python3 -c "open('gui.py','rb').read().decode('ascii'); print('OK')"
```

- [ ] **Step 5:** Smoke test manually:

```bash
python3 gui.py --port 8585 &
sleep 2
curl -s -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8585/api/nodes
curl -s -X POST -H 'Content-Type: application/json' -d '{"node":"N2P_v1.0"}' http://127.0.0.1:8585/api/lib_types
kill %1
```
Expected: JSON responses.

- [ ] **Step 6:** Full regression: `python -m pytest tests/ -q 2>&1 | tail -3`.

- [ ] **Step 7:** Commit:

```bash
git add gui.py
git commit -m "feat(gui): redesign with collateral dropdowns, single/batch modes, preview"
```

---

### Task 10: Final regression + docs + push

- [ ] **Step 1:** Full test run + summary:

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

- [ ] **Step 2:** Non-ASCII scan across repo (use the script from Point 2a Task 23).

- [ ] **Step 3:** Update `docs/task.md`. Add under "Point 2b":

```
## Point 2b -- Done

Constraint parity delivered:
- define_index override parser + lookup helper
- build_arc_infos (plural) with 3D constraint expansion (5x5x5 -> 3 decks)
- SIS template sidecar parsing + pintype glitch injection
- Per-arc metric_thresh precedence (highest glitch override)
- MPW skip_this_arc (SYNC2/3/4 Q removal subset)
- batch/resolver wired for list-returning builder + -2/-3/-4 deck suffixes

## Point 5 -- Done

GUI redesign delivered:
- Collateral-driven dropdowns: node -> lib_type -> corners/cells
- Single-Arc / Batch mode toggle
- Rescan button (auto-regenerates manifest)
- Preview / Generate separation
- Two-column layout with semantic color tokens
- API endpoints: /api/nodes, /api/lib_types, /api/corners, /api/cells,
  /api/rescan, /api/preview_v2, /api/generate_v2
```

- [ ] **Step 4:** Commit docs + push:

```bash
git add docs/task.md
git commit -m "docs(task): mark Point 2b + Point 5 done"

# Subtree push the whole deckgen/ subdir to DeckGen.git as point2b-plus-gui branch
cd ..
git subtree push --prefix=deckgen deckgen-remote point2b-plus-gui
cd deckgen
```

- [ ] **Step 5:** Summary to user:

Report final test count, git log head, non-ASCII status, and push URL.

---

## Completion Checklist

- [ ] All 10 tasks complete (2b Tasks 1-7, GUI Tasks 8-9, Final Task 10)
- [ ] 177 legacy + new tests pass with no regression
- [ ] 0 non-ASCII bytes across repo
- [ ] Point 2b spec deliverables ticked in docs/task.md
- [ ] Point 5 spec deliverables ticked in docs/task.md
- [ ] Branch `point2b-plus-gui` pushed to DeckGen.git
