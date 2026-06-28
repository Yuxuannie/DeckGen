# Measurement Grammar (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mine the template corpus into a parameterized measurement-grammar JSON, provide an `emit()` seam that reproduces any template's methodology body, and prove completeness with a byte-exact round-trip — so the engine can emit decks from collateral alone (Phase B consumes this).

**Architecture:** Three small modules under `core/measurement/`. `regions.py` classifies each template line as collateral / recipe / bias and extracts the recipe region; `mine.py` clusters templates by recipe content into `config/measurement_grammar.json` and validates via round-trip; `emit.py` selects a grammar entry and returns its recipe lines (value substitution delegated to the existing `deck_builder`). Comprehensiveness is enforced by the round-trip gate, which runs unchanged on the airgap hold+delay corpus.

**Tech Stack:** Python 3.8+ stdlib only (`os`, `json`, `re`, `argparse`, `glob`, `difflib`). pytest for tests.

## Global Constraints

- **stdlib only** — no third-party imports in `core/measurement/**` (PyYAML is allowed elsewhere but not needed here).
- **ASCII-only** for all `.py` and `.json` artifacts. Verify: `grep -rPn '[\x80-\xff]' core/measurement config/measurement_grammar.json` must be empty.
- **Never fail silently** — `emit`/`select_entry` raise typed errors listing what was tried + closest matches.
- **Run from repo root** (`/Users/nieyuxuan/Downloads/Work/4-MCQC/DeckGen`) so `core.*` imports resolve, or set `PYTHONPATH` to it.
- **Dev/test corpus:** `templates/N2P_v1.0/{delay,mpw}` (67 files). The same code must run unchanged when pointed at the airgap full hold+delay corpus — only the directory path differs.
- **Recipe boundary (from spec):** grammar owns `.options`, waveform-timestamp params, optimization block, `.option ptran_nodeset` + `.nodeset` block, toggling model-name lines, `.meas`, `.tran`, THANOS headers. Collateral (waveform/model/netlist `.inc`, `.temp`, corner/slew/load params, `VV*` sources, `X1` instance) and the WHEN/side-pin bias section are NOT owned (Phase B / flow).

---

### Task 1: Package scaffold + line classifier

**Files:**
- Create: `core/measurement/__init__.py`
- Create: `core/measurement/regions.py`
- Test: `tests/measurement/__init__.py`, `tests/measurement/test_regions.py`

**Interfaces:**
- Produces: `classify_line(line: str) -> str` returning one of
  `"collateral" | "recipe" | "bias" | "blank"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/measurement/test_regions.py
from core.measurement.regions import classify_line


def test_classify_collateral_lines():
    assert classify_line(".inc '$NETLIST_PATH'") == "collateral"
    assert classify_line(".temp $TEMPERATURE") == "collateral"
    assert classify_line(".param vdd_value = '$VDD_VALUE'") == "collateral"
    assert classify_line(".param cl = '$OUTPUT_LOAD'") == "collateral"
    assert classify_line("VVDD VDD 0 'vdd_value'") == "collateral"
    assert classify_line("X1 $NETLIST_PINS $CELL_NAME") == "collateral"


def test_classify_recipe_lines():
    assert classify_line(".options runlvl=6 ACCURATE=1") == "recipe"
    assert classify_line(".param related_pin_t01 = '10 * max_slew'") == "recipe"
    assert classify_line(".param max_slew = '0.1u'") == "recipe"
    assert classify_line(".option ptran_nodeset=1") == "recipe"
    assert classify_line(".nodeset v(X1.ml*_a) = 'vdd_value'") == "recipe"
    assert classify_line("XV$REL_PIN $REL_PIN 0 stdvs_rise VDD='vdd_value'") == "recipe"
    assert classify_line(".meas tran meas_delay trig v($REL_PIN) val='vdd_value/2'") == "recipe"
    assert classify_line(".tran 1p 5000n sweep monte=1") == "recipe"


def test_classify_bias_and_blank():
    assert classify_line("* Unspecified pins") == "bias"
    assert classify_line("* Pin definitions") == "bias"
    assert classify_line("") == "blank"
    assert classify_line("   ") == "blank"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_regions.py -v`
Expected: FAIL with `ModuleNotFoundError: core.measurement.regions`

- [ ] **Step 3: Write minimal implementation**

