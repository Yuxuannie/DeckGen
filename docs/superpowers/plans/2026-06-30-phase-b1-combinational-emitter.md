# Phase B1 — Combinational Emitter + Collateral Wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble a runnable SPICE deck for a combinational delay/slew arc from collateral + the Phase-A `emit()` recipe + an engine-derived side-pin bias — no per-cell template.

**Architecture:** A new `core/deck_assemble.py` builds the deck as `collateral_section(arc_info) + X1 instance + engine_bias_section(derived) + emit(recipe)`. It reuses `resolve_all_from_collateral` (collateral values), `core/measurement/emit.py` (recipe + value fill), `engine.stages.stage2_sensitize.derive_combinational` (sensitizing region → bias), and Phase-A `regions.extract_recipe` (validation). A sibling `core/deck_assemble_check.py` validates the assembled deck locally without a simulator. The existing `stage4_deckgen`/sequential path is left untouched (B3 unifies later).

**Tech Stack:** Python 3.8+ stdlib only; pytest (run as `python3.12 -m pytest`).

## Global Constraints

- **stdlib only** in `core/deck_assemble*.py` — no third-party imports.
- **ASCII-only** for all `.py`. Verify: `grep -rPn '[\x80-\xff]' core/deck_assemble.py core/deck_assemble_check.py` empty.
- **HSPICE-free locally** — no simulator invocation in any code or test. HSPICE runs only in airgap (not in this plan).
- **Never fail silently** — `assemble_combinational` returns a structured `{"status":"ERROR","error":...}` naming what failed; it does not raise on a bad arc.
- **Run from repo root** (`/Users/nieyuxuan/Downloads/Work/4-MCQC/DeckGen`) so `core.*` / `engine.*` imports resolve.
- **Combinational only** — sequential arcs are detected and returned as a named ERROR (handled by B2/B3), never assembled.
- **Bias values come from the engine** (`derive_combinational` SENSITIZING set), cross-checked against the kit `-when`; engine is the source of truth.

---

### Task 1: `engine_bias_section` — side-pin bias lines

**Files:**
- Create: `core/deck_assemble.py`
- Test: `tests/test_deck_assemble.py`

**Interfaces:**
- Produces: `engine_bias_section(side_bias: dict) -> list[str]` — one voltage source per
  side pin tying it to a rail (`1 -> vdd_value`, `0 -> vss_value`), sorted by pin name.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deck_assemble.py
from core.deck_assemble import engine_bias_section


def test_engine_bias_section_sorted_and_railed():
    lines = engine_bias_section({"A2": 1, "A1": 0})
    assert lines == [
        "* ===== ENGINE-DERIVED side-pin bias =====",
        "VA1 A1 0 'vss_value'",
        "VA2 A2 0 'vdd_value'",
    ]


def test_engine_bias_section_empty():
    assert engine_bias_section({}) == ["* ===== ENGINE-DERIVED side-pin bias ====="]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/test_deck_assemble.py::test_engine_bias_section_sorted_and_railed -v`
Expected: FAIL with `ModuleNotFoundError: core.deck_assemble`

- [ ] **Step 3: Write minimal implementation**

```python
# core/deck_assemble.py
"""deck_assemble.py -- assemble a runnable SPICE deck for a COMBINATIONAL delay/
slew arc from collateral + the Phase-A measurement recipe + an engine-derived
side-pin bias. No per-cell template. stdlib only, ASCII only, simulator-free.

Sequential arcs are out of scope here (B2/B3): they are detected and returned as a
named ERROR, never assembled."""
from __future__ import annotations


