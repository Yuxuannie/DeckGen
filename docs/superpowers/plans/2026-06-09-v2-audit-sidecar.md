# v2 Audit Sidecar (--verify) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount the v2 engine onto the v1 production flow as a read-only audit layer: `deckgen.py --verify` runs every resolved arc through `engine.pipeline.run_pipeline_src` and writes a `verify.json` verdict sidecar next to each deck, without changing a single v1 output byte.

**Architecture:** One new adapter module (`core/verify_sidecar.py`) maps v1's resolved per-arc data to the four engine inputs and writes the sidecar; one new engine function (`p3_property` in `engine/stages/stage5_verify.py`) implements the P3 "measurement context consistent" check from v1's substituted deck lines; `deckgen.py`/`core/batch.py` get a `--verify` flag threaded through with lazy imports so the flag-off path executes zero new code. Engine failures always degrade to an ERROR sidecar, never to a broken run.

**Tech Stack:** Python stdlib only (json, re, subprocess, datetime, dataclasses). Tests: pytest under python3.12. Spec: `docs/superpowers/specs/2026-06-09-v2-audit-sidecar-design.md`.

**Conventions that apply to every task:** run commands from the repo root (`/Users/nieyuxuan/Downloads/Work/4-MCQC/DeckGen`); zero non-ASCII bytes in any file (use `--`, never em-dash); never weaken an existing test assertion; all new files ASCII-checked before commit with `grep -rPn '[\x80-\xff]' <files>` (output must be empty).

---

### Task 1: engine version constant + record mapping helpers

**Files:**
- Modify: `engine/__init__.py` (add one line)
- Create: `core/verify_sidecar.py`
- Test: `tests/test_verify_sidecar.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verify_sidecar.py`:

```python
"""core/verify_sidecar.py -- v1 -> engine adapter for the --verify audit layer.
Spec: docs/superpowers/specs/2026-06-09-v2-audit-sidecar-design.md
"""
import json
import os

import pytest

from core.verify_sidecar import build_record, to_lit_when

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arc_info(**over):
    """Minimal collateral-path arc_info (spec section 3.1)."""
    info = {
        'CELL_NAME': 'DFFQ1', 'ARC_TYPE': 'hold',
        'REL_PIN': 'CP', 'REL_PIN_DIR': 'rise',
        'CONSTR_PIN': 'D', 'CONSTR_PIN_DIR': 'fall',
        'WHEN': '!SE&SI', 'LIT_WHEN': 'notSE_SI',
        'VECTOR': 'xxRxFxx',
        'PROBE_PIN_1': 'Q',
        'NETLIST_PATH': '/no/such.spi', 'INCLUDE_FILE': '/no/model.inc',
        'VDD_VALUE': '0.45', 'SIDE_PIN_STATES': '',
    }
    info.update(over)
    return info


class TestToLitWhen:
    def test_literal_converts(self):
        assert to_lit_when('!SE&SI') == 'notSE_SI'

    def test_multi_term(self):
        assert to_lit_when('!I0 & !I1 & I2') == 'notI0_notI1_I2'

    def test_no_condition_is_empty(self):
        assert to_lit_when('NO_CONDITION') == ''
        assert to_lit_when('') == ''
        assert to_lit_when(None) == ''


class TestBuildRecord:
    def test_collateral_fields(self):
        rec = build_record(_arc_info(), {'arc_id': 'a1', 'corner': 'c1'})
        assert rec['cell'] == 'DFFQ1'
        assert rec['arc_type'] == 'hold'
        assert rec['rel_pin'] == 'CP' and rec['rel_dir'] == 'rise'
        assert rec['constr_pin'] == 'D' and rec['constr_dir'] == 'fall'
        assert rec['when'] == 'notSE_SI'          # LIT_WHEN verbatim
        assert rec['when_literal'] == '!SE&SI'
        assert rec['vector'] == 'xxRxFxx'
        assert rec['probe_list'] == ['Q']
        assert rec['arc_id'] == 'a1' and rec['corner'] == 'c1'

    def test_no_condition_normalizes_to_empty(self):
        # Spec 3.1: the sentinel must never reach parse_when as a token.
        rec = build_record(_arc_info(WHEN='NO_CONDITION',
                                     LIT_WHEN='NO_CONDITION'), None)
        assert rec['when'] == ''

    def test_legacy_when_converted(self):
        # legacy arc_info (from _job_to_arc_info) has no WHEN/LIT_WHEN keys
        info = _arc_info()
        for k in ('WHEN', 'LIT_WHEN', 'VECTOR'):
            del info[k]
        rec = build_record(info, {'when': '!SE&SI', 'probe_pin': 'Q'})
        assert rec['when'] == 'notSE_SI'
        assert rec['vector'] == ''
        assert rec['probe_list'] == ['Q']

    def test_probe_list_numeric_order(self):
        rec = build_record(_arc_info(PROBE_PIN_2='QN'), None)
        assert rec['probe_list'] == ['Q', 'QN']

    def test_engine_version_constant_exists(self):
        import engine
        assert engine.__version__ == '2.0-2b'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'core.verify_sidecar'`

- [ ] **Step 3: Add the version constant**

In `engine/__init__.py`, after the `from engine.pipeline import run_pipeline` line, add:

```python
__version__ = "2.0-2b"
```

- [ ] **Step 4: Create `core/verify_sidecar.py` with the record helpers**

```python
"""verify_sidecar.py -- v1 -> v2-engine adapter for the --verify audit layer.

Stage-A mounting (spec docs/superpowers/specs/2026-06-09-v2-audit-sidecar-design.md):
v1 stays the production path; for every arc it resolves, this module additionally
runs engine.pipeline.run_pipeline_src and writes a verdict sidecar JSON next to
the generated deck. v1 deck bytes are NEVER touched; an engine failure always
degrades to a status=ERROR sidecar, never to a broken run.

Imported LAZILY by deckgen.py / core/batch.py (only under --verify), so the
flag-off production path executes none of this module -- including the engine
imports below.
"""

import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone

from engine.pipeline import run_pipeline_src
from engine.stages.stage5_verify import MeasContext, p3_property


class VerifyInputError(Exception):
    """A v1-side input needed by the engine is missing (e.g. netlist text)."""


# ---------------------------------------------------------------------------
# record mapping (spec section 3.1)
# ---------------------------------------------------------------------------

def to_lit_when(when):
    """Literal '!SE&SI' -> engine-encoded 'notSE_SI'; NO_CONDITION/empty -> ''."""
    if not when or when.strip() in ('', 'NO_CONDITION'):
        return ''
    toks = []
    for t in when.split('&'):
        t = t.strip()
        if not t:
            continue
        toks.append('not' + t[1:] if t.startswith('!') else t)
    return '_'.join(toks)


def build_record(arc_info, job=None):
    """Map v1's resolved arc_info (+ optional batch job dict) to the engine
    record consumed by Arc.from_record. when/vector are optional oracles; the
    engine derives independently when they are absent."""
    job = job or {}
    lit = (arc_info.get('LIT_WHEN') or '').strip()
    if lit and lit != 'NO_CONDITION':
        when = lit
    else:
        when = to_lit_when(arc_info.get('WHEN') or job.get('when') or '')
    # NO_CONDITION normalization (spec 3.1): the sentinel never reaches parse_when.
    if when == 'NO_CONDITION':
        when = ''

    probe_list = []
    i = 1
    while True:
        p = arc_info.get('PROBE_PIN_%d' % i)
        if not p:
            break
        probe_list.append(p)
        i += 1
    if not probe_list and job.get('probe_pin'):
        probe_list = [job['probe_pin']]

    return {
        'cell': arc_info['CELL_NAME'],
        'arc_type': arc_info['ARC_TYPE'],
        'rel_pin': arc_info['REL_PIN'],
        'rel_dir': arc_info['REL_PIN_DIR'],
        'constr_pin': arc_info.get('CONSTR_PIN') or arc_info['REL_PIN'],
        'constr_dir': arc_info.get('CONSTR_PIN_DIR') or '',
        'when': when,
        'lit_when': lit,
        'when_literal': arc_info.get('WHEN') or job.get('when', '') or '',
        'vector': arc_info.get('VECTOR', '') or '',
        'probe_list': probe_list,
        'measurement': '',          # filled by write_sidecar after extraction
        'arc_id': job.get('arc_id', '') or '',
        'corner': job.get('corner', '') or '',
    }
```