```python
# core/measurement/__init__.py
"""Measurement grammar: mine the template corpus into a parameterized recipe
JSON, emit recipes per arc, and prove completeness by byte-exact round-trip.
stdlib only, ASCII only (airgap-safe)."""
```

```python
# core/measurement/regions.py
"""Classify each template line into collateral / recipe / bias and extract the
recipe region (the fixed methodology body the grammar owns). Content-based, not
position-based, so interleaved sections (recipe options at top, collateral in the
middle, recipe nodeset/meas at the bottom) classify correctly. stdlib, ASCII."""
from __future__ import annotations

# Collateral: supplied by the flow / corner; filled per (cell, corner).
_COLLATERAL_PREFIXES = (
    ".inc", ".temp",
    ".param vdd_value", ".param vss_value", ".param cl",
    ".param rel_pin_slew", ".param constr_pin_slew",
    "vvdd", "vvss", "vvpp", "vvbb",
    "x1 ",
)
# Section comments that head collateral blocks (kept out of the recipe region).
_COLLATERAL_COMMENTS = (
    "* waveform", "* model include", "* netlist path", "* library information",
    "* slew and load", "* voltage", "* output load", "* subckt definition",
)
# Comments marking where engine WHEN/side-pin biases go (Phase B owns these).
_BIAS_COMMENTS = ("* unspecified pins", "* pin definitions")


def classify_line(line: str) -> str:
    s = line.strip()
    if not s:
        return "blank"
    low = s.lower()
    if low in _BIAS_COMMENTS:
        return "bias"
    if low.startswith(_COLLATERAL_COMMENTS):
        return "collateral"
    if low.startswith(_COLLATERAL_PREFIXES):
        return "collateral"
    return "recipe"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/measurement/test_regions.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/measurement/__init__.py core/measurement/regions.py tests/measurement/
git commit -m "feat(measurement): line classifier for recipe vs collateral"
```

---

### Task 2: Recipe-region extraction

**Files:**
- Modify: `core/measurement/regions.py`
- Test: `tests/measurement/test_regions.py`

**Interfaces:**
- Consumes: `classify_line` (Task 1).
- Produces: `extract_recipe(text: str) -> list[str]` — the ordered recipe lines
  (stripped of trailing whitespace), dropping collateral/bias/blank lines.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/measurement/test_regions.py
import os
from core.measurement.regions import extract_recipe

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DELAY = os.path.join(_REPO, "templates/N2P_v1.0/delay/template_common_inpin_rise_delay_fall.sp")
_MPW = os.path.join(_REPO, "templates/N2P_v1.0/mpw/template__CP__syncx__D__fall__rise__1.sp")


def test_extract_recipe_delay():
    recipe = extract_recipe(open(_DELAY).read())
    assert any(".meas tran meas_delay" in l for l in recipe)
    assert any(".tran 1p 5000n" in l for l in recipe)
    assert any("stdvs_rise" in l for l in recipe)
    # collateral excluded
    assert not any(l.strip().startswith(".inc") for l in recipe)
    assert not any(l.strip().startswith("X1 ") for l in recipe)
    assert not any("vdd_value = " in l for l in recipe)