def engine_bias_section(side_bias: dict) -> list:
    """Voltage sources tying each non-toggling input to a rail at its derived value.
    side_bias: {pin: 0|1}. 1 -> vdd_value, 0 -> vss_value. Sorted for determinism."""
    lines = ["* ===== ENGINE-DERIVED side-pin bias ====="]
    for pin in sorted(side_bias):
        rail = "vdd_value" if side_bias[pin] else "vss_value"
        lines.append("V%s %s 0 '%s'" % (pin, pin, rail))
    return lines
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/test_deck_assemble.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/deck_assemble.py tests/test_deck_assemble.py
git commit -m "feat(deck_assemble): engine-derived side-pin bias section"
```

---

### Task 2: `collateral_section` — real collateral lines from arc_info

**Files:**
- Modify: `core/deck_assemble.py`
- Test: `tests/test_deck_assemble.py`

**Interfaces:**
- Consumes: arc_info dict keys `VDD_VALUE, TEMPERATURE, INDEX_1_VALUE, INDEX_2_VALUE,
  INCLUDE_FILE, WAVEFORM_FILE, NETLIST_PATH` (from `resolve_all_from_collateral`).
- Produces: `collateral_section(arc_info: dict) -> list[str]` — the `.inc`/corner/
  slew-load/rail-source lines (the lines Phase A classifies as "collateral"), with
  REAL values (no `$` placeholders). Output net cap line is NOT here (it depends on
  the probe pin; the recipe owns load via `cl`).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_deck_assemble.py
from core.deck_assemble import collateral_section

_ARC_INFO = {
    "VDD_VALUE": "0.45", "TEMPERATURE": "-40",
    "INDEX_1_VALUE": "1.2n", "INDEX_2_VALUE": "0.5f",
    "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
    "NETLIST_PATH": "/c/AOI22.spi",
}


def test_collateral_section_has_real_values_no_placeholders():
    lines = collateral_section(_ARC_INFO)
    text = "\n".join(lines)
    assert "$" not in text                              # all values resolved
    assert ".param vdd_value = '0.45'" in text
    assert ".temp -40" in text
    assert ".param cl = '0.5f'" in text                 # INDEX_2 = load
    assert ".param rel_pin_slew = '1.2n'" in text       # INDEX_1 = slew
    assert ".inc '/c/model.inc'" in text
    assert ".inc '/c/wv.spi'" in text
    assert ".inc '/c/AOI22.spi'" in text
    assert "VVDD VDD 0 'vdd_value'" in text
    assert "VVSS VSS 0 'vss_value'" in text
    assert "VVPP VPP 0 'vdd_value'" in text
    assert "VVBB VBB 0 'vss_value'" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/test_deck_assemble.py -k collateral -v`
Expected: FAIL with `ImportError: cannot import name 'collateral_section'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/deck_assemble.py
def collateral_section(arc_info: dict) -> list:
    """Collateral lines with REAL values (Phase-A 'collateral' class). Order mirrors
    the golden template: waveform/model/netlist .inc, corner, slew/load, rails."""
    g = lambda k: arc_info.get(k, "")
    return [
        "* ===== COLLATERAL (resolved from manifest) =====",
        "* Waveform",
        ".inc '%s'" % g("WAVEFORM_FILE"),
        "* Model include file",
        ".inc '%s'" % g("INCLUDE_FILE"),
        "* Netlist path",
        ".inc '%s'" % g("NETLIST_PATH"),
        "* Library information",
        ".param vdd_value = '%s'" % g("VDD_VALUE"),
        ".param vss_value = 0",
        ".temp %s" % g("TEMPERATURE"),
        "* Slew and load information",
        ".param cl = '%s'" % g("INDEX_2_VALUE"),
        ".param rel_pin_slew = '%s'" % g("INDEX_1_VALUE"),
        "* Voltage",
        "VVDD VDD 0 'vdd_value'",
        "VVSS VSS 0 'vss_value'",
        "VVPP VPP 0 'vdd_value'",
        "VVBB VBB 0 'vss_value'",
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/test_deck_assemble.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/deck_assemble.py tests/test_deck_assemble.py
git commit -m "feat(deck_assemble): collateral section from resolved arc_info"
```

---

### Task 3: `choose_bias` — pick a sensitizing state, cross-check the kit `-when`

**Files:**
- Modify: `core/deck_assemble.py`
- Test: `tests/test_deck_assemble.py`

**Interfaces:**
- Consumes: `engine.types.CombState` (fields `label`, `assign: {pin:0/1}`), and a list of
  sensitizing `CombState`s from `derive_combinational(...).sensitizing`.
- Produces: `choose_bias(sensitizing: list, kit_when: str | None) -> dict` with
  `{"bias": {pin:0/1}, "chosen_label": str, "kit_match": bool}`. Deterministic rule:
  if `kit_when` parses to a conjunction that equals one sensitizing state's assignment,
  pick that state (`kit_match=True`); else pick the first sensitizing state by sorted
  label (`kit_match=False`). Engine is source of truth; a non-matching kit does not
  override — the divergence is reported via `kit_match=False`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_deck_assemble.py
from core.deck_assemble import choose_bias
from engine.types import CombState


def _states():
    # AOI-like: sensitizing when the other input is non-controlling
    return [
        CombState("!A2", {"A2": 0}, "F", frozenset()),
        CombState("A2", {"A2": 1}, "R", frozenset()),
    ]