(`MeasContext`/`p3_property` do not exist yet -- Task 4 creates them. To keep this
task green on its own, ALSO add the two names as a temporary import guard is NOT
allowed; instead Task 1 imports only what exists. So in THIS task, omit the line
`from engine.stages.stage5_verify import MeasContext, p3_property` -- it is added
in Task 7 when `write_sidecar` needs it. The module header above shows the final
docstring; the import block for Task 1 is exactly:)

```python
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone

from engine.pipeline import run_pipeline_src


class VerifyInputError(Exception):
    """A v1-side input needed by the engine is missing (e.g. netlist text)."""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -v`
Expected: 7 passed

- [ ] **Step 6: Full suite + ASCII scan + commit**

```bash
python3.12 -m pytest tests/ -q
grep -rPn '[\x80-\xff]' core/verify_sidecar.py engine/__init__.py tests/test_verify_sidecar.py
git add core/verify_sidecar.py engine/__init__.py tests/test_verify_sidecar.py
git commit -m "feat(verify): record mapping v1 arc_info -> engine record (+engine __version__)"
```

---

### Task 2: measurement-block extraction (loud failure)

**Files:**
- Modify: `core/verify_sidecar.py`
- Test: `tests/test_verify_sidecar.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_verify_sidecar.py`)

```python
from core.verify_sidecar import extract_meas_block

DECK_LINES = [
    "* Slew and load information\n",
    ".param cl = '0.001p'\n",
    "* Measurements\n",
    ".meas cp2q_del1 trig v(CP) val='vdd_value/2' cross=3 targ v(Q) val='vdd_value/2' cross=1 td='related_pin_t03'\n",
    ".meas cp2cp trig v(CP) val='vdd_value/2' cross=3 targ v(D) val='vdd_value/2' cross=4\n",
    " \n",
    "* Transient Sim Command\n",
    ".tran 1p 50u sweep monte=1\n",
    ".end\n",
]


class TestExtractMeasBlock:
    def test_marker_block_extracted(self):
        meas, note = extract_meas_block(DECK_LINES)
        assert note is None
        assert meas.count('.meas') == 2
        assert '.tran' not in meas

    def test_no_marker_falls_back_to_meas_lines(self):
        lines = [l for l in DECK_LINES if 'Measurements' not in l]
        meas, note = extract_meas_block(lines)
        assert note is None
        assert meas.count('.meas') == 2

    def test_nothing_found_is_loud(self):
        # Spec 3.3: an empty meas block is NEVER silent.
        lines = [l for l in DECK_LINES if '.meas' not in l
                 and 'Measurements' not in l]
        meas, note = extract_meas_block(lines)
        assert meas == ''
        assert note is not None and 'meas extraction failed' in note
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -k ExtractMeasBlock -v`
Expected: ImportError (`extract_meas_block` not defined)

- [ ] **Step 3: Implement** (append to `core/verify_sidecar.py`)

```python
# ---------------------------------------------------------------------------
# meas extraction (spec section 3.3) -- from v1's substituted deck lines
# ---------------------------------------------------------------------------

MEAS_MARKER = '* Measurements'


def extract_meas_block(deck_lines):
    """Return (meas_text, note). note is None on success; on failure it is a
    human-readable reason that MUST surface in the sidecar (never silent)."""
    lines = [l if isinstance(l, str) else str(l) for l in deck_lines]
    start = None
    for i, l in enumerate(lines):
        if MEAS_MARKER in l:
            start = i
            break
    if start is not None:
        block = []
        for l in lines[start:]:
            if l.lstrip().lower().startswith('.tran'):
                break
            block.append(l)
        text = ''.join(block).strip('\n')
        if '.meas' in text:
            return text, None
    meas_only = [l for l in lines if l.lstrip().startswith('.meas')]
    if meas_only:
        return ''.join(meas_only).strip('\n'), None
    return '', ("meas extraction failed: marker '* Measurements' absent "
                "and no .meas lines")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add core/verify_sidecar.py tests/test_verify_sidecar.py
git commit -m "feat(verify): meas-block extraction from substituted deck lines, loud on failure"
```

---

### Task 3: golden biases + three-state bias_match

**Files:**
- Modify: `core/verify_sidecar.py`
- Test: `tests/test_verify_sidecar.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from core.verify_sidecar import classify_bias_match, derive_golden_biases


class TestGoldenBiases:
    def test_from_when_literal_skips_driven_pins(self):
        # mirrors deck_builder._generate_when_condition_lines semantics
        g = derive_golden_biases(_arc_info(WHEN='!SE&SI&D'))
        assert g == {'SE': 0, 'SI': 1}      # D is the constr pin -> skipped

    def test_side_pin_states_wins(self):
        g = derive_golden_biases(_arc_info(SIDE_PIN_STATES='SE=1 SI=0'))
        assert g == {'SE': 1, 'SI': 0}

    def test_no_condition_empty(self):
        assert derive_golden_biases(_arc_info(WHEN='NO_CONDITION')) == {}


class TestBiasMatch:
    # spec section 5: per-pin three-state, masked pins are NEVER mismatches
    def test_match(self):
        out = classify_bias_match({'SE': 0, 'SI': 1}, ['SE'], ['SI'],
                                  {'SE': 0, 'SI': 1})
        assert out == 'MATCH'

    def test_critical_mismatch(self):
        out = classify_bias_match({'SE': 1, 'SI': 1}, ['SE'], ['SI'],
                                  {'SE': 0, 'SI': 1})
        assert out.startswith('MISMATCH:') and 'SE' in out

    def test_masked_disagreement_is_not_mismatch(self):
        out = classify_bias_match({'SE': 0, 'SI': 1}, ['SE'], ['SI'],
                                  {'SE': 0, 'SI': 0})
        assert out.startswith('MATCH')
        assert 'non-critical' in out and 'SI' in out

    def test_only_masked_compared(self):
        out = classify_bias_match({'SI': 1}, [], ['SI'], {'SI': 0})
        assert out == 'NON_CRITICAL'

    def test_no_golden(self):
        out = classify_bias_match({'SE': 0}, ['SE'], [], {})
        assert out.startswith('N/A')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -k "GoldenBiases or BiasMatch" -v`
Expected: ImportError

- [ ] **Step 3: Implement** (append to `core/verify_sidecar.py`)