def test_extract_recipe_mpw_has_init_block():
    recipe = extract_recipe(open(_MPW).read())
    assert any(".option ptran_nodeset" in l for l in recipe)
    assert any(".nodeset v(X1.ml*_a)" in l for l in recipe)
    assert any("cp2q_del1" in l for l in recipe)
    assert any("constr_pin_offset" in l for l in recipe)
    # collateral still excluded
    assert not any(l.strip().startswith(".inc") for l in recipe)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_regions.py -k extract -v`
Expected: FAIL with `ImportError: cannot import name 'extract_recipe'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/measurement/regions.py
def extract_recipe(text: str) -> list[str]:
    """Ordered recipe lines (the methodology body the grammar owns). Drops
    collateral, bias-section, and blank lines so two templates that differ only
    in collateral compare equal."""
    out = []
    for raw in text.splitlines():
        if classify_line(raw) == "recipe":
            out.append(raw.rstrip())
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/measurement/test_regions.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/measurement/regions.py tests/measurement/test_regions.py
git commit -m "feat(measurement): extract recipe region from a template"
```

---

### Task 3: Template key/cluster-tag parser

**Files:**
- Modify: `core/measurement/regions.py`
- Test: `tests/measurement/test_regions.py`

**Interfaces:**
- Produces: `parse_template_key(path: str) -> dict` with keys
  `{"arc_type", "rel_dir", "other_dir", "cluster_tag"}`. `arc_type` from the
  parent dir (`delay`/`mpw`). For mpw, the trailing `__<d1>__<d2>__N.sp` gives the
  two directions and the middle tokens form `cluster_tag`. For delay,
  `template_common_inpin_<rel>_delay_<probe>.sp`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/measurement/test_regions.py
from core.measurement.regions import parse_template_key


def test_parse_key_delay():
    k = parse_template_key("templates/N2P_v1.0/delay/template_common_inpin_rise_delay_fall.sp")
    assert k["arc_type"] == "delay"
    assert k["rel_dir"] == "rise"
    assert k["other_dir"] == "fall"
    assert k["cluster_tag"] == "common_inpin"


def test_parse_key_mpw_simple():
    k = parse_template_key("templates/N2P_v1.0/mpw/template__AO2__fall__rise__1.sp")
    assert k["arc_type"] == "mpw"
    assert k["rel_dir"] == "fall"
    assert k["other_dir"] == "rise"
    assert k["cluster_tag"] == "AO2"


def test_parse_key_mpw_multitoken_tag():
    k = parse_template_key("templates/N2P_v1.0/mpw/template__DET__LP__D__CP__fall__rise__1.sp")
    assert k["arc_type"] == "mpw"
    assert k["rel_dir"] == "fall"
    assert k["other_dir"] == "rise"
    assert k["cluster_tag"] == "DET.LP.D.CP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_regions.py -k parse_key -v`
Expected: FAIL with `ImportError: cannot import name 'parse_template_key'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/measurement/regions.py
import os as _os

_DIRS = ("rise", "fall")


def parse_template_key(path: str) -> dict:
    """Derive (arc_type, rel_dir, other_dir, cluster_tag) from a template path.
    Two filename schemes: delay = template_common_inpin_<rel>_delay_<probe>.sp;
    mpw = template__<tag tokens>__<d1>__<d2>__<N>.sp (tag may be multi-token).
    Unknown/odd names degrade to cluster_tag=<stem>, dirs='' (round-trip still
    keys them uniquely by provenance)."""
    arc_type = _os.path.basename(_os.path.dirname(path))
    stem = _os.path.basename(path)[:-3] if path.endswith(".sp") else _os.path.basename(path)

    if arc_type == "delay" and stem.startswith("template_common_inpin_") and "_delay_" in stem:
        body = stem[len("template_"):]                 # common_inpin_rise_delay_fall
        head, probe = body.rsplit("_", 1)              # common_inpin_rise_delay | fall
        head2, _delay = head.rsplit("_delay", 1) if "_delay" in head else (head, "")
        tag, rel = head2.rsplit("_", 1)                # common_inpin | rise
        return {"arc_type": arc_type, "rel_dir": rel, "other_dir": probe,
                "cluster_tag": tag}

    if stem.startswith("template__"):
        toks = [t for t in stem[len("template__"):].split("__") if t != ""]
        # drop a trailing numeric index token if present
        if toks and toks[-1].isdigit():
            toks = toks[:-1]
        rel = other = ""
        if len(toks) >= 2 and toks[-1] in _DIRS and toks[-2] in _DIRS:
            rel, other = toks[-2], toks[-1]
            toks = toks[:-2]
        tag = ".".join(toks) if toks else stem
        return {"arc_type": arc_type, "rel_dir": rel, "other_dir": other,
                "cluster_tag": tag}

    return {"arc_type": arc_type, "rel_dir": "", "other_dir": "", "cluster_tag": stem}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/measurement/test_regions.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add core/measurement/regions.py tests/measurement/test_regions.py
git commit -m "feat(measurement): parse arc_type/dirs/cluster_tag from template path"
```

---

### Task 4: Mine the corpus into a grammar dict

**Files:**
- Create: `core/measurement/mine.py`
- Test: `tests/measurement/test_mine.py`

**Interfaces:**
- Consumes: `extract_recipe`, `parse_template_key` (Tasks 2-3).
- Produces: `mine(template_dir: str) -> dict` returning a grammar dict:
  `{"version": 1, "source_corpus": <dir>, "entries": [ {"key": {...},
  "recipe_lines": [...], "provenance": [<filenames>]} ]}`. Templates with an
  identical recipe region collapse into one entry (provenance lists all).