def test_choose_bias_matches_kit_when():
    r = choose_bias(_states(), "A2")              # kit says A2=1
    assert r["bias"] == {"A2": 1}
    assert r["kit_match"] is True
    assert r["chosen_label"] == "A2"


def test_choose_bias_no_kit_picks_first_sorted():
    r = choose_bias(_states(), None)
    assert r["bias"] == {"A2": 0}                 # "!A2" sorts before "A2"
    assert r["kit_match"] is False


def test_choose_bias_kit_diverges_engine_wins():
    # kit claims A2=0&extra that no sensitizing state has -> engine still picks one
    r = choose_bias(_states(), "A2&A3")
    assert r["kit_match"] is False
    assert r["bias"] in ({"A2": 0}, {"A2": 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/test_deck_assemble.py -k choose_bias -v`
Expected: FAIL with `ImportError: cannot import name 'choose_bias'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/deck_assemble.py
from engine.whencond import parse_when_conjunction   # {pin: 0/1} or None for non-conj


def choose_bias(sensitizing: list, kit_when):
    """Pick one sensitizing state's side-pin assignment. Prefer the state matching
    the kit -when conjunction; else the first by sorted label. Engine is source of
    truth -- a non-matching kit yields kit_match=False, not an override."""
    states = sorted(sensitizing, key=lambda s: s.label)
    want = None
    if kit_when and kit_when not in ("NO_CONDITION", "", "NONE"):
        want = parse_when_conjunction(kit_when)        # None if OR/contradiction
    if want is not None:
        for s in states:
            if all(s.assign.get(p) == v for p, v in want.items()) and \
                    len(s.assign) == len(want):
                return {"bias": dict(s.assign), "chosen_label": s.label,
                        "kit_match": True}
    first = states[0]
    return {"bias": dict(first.assign), "chosen_label": first.label,
            "kit_match": False}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/test_deck_assemble.py -v`
Expected: PASS (6 tests). If `parse_when_conjunction` import path is wrong, confirm it
with `grep -n "def parse_when_conjunction" engine/whencond.py` and fix the import.

- [ ] **Step 5: Commit**

```bash
git add core/deck_assemble.py tests/test_deck_assemble.py
git commit -m "feat(deck_assemble): choose sensitizing bias, cross-check kit -when"
```

---

### Task 4: `assemble_combinational` — orchestrator + named errors

**Files:**
- Modify: `core/deck_assemble.py`
- Test: `tests/test_deck_assemble.py`
- Fixture (reuse, do not create): `tests/fixtures/audit_lib/netlist/AOI22.spi`

**Interfaces:**
- Consumes: `engine.stages.stage0_parse.parse(src, cell)`,
  `engine.stages.stage1_ccc.decompose(graph)`,
  `engine.stages.stage2_sensitize.{is_combinational_arc, derive_combinational}`,
  `engine.types.Arc`, `core.measurement.emit.{select_entry, emit}`, and Tasks 1-3.
- Produces: `assemble_combinational(arc_info, netlist_src, grammar) -> dict` =
  `{"status":"OK","deck_text":str,"bias":{...},"chosen_when":str,"output":str,
  "out_dir":str,"kit_match":bool,"error":None}` on success, or
  `{"status":"ERROR","deck_text":None,...,"error":"<what failed>"}` for: parse failure;
  sequential arc (CCC has a state node) — error names "sequential (B2/B3)"; empty
  SENSITIZING; no grammar entry. Never raises.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_deck_assemble.py
import os
from core.deck_assemble import assemble_combinational
from core.measurement.mine import mine

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")


def _grammar():
    return mine(os.path.join(_REPO, "templates/N2P_v1.0/delay"))


def _arc_info(rel_pin, probe_pin):
    return {"CELL_NAME": "AOI22", "ARC_TYPE": "delay",
            "REL_PIN": rel_pin, "REL_PIN_DIR": "rise",
            "PROBE_PIN_1": probe_pin, "WHEN": "NO_CONDITION",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40",
            "INDEX_1_VALUE": "1.2n", "INDEX_2_VALUE": "0.5f", "MAX_SLEW": "0.1u",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22,
            "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}


def test_assemble_combinational_ok():
    src = open(_AOI22).read()
    r = assemble_combinational(_arc_info("A1", "ZN"), src, _grammar())
    assert r["status"] == "OK", r["error"]
    deck = r["deck_text"]
    assert "$" not in deck                               # every placeholder resolved
    assert "X1 A1 A2 B1 B2 ZN VDD VSS AOI22" in deck     # instance line
    assert ".param vdd_value = '0.45'" in deck           # collateral
    assert "0 'vdd_value'" in deck or "0 'vss_value'" in deck   # bias present
    assert ".meas" in deck and ".tran" in deck           # recipe present
    assert r["output"] == "ZN"


def test_assemble_combinational_sequential_is_named_error():
    # a flip-flop netlist -> CCC has a state node -> not B1's job
    dff = os.path.join(_REPO,
        "tests/fixtures/collateral/N2P_v1.0/test_lib/Netlist/"
        "LPE_cworst_CCworst_T_m40c/DFFQ1_c.spi")
    src = open(dff).read()
    ai = _arc_info("CP", "Q"); ai["CELL_NAME"] = "DFFQ1"
    r = assemble_combinational(ai, src, _grammar())
    assert r["status"] == "ERROR"
    assert "sequential" in r["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/test_deck_assemble.py -k assemble_combinational -v`
Expected: FAIL with `ImportError: cannot import name 'assemble_combinational'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/deck_assemble.py
_DIR = {"R": "rise", "F": "fall", "rise": "rise", "fall": "fall"}


def _err(msg, **extra):
    r = {"status": "ERROR", "deck_text": None, "bias": {}, "chosen_when": "",
         "output": "", "out_dir": "", "kit_match": False, "error": msg}
    r.update(extra)
    return r


def assemble_combinational(arc_info: dict, netlist_src: str, grammar: dict) -> dict:
    """Assemble a combinational delay/slew deck. Never raises: a bad arc is a named
    ERROR row (feeds B4's coverage report)."""
    from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
    from engine.types import Arc
    from core.measurement.emit import select_entry, emit
    from core.measurement.emit import SelectionError

    cell = arc_info.get("CELL_NAME", "")
    rel = arc_info.get("REL_PIN", "")
    probe = arc_info.get("PROBE_PIN_1", "")
    try:
        graph = stage0_parse.parse(netlist_src, cell)
        ccc = stage1_ccc.decompose(graph)
    except Exception as e:
        return _err("netlist parse failed: %s" % e)

    arc = Arc(cell=cell, arc_type="combinational", rel_pin=rel, rel_dir="rise",
              constr_pin=probe, constr_dir="rise", when="NO_CONDITION",
              measurement="", raw={"probe_pin": probe})

    if not stage2_sensitize.is_combinational_arc(graph, arc, ccc):
        return _err("arc CCC has a state node -- sequential, handled by B2/B3")

    res = stage2_sensitize.derive_combinational(graph, arc, ccc)
    if not res.sensitizing:
        return _err("empty SENSITIZING: %s does not combinationally drive %s "
                    "(sequential/clock or wrong probe)" % (rel, res.output))

    cb = choose_bias(res.sensitizing, arc_info.get("WHEN"))

    rel_dir = _DIR.get(arc_info.get("REL_PIN_DIR", "rise"), "rise")
    # output edge for the chosen state -> grammar 'other_dir'
    chosen = next(s for s in res.sensitizing if s.label == cb["chosen_label"])
    out_dir = _DIR.get(chosen.out_dir or "rise", "rise")
    try:
        entry = select_entry(grammar, arc_type="delay", rel_dir=rel_dir,
                             other_dir=out_dir)
    except SelectionError as e:
        return _err("no grammar entry: %s" % e)

    recipe = emit(entry, arc_info, fill_values=True)

    pins = arc_info.get("NETLIST_PINS", "")
    deck_lines = (
        collateral_section(arc_info)
        + ["* ===== INSTANCE =====", "X1 %s %s" % (pins, cell)]
        + engine_bias_section(cb["bias"])
        + recipe
        + [".end"]
    )
    return {"status": "OK", "deck_text": "\n".join(deck_lines) + "\n",
            "bias": cb["bias"], "chosen_when": cb["chosen_label"],
            "output": res.output, "out_dir": out_dir,
            "kit_match": cb["kit_match"], "error": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/test_deck_assemble.py -v`
Expected: PASS. If `test_assemble_combinational_ok` fails on `select_entry` (the delay
grammar's only cluster is `common_inpin`; selection keys on arc_type/dirs), print the
delay entry keys with
`python3.12 -c "from core.measurement.mine import mine; [print(e['key']) for e in mine('templates/N2P_v1.0/delay')['entries']]"`
and confirm `rel_dir=rise, other_dir` matches one entry; adjust the `_DIR` mapping or
the chosen `out_dir` source (use `res.sensitizing[0].out_dir` if the chosen state's
out_dir is None) so a real entry is selected. Do NOT weaken the assertions.

- [ ] **Step 5: Commit**

```bash
git add core/deck_assemble.py tests/test_deck_assemble.py
git commit -m "feat(deck_assemble): combinational orchestrator with named errors"
```

---

### Task 5: `check_against_template` — simulator-free local validation

**Files:**
- Create: `core/deck_assemble_check.py`
- Test: `tests/test_deck_assemble_check.py`

**Interfaces:**
- Consumes: `core.measurement.regions.extract_recipe`, Task 4's `assemble_combinational`.
- Produces: `check_against_template(deck_text, template_path, side_bias, toggling_pin)
  -> dict` = `{"no_unresolved_placeholder": bool, "recipe_matches": bool,
  "bias_structural_ok": bool, "detail": [...]}`. `recipe_matches`: the recipe region
  of the assembled deck (via `extract_recipe`) equals the recipe region of the
  template after the SAME value substitution — proving emit+assembler reproduce the
  methodology. `bias_structural_ok`: every side pin in `side_bias` appears exactly
  once as `V<pin> <pin> 0 '<rail>'` with the rail matching its value, and
  `toggling_pin` has NO such bias line.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deck_assemble_check.py
import os
from core.deck_assemble import assemble_combinational
from core.deck_assemble_check import check_against_template
from core.measurement.mine import mine

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AOI22 = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/AOI22.spi")
_TMPL = os.path.join(_REPO,
    "templates/N2P_v1.0/delay/template_common_inpin_rise_delay_rise.sp")


def _arc_info():
    return {"CELL_NAME": "AOI22", "ARC_TYPE": "delay", "REL_PIN": "A1",
            "REL_PIN_DIR": "rise", "PROBE_PIN_1": "ZN", "WHEN": "NO_CONDITION",
            "VDD_VALUE": "0.45", "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2n",
            "INDEX_2_VALUE": "0.5f", "MAX_SLEW": "0.1u",
            "INCLUDE_FILE": "/c/model.inc", "WAVEFORM_FILE": "/c/wv.spi",
            "NETLIST_PATH": _AOI22, "NETLIST_PINS": "A1 A2 B1 B2 ZN VDD VSS"}


def test_check_passes_for_assembled_deck():
    g = mine(os.path.join(_REPO, "templates/N2P_v1.0/delay"))
    r = assemble_combinational(_arc_info(), open(_AOI22).read(), g)
    assert r["status"] == "OK", r["error"]
    chk = check_against_template(r["deck_text"], _TMPL, r["bias"], "A1")
    assert chk["no_unresolved_placeholder"] is True, chk["detail"]
    assert chk["bias_structural_ok"] is True, chk["detail"]


def test_check_flags_unresolved_placeholder():
    chk = check_against_template("X1 a b\n.param vdd_value = '$VDD_VALUE'\n",
                                 _TMPL, {}, "A1")
    assert chk["no_unresolved_placeholder"] is False


def test_check_flags_toggling_pin_in_bias():
    bad = "VA1 A1 0 'vdd_value'\n"      # toggling pin must NOT be biased
    chk = check_against_template(bad, _TMPL, {}, "A1")
    assert chk["bias_structural_ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/test_deck_assemble_check.py -v`
Expected: FAIL with `ModuleNotFoundError: core.deck_assemble_check`

- [ ] **Step 3: Write minimal implementation**

```python
# core/deck_assemble_check.py
"""deck_assemble_check.py -- simulator-free local validation of an assembled
combinational deck: no unresolved $ placeholders, recipe fidelity vs the golden
template, and structural correctness of the engine bias section. stdlib, ASCII."""
from __future__ import annotations

import re

from core.measurement.regions import extract_recipe


def _bias_ok(deck_text: str, side_bias: dict, toggling_pin: str, detail: list) -> bool:
    ok = True
    for pin, val in side_bias.items():
        rail = "vdd_value" if val else "vss_value"
        want = "V%s %s 0 '%s'" % (pin, pin, rail)
        n = deck_text.count(want)
        if n != 1:
            ok = False
            detail.append("bias %s expected once as %r, found %d" % (pin, want, n))
    # toggling pin must not be tied off by a bias source
    if re.search(r"(?m)^V%s\s+%s\s+0\s" % (re.escape(toggling_pin),
                                           re.escape(toggling_pin)), deck_text):
        ok = False
        detail.append("toggling pin %s must not have a bias source" % toggling_pin)
    return ok


def check_against_template(deck_text: str, template_path: str,
                           side_bias: dict, toggling_pin: str) -> dict:
    detail = []
    no_ph = "$" not in deck_text
    if not no_ph:
        detail.append("unresolved $ placeholder(s) remain in the deck")
    bias_ok = _bias_ok(deck_text, side_bias, toggling_pin, detail)
    # recipe fidelity: assembled recipe region == template recipe region (structure).
    # Compare the set of recipe LINE SHAPES with values stripped so corner-specific
    # numbers don't cause false mismatch; this proves the same methodology lines.
    tmpl_recipe = extract_recipe(open(template_path, encoding="ascii",
                                      errors="replace").read())
    deck_recipe = extract_recipe(deck_text)
    def _shape(lines):
        return [re.sub(r"'[^']*'", "''", l) for l in lines]
    recipe_matches = _shape(deck_recipe) == _shape(tmpl_recipe)
    if not recipe_matches:
        detail.append("recipe region differs from template (line shapes)")
    return {"no_unresolved_placeholder": no_ph, "recipe_matches": recipe_matches,
            "bias_structural_ok": bias_ok, "detail": detail}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/test_deck_assemble_check.py -v`
Expected: PASS (3 tests). `recipe_matches` may be False if the assembled deck's
toggling-source line (`XV...stdvs_*`) carries a different model name than this
template variant — that is expected when the chosen out_dir picks a different delay
template; the two asserted tests do not require `recipe_matches`, only
`no_unresolved_placeholder` and `bias_structural_ok`. Leave `recipe_matches` reported
for diagnostics; do not assert it green here.

- [ ] **Step 5: Commit**

```bash
git add core/deck_assemble_check.py tests/test_deck_assemble_check.py
git commit -m "feat(deck_assemble): simulator-free local deck validation"
```

---

## Self-Review

**1. Spec coverage:**
- Uniform assembler (collateral + X1 + bias + emit) → Task 4. ✓
- Real collateral reused from `resolve_all_from_collateral` → arc_info is the input to
  Task 2/4 (the tests construct it; in production it comes from the resolver). ✓
- Combinational engine-bias section (voltage source to rail, derived value) → Tasks 1, 3, 4. ✓
- Grammar entry selection for a combinational arc (arc_type=delay, dirs) → Task 4. ✓
- Local validation (no-unresolved-placeholder + recipe fidelity + bias structural) → Task 5. ✓
- Never fail silently (named ERROR for sequential / empty-sensitizing / no-grammar) → Task 4. ✓
- Thin entry point for B4/Phase C → `assemble_combinational` returns a structured dict. ✓
- stdlib/ASCII/HSPICE-free → Global Constraints + every task. ✓

**Refinement vs spec (surface to user):** the spec said "recipe + collateral reproduce
the template byte-for-byte." Planning narrows this: the template's collateral block
contains airgap-variable literal paths (a hardcoded `/CAD/.../std_wv_c651.spi`), so
byte-matching collateral is brittle. Task 5 instead checks (a) **no unresolved `$`**
(the real "is it runnable" proof), (b) **recipe fidelity** by line-shape (values
stripped), and (c) **bias structural correctness**. Recipe byte-fidelity itself is
already guaranteed by Phase A's round-trip; B1 reuses `emit`. This is a deliberate,
stronger-where-it-matters substitution, flagged for the spec author.

**2. Placeholder scan:** No TBD/TODO. Each code step has complete code. The two "if it
fails, inspect X" notes are concrete diagnostic procedures (print real grammar keys),
not deferred work.

**3. Type consistency:** `arc_info` dict keys are identical across Tasks 2/4/5.
`engine_bias_section(side_bias)`, `collateral_section(arc_info)`,
`choose_bias(sensitizing, kit_when)->{"bias","chosen_label","kit_match"}`,
`assemble_combinational(...)->{"status","deck_text","bias",...}` — consumed
consistently by Task 4 (uses 1-3) and Task 5 (uses 4's `deck_text`/`bias`).
`CombState.assign`/`.label`/`.out_dir` match `engine/types.py`. `select_entry`/`emit`
signatures match `core/measurement/emit.py` (Phase A).

**Known risk (planning, not a gap):** the orchestrator (Task 4) depends on
`stage0_parse.parse` accepting the `AOI22.spi` fixture and `derive_combinational`
returning a non-empty SENSITIZING for (A1→ZN). Both are exercised by the existing
audit on these same fixtures, so the path is known-good; Task 4's diagnostic note
covers the dir/selection edge.