```python
# ---------------------------------------------------------------------------
# golden biases + three-state bias match (spec section 5)
# ---------------------------------------------------------------------------

def derive_golden_biases(arc_info):
    """The biases v1's deck drives, with the exact semantics of
    deck_builder._generate_when_condition_lines (skip rel/constr pins;
    '!X' -> 0 else 1). A non-empty SIDE_PIN_STATES wins (more explicit)."""
    out = {}
    for tok in (arc_info.get('SIDE_PIN_STATES') or '').split():
        pin, _, val = tok.partition('=')
        if pin and val in ('0', '1'):
            out[pin] = int(val)
    if out:
        return out
    when = arc_info.get('WHEN', '') or ''
    if not when or when == 'NO_CONDITION':
        return {}
    rel = arc_info.get('REL_PIN', '')
    constr = arc_info.get('CONSTR_PIN', '')
    for cond in when.split('&'):
        cond = cond.strip()
        if not cond:
            continue
        pin = cond.lstrip('!')
        if pin in (rel, constr):
            continue
        out[pin] = 0 if cond.startswith('!') else 1
    return out


def classify_bias_match(derived, set_pins, masked_pins, golden):
    """Three-state aggregate (spec section 5): MISMATCH only for set-pin
    (critical) disagreements; masked pins are non-critical by definition."""
    if not golden:
        return 'N/A (no golden biases in deck)'
    crit_mism, crit_cmp, noncrit_diff, noncrit_cmp = [], 0, [], 0
    for pin, gval in golden.items():
        if pin not in derived:
            continue
        dval = derived[pin]
        if pin in set_pins:
            crit_cmp += 1
            if dval != gval:
                crit_mism.append('%s(derived=%s golden=%s)' % (pin, dval, gval))
        elif pin in masked_pins:
            noncrit_cmp += 1
            if dval != gval:
                noncrit_diff.append('%s derived=%s golden=%s' % (pin, dval, gval))
    if crit_mism:
        return 'MISMATCH: ' + ', '.join(crit_mism)
    if crit_cmp:
        if noncrit_diff:
            return 'MATCH (non-critical: ' + ', '.join(noncrit_diff) + ')'
        return 'MATCH'
    if noncrit_cmp:
        return 'NON_CRITICAL'
    return 'N/A (no golden biases in deck)'
```

- [ ] **Step 4: Run tests + commit**

```bash
python3.12 -m pytest tests/test_verify_sidecar.py -v   # all pass
git add core/verify_sidecar.py tests/test_verify_sidecar.py
git commit -m "feat(verify): golden-bias derivation + three-state bias_match"
```

---

### Task 4: MeasContext + p3_property static checks (a) and (b)

**Files:**
- Modify: `engine/stages/stage5_verify.py`
- Test: `tests/engine/test_p3.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/test_p3.py`:

```python
"""P3 (measurement context consistent) -- spec section 4 of
docs/superpowers/specs/2026-06-09-v2-audit-sidecar-design.md.
Worked example: mpw/template__CP__rise__fall__1.sp with max_slew=1n."""
from engine.stages.stage5_verify import MeasContext, p3_property
from engine.types import Arc, Derivation, InitializationResult, PStatus

# stdvs_mpw_rise_fall_rise_fall with t01=10n t02=20n t03=50n t04=55n (ms=1n)
EDGES = [("t01", 10.0, "rise"), ("t02", 20.0, "fall"),
         ("t03", 50.0, "rise"), ("t04", 55.0, "fall")]


def _arc(rel_dir="rise"):
    return Arc(cell="X", arc_type="hold", rel_pin="CP", rel_dir=rel_dir,
               constr_pin="D", constr_dir="fall", when="", measurement="")


def _init(precycles=1, probes=("x1.ml_a",)):
    return InitializationResult(
        required_state={}, stimulus=[],
        precycle_count=Derivation(precycles, "test", "S3.init"),
        probes=list(probes))


def _ctx(**over):
    kw = dict(rel_edges=EDGES, trig_cross=3, trig_td_ns=0.0,
              capture_t_ns=50.0, capture_dir="rise", vdd=0.45, notes=[])
    kw.update(over)
    return MeasContext(**kw)


def test_static_pass_is_stub_without_sim():
    p3 = p3_property(_ctx(), _init(), _arc())
    assert p3.status is PStatus.STUB          # (a),(b) green; (c) NOT RUN
    assert any("ALIGNED" in d for d in p3.detail)
    assert any("NOT RUN" in d for d in p3.detail)


def test_misaligned_capture_dir_fails():
    p3 = p3_property(_ctx(capture_dir="fall"), _init(), _arc("rise"))
    assert p3.status is PStatus.FAIL
    assert any("MISALIGNED" in d for d in p3.detail)


def test_precycle_mismatch_fails():
    # capture at t01: zero full cycles before it, S3 derived 1
    p3 = p3_property(_ctx(capture_t_ns=10.0), _init(precycles=1), _arc())
    assert p3.status is PStatus.FAIL
    assert any("MISMATCH" in d for d in p3.detail)


def test_unresolved_context_is_stub_with_reason():
    p3 = p3_property(_ctx(capture_t_ns=None,
                          notes=["UNRESOLVED: .param weird = 'a*b'"]),
                     _init(), _arc())
    assert p3.status is PStatus.STUB
    assert any("UNRESOLVED" in d for d in p3.detail)


def test_no_context_is_stub():
    p3 = p3_property(None, _init(), _arc())
    assert p3.status is PStatus.STUB
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest tests/engine/test_p3.py -v`
Expected: ImportError (`MeasContext` not defined)

- [ ] **Step 3: Implement** -- append to `engine/stages/stage5_verify.py` (after the existing `p2_property`, before `verify`); also add the needed imports at the top of the file (`from dataclasses import dataclass, field` and `from typing import List, Optional, Tuple`; keep existing imports untouched):