- [ ] **Step 1: Write the failing test**

```python
# tests/measurement/test_mine.py
import os
from core.measurement.mine import mine

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_mine_delay_corpus():
    g = mine(os.path.join(_REPO, "templates/N2P_v1.0/delay"))
    assert g["version"] == 1
    assert len(g["entries"]) >= 1
    # every entry has a key, recipe_lines, provenance
    for e in g["entries"]:
        assert set(e["key"]) >= {"arc_type", "rel_dir", "other_dir", "cluster_tag"}
        assert e["recipe_lines"] and e["provenance"]
    # all 4 delay templates are accounted for in provenance
    provs = [p for e in g["entries"] for p in e["provenance"]]
    assert len(provs) == 4
    assert len(set(provs)) == 4


def test_mine_dedups_identical_recipes():
    g = mine(os.path.join(_REPO, "templates/N2P_v1.0/mpw"))
    provs = [p for e in g["entries"] for p in e["provenance"]]
    assert len(provs) == 63                # every mpw template accounted for
    # entries <= templates (dedup may collapse some)
    assert len(g["entries"]) <= 63
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_mine.py -v`
Expected: FAIL with `ModuleNotFoundError: core.measurement.mine`

- [ ] **Step 3: Write minimal implementation**

```python
# core/measurement/mine.py
"""Mine a template directory into a measurement-grammar dict, and validate it by
byte-exact round-trip. CLI: `python -m core.measurement.mine mine|validate <dir>`.
Comprehensive-by-construction: the grammar is exactly the set of distinct recipe
regions in the corpus it is pointed at (run on the airgap corpus for full hold+
delay coverage). stdlib, ASCII."""
from __future__ import annotations

import glob
import json
import os

from core.measurement.regions import extract_recipe, parse_template_key


def mine(template_dir: str) -> dict:
    entries = []
    by_recipe = {}                         # recipe-tuple -> entry index
    for path in sorted(glob.glob(os.path.join(template_dir, "*.sp"))):
        recipe = extract_recipe(open(path, encoding="ascii", errors="replace").read())
        fname = os.path.basename(path)
        sig = tuple(recipe)
        if sig in by_recipe:
            entries[by_recipe[sig]]["provenance"].append(fname)
            continue
        by_recipe[sig] = len(entries)
        entries.append({"key": parse_template_key(path),
                        "recipe_lines": recipe, "provenance": [fname]})
    return {"version": 1, "source_corpus": template_dir, "entries": entries}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/measurement/test_mine.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/measurement/mine.py tests/measurement/test_mine.py
git commit -m "feat(measurement): mine corpus into grammar dict with dedup"
```

---

### Task 5: Round-trip validation + CLI

**Files:**
- Modify: `core/measurement/mine.py`
- Test: `tests/measurement/test_roundtrip.py`

**Interfaces:**
- Consumes: `mine`, `extract_recipe`, `parse_template_key`.
- Produces: `validate(template_dir, grammar) -> dict` returning
  `{"total": int, "reproduced": int, "mismatches": [{"file":..., "diff":...}],
  "coverage": float}`. Also a `main()` argparse CLI with `mine` and `validate`
  subcommands; `validate` exits non-zero on any mismatch.

- [ ] **Step 1: Write the failing test**

```python
# tests/measurement/test_roundtrip.py
import os
from core.measurement.mine import mine, validate

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _check(subdir, n):
    d = os.path.join(_REPO, "templates/N2P_v1.0", subdir)
    g = mine(d)
    rep = validate(d, g)
    assert rep["total"] == n
    assert rep["reproduced"] == n, rep["mismatches"][:2]
    assert rep["coverage"] == 100.0
    assert rep["mismatches"] == []


def test_roundtrip_delay():
    _check("delay", 4)


def test_roundtrip_mpw():
    _check("mpw", 63)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_roundtrip.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate'`

(If, after Step 3, a real template trips the line classifier, `mismatches` will
name the file and show the diff — extend `_COLLATERAL_PREFIXES`/`_BIAS_COMMENTS`
in `regions.py` to cover the new pattern, then re-run. This is the
comprehensiveness gate doing its job, not a test to weaken.)

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/measurement/mine.py
import argparse
import difflib
import sys


def _select_for_template(grammar, path):
    """The entry whose provenance lists this template (round-trip selection)."""
    fname = os.path.basename(path)
    for e in grammar["entries"]:
        if fname in e["provenance"]:
            return e
    return None


def validate(template_dir: str, grammar: dict) -> dict:
    total = reproduced = 0
    mismatches = []
    for path in sorted(glob.glob(os.path.join(template_dir, "*.sp"))):
        total += 1
        original = extract_recipe(open(path, encoding="ascii", errors="replace").read())
        entry = _select_for_template(grammar, path)
        emitted = entry["recipe_lines"] if entry else []
        if emitted == original:
            reproduced += 1
        else:
            diff = "\n".join(difflib.unified_diff(
                original, emitted, "original", "emitted", lineterm=""))
            mismatches.append({"file": os.path.basename(path), "diff": diff})
    cov = round(100.0 * reproduced / total, 1) if total else 0.0
    return {"total": total, "reproduced": reproduced,
            "mismatches": mismatches, "coverage": cov}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="core.measurement.mine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine"); m.add_argument("dir")
    m.add_argument("-o", "--out", default="config/measurement_grammar.json")
    v = sub.add_parser("validate"); v.add_argument("dir")
    v.add_argument("-g", "--grammar", default=None)
    args = ap.parse_args(argv)

    if args.cmd == "mine":
        g = mine(args.dir)
        with open(args.out, "w", encoding="ascii") as fh:
            json.dump(g, fh, indent=2, ensure_ascii=True)
            fh.write("\n")
        print("mined %d entries from %d templates -> %s"
              % (len(g["entries"]),
                 sum(len(e["provenance"]) for e in g["entries"]), args.out))
        return 0

    g = json.load(open(args.grammar, encoding="ascii")) if args.grammar else mine(args.dir)
    rep = validate(args.dir, g)
    print("round-trip: %d/%d reproduced (%.1f%%)"
          % (rep["reproduced"], rep["total"], rep["coverage"]))
    for mm in rep["mismatches"]:
        print("MISMATCH %s\n%s" % (mm["file"], mm["diff"]))
    return 0 if not rep["mismatches"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/measurement/test_roundtrip.py -v`
Expected: PASS (2 tests). If a template mismatches, follow the Step-2 note to
extend `regions.py`, then re-run until 100%.

- [ ] **Step 5: Commit**

```bash
git add core/measurement/mine.py tests/measurement/test_roundtrip.py
git commit -m "feat(measurement): byte-exact round-trip validation + CLI"
```

---

### Task 6: Grammar loading + entry selection

**Files:**
- Create: `core/measurement/emit.py`
- Test: `tests/measurement/test_emit.py`

**Interfaces:**
- Produces:
  - `load_grammar(path: str = _DEFAULT) -> dict`
  - `select_entry(grammar, *, arc_type, rel_dir, other_dir, cluster_tag=None) -> dict`
    — first entry matching the given key fields (cluster_tag optional). Raises
    `SelectionError` listing tried key + closest entries when no match.
  - `class SelectionError(Exception)`

- [ ] **Step 1: Write the failing test**

```python
# tests/measurement/test_emit.py
import os
import pytest
from core.measurement.mine import mine
from core.measurement.emit import select_entry, SelectionError

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _grammar():
    return mine(os.path.join(_REPO, "templates/N2P_v1.0/mpw"))


def test_select_by_tag_and_dirs():
    e = select_entry(_grammar(), arc_type="mpw", rel_dir="fall",
                     other_dir="rise", cluster_tag="AO2")
    assert "template__AO2__fall__rise__1.sp" in e["provenance"]


def test_select_no_match_raises_with_tried_info():
    with pytest.raises(SelectionError) as ei:
        select_entry(_grammar(), arc_type="mpw", rel_dir="rise",
                     other_dir="rise", cluster_tag="NOPE")
    msg = str(ei.value)
    assert "NOPE" in msg and "tried" in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_emit.py -v`
Expected: FAIL with `ModuleNotFoundError: core.measurement.emit`

- [ ] **Step 3: Write minimal implementation**

```python
# core/measurement/emit.py
"""Select a grammar entry and emit its recipe lines. Value substitution of the
$PLACEHOLDERS is delegated to the existing deck_builder, not re-implemented here.
stdlib, ASCII."""
from __future__ import annotations

import json
import os

_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "config", "measurement_grammar.json")