```python
# ---------------------------------------------------------------------------
# P3 -- measurement context consistent (spec 2026-06-09 audit sidecar, S4)
# ---------------------------------------------------------------------------
@dataclass
class MeasContext:
    """Measurement context lifted from v1's SUBSTITUTED deck lines (never TCL).

    Cross-counting convention (normative): the capture edge is the
    trig_cross-th crossing of v(rel_pin) counted from max(t=0, trig-clause td);
    a td= in the targ clause constrains the target search only and never
    shifts the capture count. capture_t_ns is None when extraction could not
    resolve the context (notes say why) -> P3 reports STUB, never a crash.
    """
    rel_edges: List[Tuple[str, float, str]]   # (name, t_ns, "rise"|"fall")
    trig_cross: int
    trig_td_ns: float
    capture_t_ns: Optional[float]
    capture_dir: str = ""
    vdd: float = 0.0
    notes: List[str] = field(default_factory=list)


def p3_property(ctx, init, arc, sim_data=None) -> Property:
    """P3 with the same self-describing detail style as P1/P2 (value <= reason).

    (a) capture-edge alignment and (b) pre-cycle count are static; (c) settled
    state nodes needs sim_data = (times, traces) from engine.wave.parse_csdf.
    Status: any failed check -> FAIL; statics green without sim -> STUB;
    all green with sim -> PASS. STUB means "could not evaluate", never
    "evaluated and failed".
    """
    if ctx is None or ctx.capture_t_ns is None:
        detail = list(ctx.notes) if ctx is not None else ["no meas context built"]
        detail.append("check      : meas-context extraction UNRESOLVED -- STUB")
        return Property("P3", "Meas context", PStatus.STUB, detail=detail)

    detail: list = list(ctx.notes)
    failed = False

    # (a) capture-edge alignment
    aligned = ctx.capture_dir == arc.rel_dir
    failed |= not aligned
    detail.append(
        f"capture edge : {ctx.capture_t_ns:g}ns ({ctx.capture_dir})  "
        f"<= .meas trig cross={ctx.trig_cross} from t={ctx.trig_td_ns:g}ns "
        f"(targ-clause td not counted)")
    detail.append(
        f"arc expects  : {arc.rel_dir}  <= arc.rel_dir -- "
        f"{'ALIGNED' if aligned else 'MISALIGNED'}")

    # (b) pre-cycle count: full rel-pin cycles strictly before the capture edge
    before = [e for e in ctx.rel_edges if e[1] < ctx.capture_t_ns]
    cycles = len(before) // 2          # stdvs edges strictly alternate
    derived = init.precycle_count.value
    ok_b = cycles == derived
    failed |= not ok_b
    detail.append(
        f"precycles    : {cycles} full {arc.rel_pin} cycle(s) before capture  "
        f"<= edge schedule ({len(before)} edges before {ctx.capture_t_ns:g}ns)")
    detail.append(
        f"derived      : {derived}  <= {init.precycle_count.reason} -- "
        f"{'MATCH' if ok_b else 'MISMATCH'}")

    # (c) state nodes settled (definite 0/1 per MARGIN) before the capture edge
    if sim_data is None:
        if failed:
            return Property("P3", "Meas context", PStatus.FAIL, detail=detail)
        detail.append("check      : settled-before-capture -- NOT RUN "
                      "(no sim; run --sim for P3(c))")
        return Property("P3", "Meas context", PStatus.STUB, detail=detail)

    from engine.sim import MARGIN, _bit
    from engine.wave import select
    times, traces = sim_data
    t_cap_s = ctx.capture_t_ns * 1e-9
    for node in init.probes:
        sel = select(traces, [node])
        if not sel or not times:
            failed = True
            detail.append(f"{node:<12}: trace MISSING in sim output  [FAIL]")
            continue
        ys = next(iter(sel.values()))
        idx = max((i for i, t in enumerate(times[:len(ys)]) if t <= t_cap_s),
                  default=None)
        if idx is None:
            failed = True
            detail.append(f"{node:<12}: no sample at or before capture  [FAIL]")
            continue
        v = ys[idx]
        bit = _bit(v, ctx.vdd) if ctx.vdd else None
        ok = bit is not None
        failed |= not ok
        detail.append(
            f"{node:<12}: {v:.3f}V -> {bit if ok else 'X (mid-rail)'}  "
            f"<= within MARGIN={MARGIN} of rail @ t<={ctx.capture_t_ns:g}ns  "
            f"[{'ok' if ok else 'FAIL'}]")
    detail.append("check      : settled-before-capture -- RAN")
    return Property("P3", "Meas context",
                    PStatus.FAIL if failed else PStatus.PASS, detail=detail)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.12 -m pytest tests/engine/test_p3.py tests/engine/ -q`
Expected: all pass (including all pre-existing engine tests)

- [ ] **Step 5: Commit**

```bash
git add engine/stages/stage5_verify.py tests/engine/test_p3.py
git commit -m "feat(engine): P3 static checks -- capture-edge alignment + pre-cycle count"
```

---

### Task 5: P3 check (c) -- settled state nodes from CSDF

**Files:**
- Modify: `engine/stages/stage5_verify.py` (already done in Task 4 -- check (c) code is included there)
- Test: `tests/engine/test_p3.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/engine/test_p3.py`)

```python
from engine.wave import parse_csdf

CSDF_SETTLED = """#H
#N 'v(x1.ml_a)' 'v(x1.sl_a)'
#C 0.0 2  0.0 0.45
#C 4.0e-8 2  0.448 0.002
#C 6.0e-8 2  0.45 0.0
"""

CSDF_MIDRAIL = """#H
#N 'v(x1.ml_a)' 'v(x1.sl_a)'
#C 0.0 2  0.0 0.45
#C 4.0e-8 2  0.225 0.002
#C 6.0e-8 2  0.45 0.0
"""


def test_settled_nodes_pass_with_sim():
    sim = parse_csdf(CSDF_SETTLED)
    p3 = p3_property(_ctx(), _init(probes=("x1.ml_a", "x1.sl_a")), _arc(), sim)
    assert p3.status is PStatus.PASS
    assert any("RAN" in d for d in p3.detail)


def test_midrail_node_fails_with_sim():
    # x1.ml_a sits at VDD/2 at the last sample before capture (50ns)
    sim = parse_csdf(CSDF_MIDRAIL)
    p3 = p3_property(_ctx(), _init(probes=("x1.ml_a", "x1.sl_a")), _arc(), sim)
    assert p3.status is PStatus.FAIL
    assert any("mid-rail" in d for d in p3.detail)


def test_missing_trace_fails_with_sim():
    sim = parse_csdf(CSDF_SETTLED)
    p3 = p3_property(_ctx(), _init(probes=("x1.nope",)), _arc(), sim)
    assert p3.status is PStatus.FAIL
    assert any("MISSING" in d for d in p3.detail)
```

- [ ] **Step 2: Run tests**

Run: `python3.12 -m pytest tests/engine/test_p3.py -v`
Expected: the three new tests PASS immediately (check (c) shipped in Task 4's code). If any fails, fix `p3_property` -- do NOT touch the assertions.

- [ ] **Step 3: Commit**

```bash
git add tests/engine/test_p3.py
git commit -m "test(engine): P3 check (c) settled-state cases against CSDF fixtures"
```

---

### Task 6: build_meas_context -- deck-line parser with the worked example

**Files:**
- Modify: `core/verify_sidecar.py`
- Test: `tests/test_verify_sidecar.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_verify_sidecar.py`)

```python
from core.verify_sidecar import build_meas_context

# Substituted v1 deck shape -- the worked example from the spec
# (mpw/template__CP__rise__fall__1.sp with max_slew = 1n).
WORKED_DECK = [
    ".param max_slew = '1n'\n",
    ".param search_window = '1n'\n",
    ".param opt_init = '5 * search_window'\n",
    ".param constr_pin_offset = opt_init\n",
    ".param related_pin_t01 = '10 * max_slew'\n",
    ".param related_pin_t02 = '20 * max_slew'\n",
    ".param related_pin_t03 = '50 * max_slew'\n",
    ".param related_pin_t04 = '50 * max_slew + constr_pin_offset'\n",
    "XVCP CP 0 stdvs_mpw_rise_fall_rise_fall VDD='vdd_value' slew='rel_pin_slew'"
    " t01='related_pin_t01' t02='related_pin_t02' t03='related_pin_t03'"
    " t04='related_pin_t04'\n",
    "* Measurements\n",
    ".meas cp2q_del1 trig v(CP) val='vdd_value/2' cross=3 targ v(Q)"
    " val='vdd_value/2' cross=1 td='related_pin_t03'\n",
    ".tran 1p 50u sweep monte=1\n",
]


class TestBuildMeasContext:
    def test_worked_example(self):
        ctx = build_meas_context(WORKED_DECK, _arc_info())
        assert [(t, d) for _, t, d in ctx.rel_edges] == \
            [(10.0, 'rise'), (20.0, 'fall'), (50.0, 'rise'), (55.0, 'fall')]
        assert ctx.trig_cross == 3
        assert ctx.trig_td_ns == 0.0          # td is in the TARG clause
        assert ctx.capture_t_ns == 50.0       # 3rd crossing from t=0 = rise@t03
        assert ctx.capture_dir == 'rise'
        assert ctx.vdd == 0.45

    def test_td_moved_into_trig_clause_shifts_the_count(self):
        # Pins the normative convention: only a trig-clause td gates counting.
        lines = [l.replace(
            "cross=3 targ v(Q) val='vdd_value/2' cross=1 td='related_pin_t03'",
            "cross=3 td='related_pin_t03' targ v(Q) val='vdd_value/2' cross=1")
            for l in WORKED_DECK]
        ctx = build_meas_context(lines, _arc_info())
        assert ctx.trig_td_ns == 50.0
        # only 2 edges at/after 50ns -> no 3rd crossing -> unresolved
        assert ctx.capture_t_ns is None
        assert any('cross=3' in n for n in ctx.notes)

    def test_unresolved_param_is_stub_not_crash(self):
        lines = [l.replace("'50 * max_slew'", "'sin(x)'") for l in WORKED_DECK]
        ctx = build_meas_context(lines, _arc_info())
        assert ctx.capture_t_ns is None
        assert any('UNRESOLVED' in n for n in ctx.notes)

    def test_no_toggling_line_is_unresolved(self):
        lines = [l for l in WORKED_DECK if not l.startswith('XVCP')]
        ctx = build_meas_context(lines, _arc_info())
        assert ctx.capture_t_ns is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -k BuildMeasContext -v`