class SelectionError(Exception):
    pass


def load_grammar(path: str = _DEFAULT) -> dict:
    with open(path, encoding="ascii") as fh:
        return json.load(fh)


def select_entry(grammar, *, arc_type, rel_dir, other_dir, cluster_tag=None):
    want = {"arc_type": arc_type, "rel_dir": rel_dir, "other_dir": other_dir}
    if cluster_tag is not None:
        want["cluster_tag"] = cluster_tag
    matches = [e for e in grammar["entries"]
               if all(e["key"].get(k) == v for k, v in want.items())]
    if matches:
        return matches[0]
    closest = [e["key"] for e in grammar["entries"]
               if e["key"].get("arc_type") == arc_type][:5]
    raise SelectionError(
        "no grammar entry for tried=%r; closest %d entr(ies): %r"
        % (want, len(closest), closest))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/measurement/test_emit.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/measurement/emit.py tests/measurement/test_emit.py
git commit -m "feat(measurement): grammar load + entry selection with typed errors"
```

---

### Task 7: Emit recipe lines (arc-identity fill)

**Files:**
- Modify: `core/measurement/emit.py`
- Test: `tests/measurement/test_emit.py`

**Interfaces:**
- Consumes: `select_entry`.
- Produces: `emit(entry, arc_info, *, fill_values=False) -> list[str]`. By default
  fills only arc-identity placeholders (`$REL_PIN`, `$CONSTR_PIN`,
  `$PROBE_PIN_1`) from `arc_info` and leaves corner/slew/load placeholders intact
  for `deck_builder`. `fill_values=True` also fills `$VDD_VALUE`,
  `$INDEX_1_VALUE`, `$INDEX_2_VALUE`, `$MAX_SLEW`, `$OUTPUT_LOAD`,
  `$TEMPERATURE`, and `$PUSHOUT_PER` (default `'0.4'`).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/measurement/test_emit.py
from core.measurement.emit import emit


def test_emit_fills_arc_identity_only_by_default():
    e = select_entry(_grammar(), arc_type="mpw", rel_dir="fall",
                     other_dir="rise", cluster_tag="CP.syncx.D")
    arc_info = {"REL_PIN": "CP", "CONSTR_PIN": "D", "PROBE_PIN_1": "Q"}
    lines = emit(e, arc_info)
    text = "\n".join(lines)
    assert "v(CP)" in text and "$REL_PIN" not in text
    assert "$VDD_VALUE" in text or "vdd_value" in text   # corner left for deck_builder
    assert "$INDEX_1_VALUE" in text or "$INDEX_2_VALUE" in text


def test_emit_fill_values_resolves_corner():
    e = select_entry(_grammar(), arc_type="mpw", rel_dir="fall",
                     other_dir="rise", cluster_tag="CP.syncx.D")
    arc_info = {"REL_PIN": "CP", "CONSTR_PIN": "D", "PROBE_PIN_1": "Q",
                "VDD_VALUE": "0.45", "INDEX_1_VALUE": "1n", "INDEX_2_VALUE": "2f",
                "MAX_SLEW": "0.1u", "OUTPUT_LOAD": "0.5f", "TEMPERATURE": "-40"}
    text = "\n".join(emit(e, arc_info, fill_values=True))
    assert "$INDEX_1_VALUE" not in text and "$PUSHOUT_PER" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_emit.py -k emit -v`
Expected: FAIL with `ImportError: cannot import name 'emit'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/measurement/emit.py
_IDENTITY = ("REL_PIN", "CONSTR_PIN", "PROBE_PIN_1")
_VALUE = ("VDD_VALUE", "INDEX_1_VALUE", "INDEX_2_VALUE", "MAX_SLEW",
          "OUTPUT_LOAD", "TEMPERATURE")


def emit(entry, arc_info, *, fill_values=False):
    keys = list(_IDENTITY)
    if fill_values:
        keys += list(_VALUE)
    out = []
    for line in entry["recipe_lines"]:
        for k in keys:
            if k in arc_info:
                line = line.replace("$" + k, str(arc_info[k]))
        if fill_values:
            line = line.replace("$PUSHOUT_PER", str(arc_info.get("PUSHOUT_PER", "0.4")))
        out.append(line)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/measurement/test_emit.py -v`