Expected: ImportError

- [ ] **Step 3: Implement** (append to `core/verify_sidecar.py`)

```python
# ---------------------------------------------------------------------------
# meas context from substituted deck lines (spec section 4.1)
# ---------------------------------------------------------------------------

_UNIT_NS = {'f': 1e-6, 'p': 1e-3, 'n': 1.0, 'u': 1e3, 'm': 1e6}
_PARAM_RE = re.compile(r"^\s*\.param\s+(\w+)\s*=\s*'?([^'\n]*?)'?\s*$")
_STDVS_RE = re.compile(r"^\s*XV\w*\s+(\S+)\s+0\s+(stdvs\w+)\s+(.*)$")
_TPAR_RE = re.compile(r"\bt(\d\d)\s*=\s*'([^']+)'")
_NUM_RE = re.compile(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?([fpnum]?)$")


def _resolve_ns(expr, params, depth=0):
    """Resolve a v1 template time expression to ns. Handles exactly the forms
    the production templates use: NUM[unit] | NAME | K * NAME | A + B.
    Returns None when the form is anything else (caller notes UNRESOLVED)."""
    if depth > 10 or expr is None:
        return None
    expr = expr.strip().strip("'")
    if '+' in expr:
        total = 0.0
        for part in expr.split('+'):
            v = _resolve_ns(part, params, depth + 1)
            if v is None:
                return None
            total += v
        return total
    if '*' in expr:
        left, _, right = expr.partition('*')
        try:
            k = float(left.strip())
        except ValueError:
            return None
        v = _resolve_ns(right, params, depth + 1)
        return None if v is None else k * v
    m = _NUM_RE.match(expr)
    if m:
        unit = m.group(1)
        return float(expr[:-1] if unit else expr) * _UNIT_NS.get(unit, 1.0)
    if expr in params:
        return _resolve_ns(params[expr], params, depth + 1)
    return None


def build_meas_context(deck_lines, arc_info):
    """Lift MeasContext from v1's substituted deck lines (spec 4.1).
    Never raises for unexpected template shapes: returns a context with
    capture_t_ns=None and a note (P3 then reports STUB naming the gap)."""
    lines = [l if isinstance(l, str) else str(l) for l in deck_lines]
    rel_pin = arc_info.get('REL_PIN', '')
    notes = []
    try:
        vdd = float(arc_info.get('VDD_VALUE') or 0.0)
    except ValueError:
        vdd = 0.0
        notes.append("UNRESOLVED: VDD_VALUE %r" % arc_info.get('VDD_VALUE'))

    params = {}
    for l in lines:
        m = _PARAM_RE.match(l)
        if m:
            params[m.group(1)] = m.group(2)

    def _unresolved(reason):
        notes.append(reason)
        return MeasContext(rel_edges=[], trig_cross=0, trig_td_ns=0.0,
                           capture_t_ns=None, capture_dir='', vdd=vdd,
                           notes=notes)

    # toggling-pin line: edge directions from the stdvs model-name suffix,
    # edge times from its tNN= params
    stdvs = None
    for l in lines:
        m = _STDVS_RE.match(l)
        if m and m.group(1) == rel_pin:
            stdvs = m
            break
    if stdvs is None:
        return _unresolved("UNRESOLVED: no stdvs toggling line for rel_pin "
                           "%r" % rel_pin)
    dirs = [t for t in stdvs.group(2).split('_') if t in ('rise', 'fall')]
    tpars = sorted(_TPAR_RE.findall(stdvs.group(3)))
    edges = []
    for (idx, pname), d in zip(tpars, dirs):
        t = _resolve_ns(pname, params)
        if t is None:
            return _unresolved("UNRESOLVED: .param %s = %r" %
                               (pname, params.get(pname)))
        edges.append(('t' + idx, t, d))
    edges.sort(key=lambda e: e[1])
    if not edges:
        return _unresolved("UNRESOLVED: stdvs line has no tNN= edge params")

    # primary measurement: first .meas whose trig probes v(rel_pin).
    # Clause attribution (normative): split at the 'targ' keyword; only a
    # trig-clause td gates the capture count.
    trig_cross, trig_td = None, 0.0
    pat = re.compile(r"trig\s+v\(%s\)" % re.escape(rel_pin), re.IGNORECASE)
    for l in lines:
        if not l.lstrip().startswith('.meas') or not pat.search(l):
            continue
        trig_part = re.split(r"\btarg\b", l, maxsplit=1)[0]
        mc = re.search(r"cross\s*=\s*(\d+)", trig_part)
        if not mc:
            continue
        trig_cross = int(mc.group(1))
        mtd = re.search(r"td\s*=\s*'?([^'\s]+)'?", trig_part)
        if mtd:
            td = _resolve_ns(mtd.group(1), params)
            if td is None:
                return _unresolved("UNRESOLVED: trig td %r" % mtd.group(1))
            trig_td = td
        break
    if trig_cross is None:
        return _unresolved("UNRESOLVED: no .meas trig on v(%s) with cross="
                           % rel_pin)

    after = [e for e in edges if e[1] >= trig_td]
    if len(after) < trig_cross:
        notes.append("trig cross=%d after td=%gns: only %d edge(s) in the "
                     "schedule" % (trig_cross, trig_td, len(after)))
        return MeasContext(rel_edges=edges, trig_cross=trig_cross,
                           trig_td_ns=trig_td, capture_t_ns=None,
                           capture_dir='', vdd=vdd, notes=notes)
    _, cap_t, cap_d = after[trig_cross - 1]
    return MeasContext(rel_edges=edges, trig_cross=trig_cross,
                       trig_td_ns=trig_td, capture_t_ns=cap_t,
                       capture_dir=cap_d, vdd=vdd, notes=notes)
```

Also add to the import block at the top of `core/verify_sidecar.py`:

```python
from engine.stages.stage5_verify import MeasContext, p3_property
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add core/verify_sidecar.py tests/test_verify_sidecar.py
git commit -m "feat(verify): MeasContext extraction from deck lines (worked example + td attribution)"
```

---

### Task 7: write_sidecar -- orchestration, ERROR path, JSON schema

**Files:**
- Modify: `core/verify_sidecar.py`
- Test: `tests/test_verify_sidecar.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_verify_sidecar.py`)

```python
import core.verify_sidecar as vs

SDFX = os.path.join(REPO, 'engine', 'fixtures', 'SDFX_LPE_PLACEHOLDER.subckt')


def _sdfx_arc_info(**over):
    info = _arc_info(CELL_NAME='SDFX_LPE_PLACEHOLDER', NETLIST_PATH=SDFX)
    info.update(over)
    return info


class TestWriteSidecar:
    def test_ok_sidecar_on_engine_fixture(self, tmp_path):
        path = vs.write_sidecar(str(tmp_path), _sdfx_arc_info(),
                                {'arc_id': 'a1', 'corner': 'c1'}, WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['schema_version'] == 1
        assert data['status'] == 'OK'
        assert data['arc']['cell'] == 'SDFX_LPE_PLACEHOLDER'
        assert data['verdict']['p1']['status'] == 'PASS'
        assert data['verdict']['p3']['status'] in ('STUB', 'PASS', 'FAIL')
        assert data['engine']['version'] == '2.0-2b'
        assert data['biases']['match'].split()[0] in (
            'MATCH', 'MISMATCH:', 'NON_CRITICAL', 'N/A')
        assert 'derived independently' not in data['arc_check']  # when given
        assert data['timestamps']['started'] <= data['timestamps']['finished']

    def test_missing_netlist_is_error_sidecar(self, tmp_path):
        path = vs.write_sidecar(str(tmp_path),
                                _sdfx_arc_info(NETLIST_PATH='/no/such.spi'),
                                None, WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['status'] == 'ERROR'
        assert 'no netlist text available' in data['error']['summary']
        assert 'verdict' not in data

    def test_engine_exception_yields_error_sidecar(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('boom')
        monkeypatch.setattr(vs, 'run_pipeline_src', boom)
        path = vs.write_sidecar(str(tmp_path), _sdfx_arc_info(), None,
                                WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['status'] == 'ERROR'
        assert data['error']['type'] == 'RuntimeError'
        assert any('boom' in t for t in data['error']['traceback_tail'])

    def test_stripped_meas_marker_is_loud(self, tmp_path):
        lines = [l for l in WORKED_DECK if '.meas' not in l
                 and 'Measurements' not in l]
        path = vs.write_sidecar(str(tmp_path), _sdfx_arc_info(), None, lines)
        data = json.loads(open(path).read())
        assert data['status'] == 'OK'
        assert any('meas extraction failed' in n for n in data['notes'])
        assert data['verdict']['p3']['status'] == 'STUB'
        assert any('no measurement block found' in d
                   for d in data['verdict']['p3']['detail'])

    def test_no_when_reports_derived_independently(self, tmp_path):
        path = vs.write_sidecar(
            str(tmp_path),
            _sdfx_arc_info(WHEN='NO_CONDITION', LIT_WHEN='NO_CONDITION'),
            None, WORKED_DECK)
        data = json.loads(open(path).read())
        assert data['status'] == 'OK'
        assert 'derived independently' in data['arc_check']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -k WriteSidecar -v`
Expected: AttributeError (`write_sidecar` not defined)

- [ ] **Step 3: Implement** (append to `core/verify_sidecar.py`)

```python
# ---------------------------------------------------------------------------
# sidecar writer (spec section 5)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
SIDECAR_NAME = 'verify.json'


def engine_version_info():
    import engine
    commit = None
    try:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(engine.__file__)))
        out = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                             cwd=repo, capture_output=True, text=True,
                             timeout=1)
        if out.returncode == 0:
            commit = out.stdout.strip()
    except Exception:
        pass        # air-gapped server may have no git; commit stays None
    return {'version': getattr(engine, '__version__', 'unknown'),
            'commit': commit}


def _prop_dict(p):
    return {'status': p.status.value, 'detail': list(p.detail)}


def write_sidecar(deck_dir, arc_info, job, deck_lines):
    """Run the engine on one v1-resolved arc and write {deck_dir}/verify.json.
    NEVER raises for engine-side problems: any failure becomes a status=ERROR
    sidecar. (A failure writing the file itself propagates; the batch caller
    catches it and warns -- spec section 5.)"""
    started = datetime.now(timezone.utc).isoformat()
    record = build_record(arc_info, job)
    payload = {
        'schema_version': SCHEMA_VERSION,
        'arc': {
            'arc_id': record['arc_id'], 'cell': record['cell'],
            'arc_type': record['arc_type'], 'corner': record['corner'],
            'rel_pin': record['rel_pin'], 'rel_dir': record['rel_dir'],
            'constr_pin': record['constr_pin'],
            'constr_dir': record['constr_dir'],
            'when': record['when'], 'when_literal': record['when_literal'],
            'vector': record['vector'],
        },
        'engine': engine_version_info(),
        'deck': 'nominal_sim.sp',
    }
    notes = []
    try:
        npath = arc_info.get('NETLIST_PATH') or ''
        if not npath or not os.path.isfile(npath):
            raise VerifyInputError(
                'no netlist text available (NETLIST_PATH=%r)' % npath)
        with open(npath, 'r') as fh:
            src = fh.read()

        meas, mnote = extract_meas_block(deck_lines)
        if mnote:
            notes.append(mnote)
        record['measurement'] = meas
        inc = arc_info.get('INCLUDE_FILE') or ''
        model = ".inc '%s'" % inc if inc else ''

        result = run_pipeline_src(record, src, meas, model, 'v1-audit')

        if mnote:
            ctx = MeasContext(rel_edges=[], trig_cross=0, trig_td_ns=0.0,
                              capture_t_ns=None, capture_dir='', vdd=0.0,
                              notes=['no measurement block found in v1 deck '
                                     "(marker '* Measurements' absent and no "
                                     '.meas lines)'])
        else:
            ctx = build_meas_context(deck_lines, arc_info)
        result.verdict.p3 = p3_property(ctx, result.init, result.arc,
                                        sim_data=None)

        golden = derive_golden_biases(arc_info)
        derived = {p: d.value for p, d in result.sens.side_biases.items()}
        v = result.verdict
        payload.update({
            'status': 'OK',
            'verdict': {'overall': v.overall.value,
                        'p1': _prop_dict(v.p1), 'p2': _prop_dict(v.p2),
                        'p3': _prop_dict(v.p3)},
            'biases': {
                'derived': {p: {'value': d.value, 'reason': d.reason}
                            for p, d in result.sens.side_biases.items()},
                'golden': golden,
                'match': classify_bias_match(derived, result.sens.set_pins,
                                             result.sens.masked_pins, golden),
            },
            'arc_check': result.sens.arc_check,
            'stage_log': list(result.stage_log),
        })
    except Exception as e:
        frames = traceback.extract_tb(sys.exc_info()[2])
        last = frames[-1] if frames else None
        summary = ('%s:%s in %s: %s' % (last.filename, last.lineno,
                                        last.name, e)
                   if last else str(e))
        payload.update({
            'status': 'ERROR',
            'error': {'type': type(e).__name__, 'summary': summary,
                      'traceback_tail':
                          traceback.format_exc().splitlines()[-5:]},
        })
    payload['notes'] = notes
    payload['timestamps'] = {'started': started,
                             'finished': datetime.now(timezone.utc).isoformat()}
    path = os.path.join(deck_dir, SIDECAR_NAME)
    with open(path, 'w') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write('\n')
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -v`
Expected: all pass. (The OK-path test runs the real engine on the SDFX fixture; P1
must be PASS there, proving the record mapping end-to-end.)

- [ ] **Step 5: Commit**

```bash
git add core/verify_sidecar.py tests/test_verify_sidecar.py
git commit -m "feat(verify): sidecar writer -- OK/ERROR schema, P3 wiring, never breaks the run"
```

---

### Task 8: --verify flag through deckgen.py and core/batch.py + byte-identity regression