Expected: PASS (4 tests).
Note: if `cluster_tag="CP.syncx.D"` does not match (the dotted tag depends on
Task 3's join), run `python -m core.measurement.mine mine templates/N2P_v1.0/mpw -o /tmp/g.json`
and read the actual `key.cluster_tag` for `template__CP__syncx__D__fall__rise__1.sp`,
then use that exact value in the test.

- [ ] **Step 5: Commit**

```bash
git add core/measurement/emit.py tests/measurement/test_emit.py
git commit -m "feat(measurement): emit recipe lines with arc-identity fill"
```

---

### Task 8: Generate the committed grammar + ASCII guard + suite

**Files:**
- Create: `config/measurement_grammar.json` (generated)
- Test: `tests/measurement/test_artifact.py`

**Interfaces:**
- Consumes: the CLI from Task 5; `load_grammar` from Task 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/measurement/test_artifact.py
import os, json
from core.measurement.emit import load_grammar, _DEFAULT

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_committed_grammar_loads_and_is_ascii():
    g = load_grammar(_DEFAULT)
    assert g["version"] == 1 and g["entries"]
    raw = open(_DEFAULT, "rb").read()
    assert all(b < 128 for b in raw), "grammar JSON must be ASCII-only"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/measurement/test_artifact.py -v`
Expected: FAIL (`config/measurement_grammar.json` does not exist yet)

- [ ] **Step 3: Generate the artifact**

Generate the grammar from the combined local corpus (delay + mpw). Mine each
subdir and merge entries into one file (the corpus has two arc-type subdirs):

```bash
cd /Users/nieyuxuan/Downloads/Work/4-MCQC/DeckGen
python - <<'PY'
import json
from core.measurement.mine import mine
entries = []
for sub in ("delay", "mpw"):
    g = mine("templates/N2P_v1.0/%s" % sub)
    entries += g["entries"]
out = {"version": 1, "source_corpus": "templates/N2P_v1.0", "entries": entries}
with open("config/measurement_grammar.json", "w", encoding="ascii") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=True); fh.write("\n")
print("entries:", len(entries))
PY
grep -rPn '[\x80-\xff]' config/measurement_grammar.json core/measurement && echo "NON-ASCII FOUND" || echo "ASCII OK"
```

Expected: prints an entry count and `ASCII OK`.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/measurement/ -v`
Expected: PASS (all tests across the 5 test files).

- [ ] **Step 5: Commit**

```bash
git add config/measurement_grammar.json tests/measurement/test_artifact.py
git commit -m "feat(measurement): generate committed grammar artifact + ascii guard"
```

---

## Self-Review

**1. Spec coverage:**
- Miner (templatize/cluster -> grammar.json) → Tasks 4, 8. ✓
- Emitter (select_entry + emit, delegate substitution) → Tasks 6, 7. ✓
- Round-trip validation CLI + tests → Task 5. ✓
- Recipe boundary owns init/nodeset/options/meas/tran; excludes collateral/bias → Tasks 1, 2 (classifier). ✓
- Two families (simple_edge delay/slew, constraint_opt hold/mpw) → covered by content-clustering (Task 4) keyed via Task 3; family field is implied by arc_type/recipe content. NOTE: spec's `key.family`/`placeholders` fields are descriptive; the implementation keys on (arc_type, dirs, cluster_tag) + recipe-content dedup, which is sufficient for round-trip. If a consumer needs `family` explicitly, derive it from arc_type in Phase B.
- Airgap: stdlib-only, ASCII-only, runs unchanged on another dir → Global Constraints + Task 8 guard. ✓
- "Never fail silently" → Task 6 SelectionError. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has complete code. The two "if it mismatches, extend regions.py" notes are the intended round-trip workflow, not deferred work.

**3. Type consistency:** `mine` returns `{"entries":[{"key","recipe_lines","provenance"}]}` (Task 4) consumed identically by `validate` (Task 5), `select_entry` (Task 6), `emit` (Task 7). Key fields `arc_type/rel_dir/other_dir/cluster_tag` are produced by `parse_template_key` (Task 3) and matched by `select_entry` (Task 6) — consistent. `extract_recipe` list[str] flows mine->validate->emit unchanged.

**Known iteration point:** the line classifier (Task 1) is seeded from two templates; the round-trip gate (Task 5) over all 67 local templates will surface any uncovered collateral/recipe pattern. Expected and handled by extending `regions.py` constants — not a plan gap.