**Files:**
- Modify: `deckgen.py`
- Modify: `core/batch.py`
- Test: `tests/test_verify_sidecar.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_verify_sidecar.py`)

```python
import hashlib

from core.batch import run_batch

FIXTURE_COLLATERAL = os.path.join(REPO, 'tests', 'fixtures', 'collateral')
ARC_IDS = ['hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1']
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


def _tree_hashes(root):
    out = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, root)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return out


def _run(outdir, verify):
    return run_batch(arc_ids=ARC_IDS, corner_names=[CORNER], files={},
                     output_dir=str(outdir), nominal_only=True,
                     node='N2P_v1.0', lib_type='test_lib',
                     collateral_root=FIXTURE_COLLATERAL, verify=verify)


class TestVerifyBatch:
    def test_byte_identical_whole_tree(self, tmp_path):
        # Spec 8a: every common file identical; only verify.json may be added.
        manifest = os.path.join(FIXTURE_COLLATERAL, 'N2P_v1.0', 'test_lib',
                                'manifest.json')
        before = open(manifest, 'rb').read() if os.path.exists(manifest) else None
        _run(tmp_path / 'off', verify=False)
        _run(tmp_path / 'on', verify=True)
        off = _tree_hashes(tmp_path / 'off')
        on = _tree_hashes(tmp_path / 'on')
        on_base = {k: v for k, v in on.items()
                   if os.path.basename(k) != 'verify.json'}
        assert on_base == off
        assert any(os.path.basename(k) == 'verify.json' for k in on)
        if before is not None:
            assert open(manifest, 'rb').read() == before

    def test_sidecar_well_formed_per_job(self, tmp_path):
        jobs, results, errors = _run(tmp_path, verify=True)
        assert not errors
        for r in results:
            if not r['success']:
                continue
            assert r.get('sidecar')
            data = json.loads(open(r['sidecar']).read())
            assert data['schema_version'] == 1
            assert data['status'] in ('OK', 'ERROR')
            assert data['arc']['cell'] == 'DFFQ1'

    def test_engine_crash_does_not_abort_batch(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('boom')
        monkeypatch.setattr(vs, 'run_pipeline_src', boom)
        jobs, results, errors = _run(tmp_path, verify=True)
        ok = [r for r in results if r['success']]
        assert ok                                # decks still written
        for r in ok:
            data = json.loads(open(r['sidecar']).read())
            assert data['status'] == 'ERROR'

    def test_cli_flag_exists(self):
        import deckgen
        import sys as _sys
        argv = _sys.argv
        _sys.argv = ['deckgen.py', '--verify', '--cell', 'X', '--arc_type',
                     'hold', '--rel_pin', 'CP', '--rel_dir', 'rise']
        try:
            args = deckgen.parse_args()
            assert args.verify is True
        finally:
            _sys.argv = argv
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -k "VerifyBatch" -v`
Expected: TypeError (`run_batch` has no `verify` kwarg) / AttributeError (no `args.verify`)

- [ ] **Step 3: Thread `verify` through `core/batch.py`**

In `execute_jobs`, change the signature and add the sidecar call after the MC-deck
write inside `_run_one` (the deck files are already on disk at that point):

```python
def execute_jobs(jobs, output_dir, nominal_only=False, num_samples=5000,
                 files=None, verify=False):
```

Inside `_run_one`, replace the final success `return` with:

```python
            sidecar = None
            if verify:
                # Audit sidecar -- observer only. Its own failure must never
                # fail the job (the deck is already written and valid).
                try:
                    from core.verify_sidecar import write_sidecar
                    sidecar = write_sidecar(deck_dir, arc_info, job,
                                            nominal_lines)
                except Exception as ve:
                    import sys
                    print("  WARN: verify sidecar failed for job "
                          f"{job['id']}: {ve}", file=sys.stderr)

            return {'id': job['id'], 'success': True,
                    'nominal': nominal_path, 'mc': mc_path, 'error': None,
                    'sidecar': sidecar}
```

In `run_batch`, change the signature and pass-through:

```python
def run_batch(arc_ids, corner_names, files, overrides=None, output_dir='.',
              selected_ids=None, nominal_only=False, num_samples=5000,
              node=None, lib_type=None, collateral_root='collateral',
              verify=False):
```

```python
    results = execute_jobs(jobs_to_run, output_dir,
                           nominal_only=nominal_only,
                           num_samples=num_samples,
                           files=files, verify=verify)
```

- [ ] **Step 4: Add the flag to `deckgen.py`**

In `parse_args()`, after the `--rescan` argument:

```python
    p.add_argument('--verify', action='store_true',
                   help='also run the v2 engine per arc and write a verdict '
                        'sidecar JSON next to each deck (audit only; never '
                        'changes deck output)')
```

In `_run_batch`, pass it through and report it:

```python
    jobs, results, errors = run_batch(
        arc_ids=arc_ids,
        corner_names=corner_names,
        files=files,
        overrides=overrides,
        output_dir=args.output,
        nominal_only=args.nominal_only,
        num_samples=args.num_samples,
        node=args.node,
        lib_type=args.lib_type,
        verify=args.verify,
    )
```

and inside the per-result loop, after the success `print`:

```python
        if r['success'] and r.get('sidecar'):
            print(f"        verify: {r['sidecar']}")
```

In `_run_single`, after the decks are written (both branches set a deck path;
compute `deck_dir` from it) and before the final summary print:

```python
    if args.verify:
        # Lazy import: with --verify off, no engine code is ever loaded.
        from core.verify_sidecar import write_sidecar
        deck_dir = os.path.dirname(out_path if args.nominal_only
                                   else nominal_path)
        try:
            sc = write_sidecar(deck_dir, arc_info,
                               {'when': args.when,
                                'probe_pin': args.probe_pin or ''},
                               nominal_lines)
            print(f"Verify sidecar: {sc}")
        except Exception as ve:
            print(f"WARN: verify sidecar failed: {ve}", file=sys.stderr)
```

(Note: in the `nominal_only` branch the variable is `out_path`; in the other it is
`nominal_path` -- both already exist in `_run_single`.)

- [ ] **Step 5: Run the new tests, then the full suite**

Run: `python3.12 -m pytest tests/test_verify_sidecar.py -v && python3.12 -m pytest tests/ -q`
Expected: all pass (376 pre-existing + all new)

- [ ] **Step 6: ASCII scan + commit**

```bash
grep -rPn '[\x80-\xff]' deckgen.py core/batch.py core/verify_sidecar.py tests/test_verify_sidecar.py
git add deckgen.py core/batch.py tests/test_verify_sidecar.py
git commit -m "feat(verify): --verify flag through deckgen/batch + whole-tree byte-identity regression"
```

---

### Task 9: P3 in the engine --sim path (engine/run.py + p2_deck edge export)

**Files:**
- Modify: `engine/p2_deck.py` (export the PWL edge schedule in the wave info dict)
- Modify: `engine/run.py`
- Test: `tests/engine/test_p3.py`

- [ ] **Step 1: Write the failing test** (append to `tests/engine/test_p3.py`)

```python
def test_p2_deck_info_exports_rel_edges():
    import os
    from engine.config import ENGINE_DIR
    from engine.p2_deck import build as build_p2
    from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
    from engine.stages import stage3_initialize
    with open(os.path.join(ENGINE_DIR, 'fixtures',
                           'SDFX_LPE_PLACEHOLDER.subckt'), 'r',
              encoding='ascii') as fh:
        g = stage0_parse.parse(fh.read(), 'SDFX_LPE_PLACEHOLDER')
    ccc = stage1_ccc.decompose(g)
    arc = _arc()
    arc.cell = 'SDFX_LPE_PLACEHOLDER'
    sens = stage2_sensitize.derive(g, arc, ccc)
    init = stage3_initialize.derive(g, ccc, arc, sens)
    _, info = build_p2(arc, sens, init, init.probes, wave=True)
    edges = info['rel_edges_ns']
    assert [d for _, _, d in edges] == ['rise', 'fall', 'rise']
    assert edges[-1][1] == info['t_cap_edge'] * 1e9
    # 2 edges before the capture edge -> exactly 1 pre-cycle, matching S3
    before = [e for e in edges if e[1] < edges[-1][1]]
    assert len(before) // 2 == init.precycle_count.value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/engine/test_p3.py::test_p2_deck_info_exports_rel_edges -v`
Expected: KeyError `'rel_edges_ns'`

- [ ] **Step 3: Export the edge schedule from `engine/p2_deck.py`**

In `build()`, change the final `info` dict to:

```python
    info = {"meas_map": meas_map, "t_settle": t_settle * 1e-9,
            "t_cap_edge": t_cap_edge * 1e-9,
            "rel_edges_ns": [("load_r", t_load_r, "rise"),
                             ("load_f", t_load_f, "fall"),
                             ("cap", t_cap_edge, "rise")]}
```

- [ ] **Step 4: Wire P3 into the `--sim` path in `engine/run.py`**

Replace the existing `if args.sim or args.mt0:` block body with (the `run_p2`/`p2_property` lines are unchanged; the P3 part is appended):

```python
    if args.sim or args.mt0:
        from engine.sim import run_p2
        from engine.stages.stage5_verify import (MeasContext, p2_property,
                                                 p3_property)
        p2res = run_p2(result.arc, result.ccc, result.sens, result.init,
                       args.simdir, hspice_cmd=args.hspice,
                       mt0_path=args.mt0, mt0_inv_path=args.mt0_inv)
        result.verdict.p2 = p2_property(p2res)
        result.stage_log[-1] = (f"S5 verify   : P2 {'PASS' if p2res.passed else 'FAIL/n-a'} "
                                f"({'ran' if p2res.ran else p2res.note})")

        # P3: meas context from the P2 prototype deck's own timeline; check (c)
        # evaluates the wave run's CSDF when it exists, else P3 stays STUB.
        from engine import golden_env as G
        from engine.p2_deck import build as build_p2
        _, winfo = build_p2(result.arc, result.sens, result.init,
                            result.init.probes, wave=True)
        ctx = MeasContext(
            rel_edges=winfo["rel_edges_ns"], trig_cross=3, trig_td_ns=0.0,
            capture_t_ns=winfo["t_cap_edge"] * 1e9, capture_dir="rise",
            vdd=float(G.VDD_VALUE),
            notes=["context from P2 prototype deck timeline"])
        sim_data = None
        tr0 = args.tr0 or os.path.join(args.simdir, "p2_wave.tr0")
        if os.path.isfile(tr0):
            from engine.wave import parse_csdf
            with open(tr0, "r", encoding="ascii", errors="replace") as fh:
                sim_data = parse_csdf(fh.read())
        result.verdict.p3 = p3_property(ctx, result.init, result.arc, sim_data)
```

Note `p2_property` moves from a local import inside the block to this import line --
it was already imported there before; keep a single import statement as shown.

- [ ] **Step 5: Run the engine tests + full suite**

Run: `python3.12 -m pytest tests/engine/ -q && python3.12 -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 6: Smoke the CLI paths by hand**

```bash
python3.12 -m engine.run --netlist engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt --when notSE_SI | head -8
python3.12 -m engine.run --netlist engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt --when notSE_SI --mt0 /dev/null --simdir /tmp/dg_p3 2>&1 | grep -A4 "P3"
```
Expected: first command unchanged from before this task; second shows P3 with the
prototype-timeline detail lines (STUB without a tr0; the /dev/null mt0 makes P2
report not-ran, which is fine for the smoke).

- [ ] **Step 7: ASCII scan + commit**

```bash
grep -rPn '[\x80-\xff]' engine/run.py engine/p2_deck.py tests/engine/test_p3.py
git add engine/run.py engine/p2_deck.py tests/engine/test_p3.py
git commit -m "feat(engine): wire P3 into the --sim path via the P2 deck timeline"
```

---

### Task 10: final verification sweep

**Files:** none new

- [ ] **Step 1: Full suite under python3.12**

Run: `python3.12 -m pytest tests/ -q`
Expected: all pass, zero skips introduced by this work

- [ ] **Step 2: Repo-wide non-ASCII scan (CLAUDE.md)**

Run: `grep -rPn '[\x80-\xff]' . --include='*.py' --include='*.yaml' --include='*.sp' --include='*.md' | grep -v '^Binary'`
Expected: empty (pre-existing exceptions, if any, must predate this work -- check with `git stash` if unsure)

- [ ] **Step 3: End-to-end CLI smoke on the collateral fixture**

```bash
python3.12 - <<'EOF'
import json, os, tempfile
from core.batch import run_batch
out = tempfile.mkdtemp()
jobs, results, errors = run_batch(
    arc_ids=['hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1'],
    corner_names=['ssgnp_0p450v_m40c_cworst_CCworst_T'], files={},
    output_dir=out, nominal_only=True, node='N2P_v1.0', lib_type='test_lib',
    collateral_root='tests/fixtures/collateral', verify=True)
for r in results:
    print(r['success'], r.get('sidecar'))
    if r.get('sidecar'):
        d = json.load(open(r['sidecar']))
        print(' ', d['status'], d.get('verdict', {}).get('overall'))
EOF
```
Expected: each successful job prints a sidecar path; status is OK or ERROR (the
fixture netlist has no transistor body, so ERROR/FAIL verdicts are legitimate --
well-formedness is the requirement).

- [ ] **Step 4: Verify acceptance criteria against the spec** (sections 8-9 of the
spec): byte-identity test green, sidecars well-formed, ERROR path covered, P3 unit
tests green, `--sim` path wired. If any criterion lacks a green test, STOP and add
it before closing.

- [ ] **Step 5: Commit anything outstanding; do NOT push** (signing server may need
the user -- per CLAUDE.md, never push unsigned without checking with Yuxuan).

---

## Self-Review Notes (already applied)

- Spec coverage: 3.1 -> Task 1; 3.3 -> Task 2; 5 (biases/CSV semantics) -> Task 3;
  4.1/4.2 static -> Task 4; 4.2(c) -> Task 5; 4.1 extraction + worked example +
  td attribution -> Task 6; 5 (schema/ERROR) -> Task 7; 2/6/8a-c (flag, batch,
  byte-identity, crash path, loud meas, NO_CONDITION, three-state) -> Tasks 7-8;
  4.4 (--sim path) -> Task 9. CSV aggregator: intentionally NOT implemented
  (separate task per spec; columns are fixed in the spec).
- Type consistency: `MeasContext` fields used by `p3_property` (Task 4) match the
  constructor calls in Tasks 6, 7, and 9; `write_sidecar(deck_dir, arc_info, job,
  deck_lines)` is called with the same shape from batch (Task 8) and single-arc
  (Task 8) paths; `run_batch(..., verify=)` matches `execute_jobs(..., verify=)`.
- Known fixture caveat (from the spec): `tests/fixtures/collateral/.../DFFQ1_c.spi`
  has no transistor body, so engine verdicts there may be ERROR -- tests assert
  well-formedness and byte-identity, not PASS. The engine-green path is covered by
  Task 7's SDFX fixture test.
