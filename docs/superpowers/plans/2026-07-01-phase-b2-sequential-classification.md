# Phase B2 -- Structural Sequential Classification + Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify a sequential cell's structural decomposition as `latch` / `ff_chain` / `multibit` / `recognized_unsupported` and derive per-bit master/slave depth, so B3 can emit the correct precycle recipe (replacing stage3's hardcoded `precycle_count=1`).

**Architecture:** Two new stdlib-only modules under `engine/stages/`. `storage_view.py` lifts the influence-graph + cross-coupled-SCC + cone/distance extraction (currently inline in `stage1_ccc.decompose` and re-implemented in `tools/seq_probe.py`) into one reusable `build_storage_view(graph) -> StorageView`. `stage1b_classify.py` consumes the view: `peel_bits` recovers true output bits via nested-cone peeling (defeating the scan-chain false-merge), pairs master/slave per bit, and emits one `SequentialClass`. `stage1_ccc.py` is left unchanged (its green tests are the safety net). `tools/seq_probe.py` is migrated onto the two new functions.

**Tech Stack:** Python 3.12, stdlib only, `dataclasses`. Consumes `engine.types.DeviceGraph` (stage0 output) and reuses `engine.stages.stage1_ccc._sccs`, `_min_dist`, `RAILS`. Name cross-check via `core.principle_engine.classifier.classify_cell`.

## Global Constraints

- **ASCII-only** for all `.py` files. Verify empty output: `grep -rPn '[\x80-\xff]' engine/stages/storage_view.py engine/stages/stage1b_classify.py tools/seq_probe.py`
- **stdlib-only, simulator-free.** No new dependencies; no HSPICE invocation.
- **Never weaken a test assertion to make a test pass.** If implementation disagrees with an assertion, fix the implementation. Changing an expected value/exception/attribute requires Yuxuan's explicit approval (CLAUDE.md).
- **`classify` never raises.** Any internal failure returns `SequentialClass(verdict="recognized_unsupported", ..., reason="internal: <e>")`. Never fail silently; never drop a core without surfacing it in `reason`/`paired_cleanly`/`divergence`.
- **`stage1_ccc.py` is NOT modified.** The ~15-line extraction duplication into `storage_view.py` is intentional and noted for later unification.
- **Tests run with `python3.12 -m pytest`.** Test files live under `tests/engine/`.
- **Design of record:** `docs/superpowers/specs/2026-07-01-phase-b2-sequential-classification-design.md`. All type names/signatures below match Section 3 of that spec.

---

## File Structure

- Create `engine/stages/storage_view.py` -- `StorageCore`, `StorageView`, `build_storage_view`. Extraction only; no classification.
- Create `engine/stages/stage1b_classify.py` -- `Stage`, `BitClass`, `SequentialClass`, `peel_bits`, `_pair`, `_name_crosscheck`, `classify_cores`, `classify`. Pure logic on top of the view + one graph entry point.
- Create `tests/engine/test_storage_view.py` -- extraction tests (synth latch fixture + real SDFX fixture).
- Create `tests/engine/test_stage1b_classify.py` -- pure-logic tests on hand-built `StorageCore` lists (incl. transcribed MB8 vector) + one end-to-end via `classify(graph)`.
- Create `tests/fixtures/audit_lib/netlist/SYNTH_LATCH.spi` -- minimal cross-coupled bistable fixture.
- Modify `tools/seq_probe.py` -- replace its inline core extraction + heuristic with `build_storage_view` + `classify`.

---

### Task 1: Storage view extraction (`build_storage_view`)

**Files:**
- Create: `engine/stages/storage_view.py`
- Create: `tests/fixtures/audit_lib/netlist/SYNTH_LATCH.spi`
- Test: `tests/engine/test_storage_view.py`

**Interfaces:**
- Consumes: `engine.types.DeviceGraph` (fields `.ports: list[str]`, `.devices: list[Device]`, `.cell: str`; each `Device.terminals` is `{"d","g","s","b"} -> logical net`). Reuses `engine.stages.stage1_ccc._sccs(adj)`, `_min_dist(adj, sources, targets)` (returns a large sentinel when unreachable), `RAILS`.
- Produces: `StorageCore(nets: frozenset, dist_to_out: int, cone: frozenset)`; `StorageView(cores: tuple, outputs: tuple, notes: tuple)`; `build_storage_view(graph) -> StorageView` (cores sorted by `(dist_to_out, sorted(nets))`).

- [ ] **Step 1: Write the synth-latch fixture**

Create `tests/fixtures/audit_lib/netlist/SYNTH_LATCH.spi` (device line syntax `Xname drain gate source bulk model`, matching the existing `AOI22.spi` fixture in the same directory):

```spice
* SYNTH_LATCH.spi -- minimal cross-coupled bistable + output buffer.
* Structural fixture for build_storage_view: 1 storage core {a,b}, cone {Q}.
* D and CP are declared inputs; the loop is self-holding (no clock modeled).
.subckt SYNTH_LATCH D CP Q VDD VSS
* cross-coupled inverter pair -> storage core over nets a, b
XP1 b a VDD VDD pch_svt_mac
XN1 b a VSS VSS nch_svt_mac
XP2 a b VDD VDD pch_svt_mac
XN2 a b VSS VSS nch_svt_mac
* output buffer a -> Q (gives the core a distance-1 cone to Q)
XPO Q a VDD VDD pch_svt_mac
XNO Q a VSS VSS nch_svt_mac
.ends
```

- [ ] **Step 2: Write the failing test**

Create `tests/engine/test_storage_view.py`:

```python
import os
from engine.stages import stage0_parse
from engine.stages.storage_view import build_storage_view

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SYNTH = os.path.join(_REPO, "tests/fixtures/audit_lib/netlist/SYNTH_LATCH.spi")
_SDFX = os.path.join(_REPO, "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt")


def test_synth_latch_one_core_cone_q():
    g = stage0_parse.parse(open(_SYNTH).read(), "SYNTH_LATCH")
    view = build_storage_view(g)
    assert view.outputs == ("Q",)
    assert len(view.cores) == 1
    core = view.cores[0]
    assert len(core.nets) == 2                 # cross-coupled pair
    assert core.cone == frozenset({"Q"})
    assert core.dist_to_out == 1


def test_sdfx_two_cores_distinct_distance():
    g = stage0_parse.parse(open(_SDFX).read(), "SDFX_LPE_PLACEHOLDER")
    view = build_storage_view(g)
    assert view.outputs == ("Q",)
    assert len(view.cores) == 2
    # cores sorted by dist_to_out ascending: slave (nearer) then master (farther)
    assert view.cores[0].dist_to_out == 1
    assert view.cores[1].dist_to_out == 2
    assert all(c.cone == frozenset({"Q"}) for c in view.cores)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3.12 -m pytest tests/engine/test_storage_view.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'engine.stages.storage_view'`

- [ ] **Step 4: Write the implementation**

Create `engine/stages/storage_view.py`:

```python
"""storage_view.py -- shared structural storage-core extraction for B2.

Lifts the influence-graph + cross-coupled-SCC + per-core cone/distance logic
(currently inline in stage1_ccc.decompose and re-implemented in
tools/seq_probe.py) into ONE reusable function. Consumes a DeviceGraph
(stage0 output); returns a StorageView. stdlib only, ASCII only,
simulator-free. stage1_ccc.py is intentionally left unchanged -- this ~15-line
duplication is noted for a later unification.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.types import DeviceGraph
from engine.stages.stage1_ccc import _sccs, _min_dist, RAILS


@dataclass(frozen=True)
class StorageCore:
    nets: frozenset      # cross-coupled gate-controlling nets (the SCC core)
    dist_to_out: int     # min BFS influence-hops to any output port
    cone: frozenset      # output ports forward-reachable in the influence graph


@dataclass(frozen=True)
class StorageView:
    cores: tuple         # StorageCore list, sorted by (dist_to_out, sorted nets)
    outputs: tuple       # output ports (driven, non-rail), sorted
    notes: tuple         # provenance strings


def _cone(influence, core, outputs):
    """Output ports forward-reachable from a core in the influence graph."""
    seen = set(core)
    stack = list(core)
    hit = set()
    while stack:
        n = stack.pop()
        if n in outputs:
            hit.add(n)
        for w in influence.get(n, ()):
            if w not in seen:
                seen.add(w)
                stack.append(w)
    return frozenset(hit)


def build_storage_view(graph: DeviceGraph) -> StorageView:
    devs = graph.devices
    driven = {d.terminals["d"] for d in devs}
    input_ports = {p for p in graph.ports if p not in RAILS and p not in driven}
    output_ports = {p for p in graph.ports if p in driven and p not in RAILS}
    boundaries = RAILS | input_ports

    # influence graph: gate->drain and source->drain over non-rail nets
    # (mirrors stage1_ccc.decompose exactly).
    influence = {}
    for d in devs:
        dd, g, s = d.terminals["d"], d.terminals["g"], d.terminals["s"]
        for src in (g, s):
            if src not in RAILS and dd not in RAILS:
                influence.setdefault(src, set()).add(dd)

    internal_adj = {u: {w for w in vs if w not in boundaries}
                    for u, vs in influence.items() if u not in boundaries}
    gate_nets = {d.terminals["g"] for d in devs if d.terminals["g"] not in RAILS}

    cores = []
    for scc in _sccs(internal_adj):
        if len(scc) < 2:
            continue
        core = frozenset(n for n in scc if n in gate_nets)
        if len(core) >= 2:                      # cross-couple has >= 2 controllers
            dist = _min_dist(influence, set(core), output_ports)
            cone = _cone(influence, core, output_ports)
            cores.append(StorageCore(nets=core, dist_to_out=dist, cone=cone))

    cores.sort(key=lambda c: (c.dist_to_out, sorted(c.nets)))
    notes = (
        "storage_view: %d cross-coupled core(s) over influence graph" % len(cores),
        "outputs=%s" % sorted(output_ports),
    )
    return StorageView(cores=tuple(cores), outputs=tuple(sorted(output_ports)),
                       notes=notes)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3.12 -m pytest tests/engine/test_storage_view.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: ASCII guard**

Run: `grep -rPn '[\x80-\xff]' engine/stages/storage_view.py tests/engine/test_storage_view.py tests/fixtures/audit_lib/netlist/SYNTH_LATCH.spi`
Expected: no output (exit 1).

- [ ] **Step 7: Commit**

```bash
git add engine/stages/storage_view.py tests/engine/test_storage_view.py tests/fixtures/audit_lib/netlist/SYNTH_LATCH.spi
git commit -m "feat(b2): build_storage_view -- shared storage-core extraction"
```

---

### Task 2: Classification types + nested-cone peeling (`peel_bits`)

**Files:**
- Create: `engine/stages/stage1b_classify.py` (types + `peel_bits` only this task)
- Test: `tests/engine/test_stage1b_classify.py`

**Interfaces:**
- Consumes: `StorageCore` from Task 1 (`nets`, `dist_to_out`, `cone`).
- Produces: `Stage(nets, role, dist_to_out)`; `BitClass(outputs, stages, latch_stages, ff_depth, paired_cleanly)`; `SequentialClass(verdict, bits, name_hint, divergence, reason)`; `peel_bits(cores) -> (bits, dangling)` where `bits` is a list of `{"cores": set[int], "outputs": list[str]}` and `dangling` is a `set[int]` of core indices with empty cone.

- [ ] **Step 1: Write the failing test**

Create `tests/engine/test_stage1b_classify.py`:

```python
from engine.stages.storage_view import StorageCore
from engine.stages.stage1b_classify import peel_bits


def _core(dist, cone):
    # nets are irrelevant to peel_bits; distinct placeholders keep them unequal.
    return StorageCore(nets=frozenset({"n%d_a" % dist, "n%d_b" % dist}),
                       dist_to_out=dist, cone=frozenset(cone))


def _mb8_cores():
    # Transcribed from the real MB8 report: 8 slaves (dist 1) + 8 masters (dist 4),
    # cones nest because the scan chain links bit k into every later bit's cone.
    def qs(k):
        return frozenset("Q%d" % i for i in range(k, 9))
    cores = []
    for k in range(1, 9):                       # slaves, dist 1
        cores.append(StorageCore(frozenset({"sl%d_a" % k, "sl%d_b" % k}), 1, qs(k)))
    for k in range(1, 9):                       # masters, dist 4
        cores.append(StorageCore(frozenset({"ml%d_a" % k, "ml%d_b" % k}), 4, qs(k)))
    return cores


def test_peel_single_bit_two_cores():
    cores = [_core(1, {"Q"}), _core(2, {"Q"})]
    bits, dangling = peel_bits(cores)
    assert len(bits) == 1
    assert bits[0]["cores"] == {0, 1}
    assert bits[0]["outputs"] == ["Q"]
    assert dangling == set()


def test_peel_mb8_recovers_eight_bits():
    cores = _mb8_cores()
    bits, dangling = peel_bits(cores)
    assert len(bits) == 8
    assert dangling == set()
    # smallest cone first: bit for Q8 = {slave8(idx7), master8(idx15)}
    by_output = {b["outputs"][0]: b["cores"] for b in bits}
    assert by_output["Q8"] == {7, 15}
    assert by_output["Q1"] == {0, 8}
    # each bit owns exactly its slave+master pair
    assert all(len(v) == 2 for v in by_output.values())


def test_peel_dangling_core_has_empty_cone():
    cores = [_core(1, {"Q"}), _core(2, set())]   # second core reaches no output
    bits, dangling = peel_bits(cores)
    assert dangling == {1}
    assert len(bits) == 1
    assert bits[0]["cores"] == {0}


def test_peel_complementary_output_joins_same_bit():
    # Q and QN share the same reacher set -> QN attaches to the existing bit.
    cores = [_core(1, {"Q", "QN"}), _core(2, {"Q", "QN"})]
    bits, dangling = peel_bits(cores)
    assert len(bits) == 1
    assert sorted(bits[0]["outputs"]) == ["Q", "QN"]
    assert bits[0]["cores"] == {0, 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'engine.stages.stage1b_classify'`

- [ ] **Step 3: Write the types + peel_bits**

Create `engine/stages/stage1b_classify.py`:

```python
"""stage1b_classify.py -- structural sequential classification + depth (B2).

Classifies a cell's storage cores as latch / ff_chain / multibit /
recognized_unsupported and derives per-bit master/slave depth. Structure is
primary; the cell-name family (family_types regex) is an advisory cross-check
that reports divergence but never overrides. classify() never raises. stdlib +
engine only, ASCII only, simulator-free.

The naive discriminator (forward output-cone connectivity) mis-merges scan
multibit into one deep chain, because the scan daisy-chain links every earlier
bit into every later bit's output cone. peel_bits recovers the true bits from
the NESTED cone sets instead. See the B2 design doc, Section 2.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    nets: frozenset          # the storage core's nets
    role: str                # "latch" | "master" | "slave" | "unpaired"
    dist_to_out: int         # BFS influence-hops to nearest output


@dataclass(frozen=True)
class BitClass:
    outputs: tuple           # Q port(s) this bit drives, e.g. ("Q1",)
    stages: tuple            # ordered Stage list, master ... slave
    latch_stages: int        # == len(stages); latch=1, DFF=2, sync6=12
    ff_depth: int            # master/slave pair count; latch=0; k//2 otherwise
    paired_cleanly: bool     # False = odd core count / could not pair


@dataclass(frozen=True)
class SequentialClass:
    verdict: str             # "latch"|"ff_chain"|"multibit"
                             #   |"recognized_unsupported"|"combinational"
    bits: tuple
    name_hint: str
    divergence: str
    reason: str


def peel_bits(cores):
    """Partition cores into output bits via nested-cone peeling.

    Returns (bits, dangling): bits is a list of {"cores": set[int],
    "outputs": list[str]}; dangling is the set of core indices whose cone is
    empty (drive no output). Outputs are peeled smallest-cone first so each bit
    claims only its own not-yet-assigned cores; a later output with no new cores
    (e.g. a complementary QN) attaches to the bit already holding those cores.
    """
    reachers = {}                               # q -> set(core index)
    for i, c in enumerate(cores):
        for q in c.cone:
            reachers.setdefault(q, set()).add(i)
    assigned = set()
    bits = []
    for q in sorted(reachers, key=lambda q: (len(reachers[q]), q)):
        new = reachers[q] - assigned
        if not new:
            for b in bits:
                if reachers[q] <= b["cores"]:
                    b["outputs"].append(q)
                    break
            continue
        bits.append({"cores": set(new), "outputs": [q]})
        assigned |= new
    dangling = set(range(len(cores))) - assigned
    return bits, dangling
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: ASCII guard**

Run: `grep -rPn '[\x80-\xff]' engine/stages/stage1b_classify.py tests/engine/test_stage1b_classify.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add engine/stages/stage1b_classify.py tests/engine/test_stage1b_classify.py
git commit -m "feat(b2): classification types + nested-cone peel_bits"
```

---

### Task 3: Master/slave pairing + per-bit depth (`_pair`)

**Files:**
- Modify: `engine/stages/stage1b_classify.py` (add `_pair`)
- Test: `tests/engine/test_stage1b_classify.py` (add pairing tests)

**Interfaces:**
- Consumes: `peel_bits` output bit dict (`{"cores": set[int], "outputs": list[str]}`), the full `cores` list.
- Produces: `_pair(cores, bit) -> BitClass`. Within a bit: sort cores by `dist_to_out` ascending; 1 core -> `latch` (ff_depth 0); >=2 -> consecutive pairs, nearer=`slave`, farther=`master`, `ff_depth = k // 2`; odd k -> last core `unpaired`, `paired_cleanly=False`. `stages` emitted master-first (descending distance).

- [ ] **Step 1: Write the failing test**

Add to `tests/engine/test_stage1b_classify.py` (append; `_core` helper already defined in Task 2):

```python
from engine.stages.stage1b_classify import _pair


def test_pair_single_core_is_latch():
    cores = [_core(1, {"Q"})]
    bit = {"cores": {0}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 1
    assert bc.ff_depth == 0
    assert bc.paired_cleanly is True
    assert bc.stages[0].role == "latch"
    assert bc.outputs == ("Q",)


def test_pair_dff_two_cores_depth_one():
    cores = [_core(1, {"Q"}), _core(2, {"Q"})]      # slave dist1, master dist2
    bit = {"cores": {0, 1}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 2
    assert bc.ff_depth == 1
    assert bc.paired_cleanly is True
    # stages emitted master-first
    assert [s.role for s in bc.stages] == ["master", "slave"]
    assert bc.stages[0].dist_to_out == 2 and bc.stages[1].dist_to_out == 1


def test_pair_sync_depth_two():
    cores = [_core(1, {"Q"}), _core(2, {"Q"}), _core(3, {"Q"}), _core(4, {"Q"})]
    bit = {"cores": {0, 1, 2, 3}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 4
    assert bc.ff_depth == 2
    assert bc.paired_cleanly is True
    assert [s.role for s in bc.stages] == ["master", "slave", "master", "slave"]


def test_pair_odd_core_count_unpaired():
    cores = [_core(1, {"Q"}), _core(2, {"Q"}), _core(3, {"Q"})]
    bit = {"cores": {0, 1, 2}, "outputs": ["Q"]}
    bc = _pair(cores, bit)
    assert bc.latch_stages == 3
    assert bc.ff_depth == 1
    assert bc.paired_cleanly is False
    assert "unpaired" in [s.role for s in bc.stages]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py -k pair -v`
Expected: FAIL -- `ImportError: cannot import name '_pair'`

- [ ] **Step 3: Add `_pair`**

Append to `engine/stages/stage1b_classify.py`:

```python
def _pair(cores, bit):
    """Order a bit's cores by distance-to-output and pair master/slave.

    Nearer-to-output is slave, farther is master. Odd leftover -> 'unpaired'
    and paired_cleanly=False. Stages are emitted master-first (farthest first).
    """
    members = sorted(bit["cores"],
                     key=lambda i: (cores[i].dist_to_out, sorted(cores[i].nets)))
    outputs = tuple(sorted(bit["outputs"]))
    k = len(members)
    if k == 1:
        c = cores[members[0]]
        return BitClass(outputs, (Stage(c.nets, "latch", c.dist_to_out),),
                        1, 0, True)
    paired_cleanly = (k % 2 == 0)
    ff_depth = k // 2
    role = {}
    for p in range(0, k - 1, 2):
        role[members[p]] = "slave"          # nearer to output
        role[members[p + 1]] = "master"     # one stage farther back
    if not paired_cleanly:
        role[members[k - 1]] = "unpaired"
    ordered = sorted(members,
                     key=lambda i: (-cores[i].dist_to_out, sorted(cores[i].nets)))
    stages = tuple(Stage(cores[i].nets, role[i], cores[i].dist_to_out)
                   for i in ordered)
    return BitClass(outputs, stages, k, ff_depth, paired_cleanly)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/stages/stage1b_classify.py tests/engine/test_stage1b_classify.py
git commit -m "feat(b2): master/slave pairing + per-bit depth"
```

---

### Task 4: Verdict + name cross-check (`classify_cores`, `classify`)

**Files:**
- Modify: `engine/stages/stage1b_classify.py` (add `_name_crosscheck`, `classify_cores`, `classify`)
- Test: `tests/engine/test_stage1b_classify.py` (add verdict + end-to-end tests)

**Interfaces:**
- Consumes: `peel_bits`, `_pair` (this module); `build_storage_view` (Task 1); `core.principle_engine.classifier.classify_cell(cell_name).cell_class.value` for the advisory name family.
- Produces: `classify_cores(cores, cell_name="") -> SequentialClass` (pure, from a StorageCore list); `classify(graph, cell_name="") -> SequentialClass` (graph entry point). Verdict rules: 0 cores -> `combinational`; dangling core -> `recognized_unsupported`; 1 bit & `latch_stages==1` -> `latch`; 1 bit else -> `ff_chain`; >1 bit -> `multibit`. `divergence` set when the name family implies a different verdict; never overrides. Any exception -> `recognized_unsupported` with `reason="internal: <e>"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/engine/test_stage1b_classify.py`:

```python
import os
from engine.stages import stage0_parse
from engine.stages.stage1b_classify import classify_cores, classify

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SDFX = os.path.join(_REPO, "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt")


def test_classify_cores_latch():
    r = classify_cores([_core(1, {"Q"})])
    assert r.verdict == "latch"
    assert len(r.bits) == 1 and r.bits[0].ff_depth == 0


def test_classify_cores_ff_chain():
    r = classify_cores([_core(1, {"Q"}), _core(2, {"Q"})])
    assert r.verdict == "ff_chain"
    assert r.bits[0].ff_depth == 1


def test_classify_cores_multibit_mb8():
    r = classify_cores(_mb8_cores(), "MB8SRLSDFQSXGZ2422MZD1BWP130HPNPN3P48CPD")
    assert r.verdict == "multibit"
    assert len(r.bits) == 8
    assert all(b.ff_depth == 1 for b in r.bits)
    assert r.divergence == ""                    # name family 'mb' agrees


def test_classify_cores_odd_is_reviewed_ff_chain():
    r = classify_cores([_core(1, {"Q"}), _core(2, {"Q"}), _core(3, {"Q"})])
    assert r.verdict == "ff_chain"
    assert r.bits[0].paired_cleanly is False
    assert "odd" in r.reason.lower()


def test_classify_cores_dangling_unsupported():
    r = classify_cores([_core(1, {"Q"}), _core(2, set())])
    assert r.verdict == "recognized_unsupported"
    assert "drive no output" in r.reason


def test_classify_cores_no_cores_is_combinational():
    r = classify_cores([])
    assert r.verdict == "combinational"


def test_classify_cores_name_divergence():
    # name 'DFFX1' -> family flop -> implies ff_chain, but structure is a latch.
    r = classify_cores([_core(1, {"Q"})], "DFFX1")
    assert r.verdict == "latch"                  # structure wins
    assert r.divergence != ""
    assert "flop" in r.divergence


def test_classify_never_raises_on_bad_cores():
    class Bad:
        cone = frozenset({"Q"})
        # missing dist_to_out / nets -> _pair blows up
    r = classify_cores([Bad()])
    assert r.verdict == "recognized_unsupported"
    assert r.reason.startswith("internal:")


def test_classify_graph_sdfx_is_ff_chain_depth_one():
    g = stage0_parse.parse(open(_SDFX).read(), "SDFX_LPE_PLACEHOLDER")
    r = classify(g)
    assert r.verdict == "ff_chain"
    assert len(r.bits) == 1
    assert r.bits[0].ff_depth == 1
    assert [s.role for s in r.bits[0].stages] == ["master", "slave"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py -k "classify" -v`
Expected: FAIL -- `ImportError: cannot import name 'classify_cores'`

- [ ] **Step 3: Add the verdict logic**

Append to `engine/stages/stage1b_classify.py`:

```python
from engine.types import DeviceGraph
from engine.stages.storage_view import build_storage_view


_NAME_TO_VERDICT = {
    "latch": "latch",
    "flop": "ff_chain",
    "sync": "ff_chain",
    "mb": "multibit",
    "retn": "recognized_unsupported",
    "det": "recognized_unsupported",
    "drdf": "recognized_unsupported",
    "div4": "recognized_unsupported",
    "edf": "recognized_unsupported",
}


def _name_crosscheck(cell_name, verdict):
    """Advisory only: compare structural verdict to the cell-name family.
    Returns (name_hint, divergence). Never raises, never overrides."""
    if not cell_name:
        return ("", "")
    try:
        from core.principle_engine.classifier import classify_cell
        fam = classify_cell(cell_name).cell_class.value
    except Exception:
        return ("", "")
    expected = _NAME_TO_VERDICT.get(fam, "")
    if not expected or expected == verdict:
        return (fam, "")
    return (fam, "name=%s implies %s but structure=%s" % (fam, expected, verdict))


def classify_cores(cores, cell_name=""):
    """Classify a StorageCore list into one SequentialClass. Never raises."""
    try:
        if not cores:
            nh, _ = _name_crosscheck(cell_name, "combinational")
            return SequentialClass("combinational", (), nh, "",
                                   "no storage core -- combinational (not B2's job)")
        raw_bits, dangling = peel_bits(cores)
        bits = tuple(_pair(cores, b) for b in raw_bits)
        if dangling:
            names = sorted(sorted(cores[i].nets)[0] for i in dangling)
            nh, _ = _name_crosscheck(cell_name, "recognized_unsupported")
            return SequentialClass("recognized_unsupported", bits, nh, "",
                                   "storage core(s) drive no output: %s" % names)
        if len(bits) == 1:
            verdict = "latch" if bits[0].latch_stages == 1 else "ff_chain"
        else:
            verdict = "multibit"
        nh, div = _name_crosscheck(cell_name, verdict)
        reason = ""
        if any(not b.paired_cleanly for b in bits):
            odd = [b.latch_stages for b in bits if not b.paired_cleanly]
            reason = "odd core count in bit(s): %s (review, could not pair)" % odd
        return SequentialClass(verdict, bits, nh, div, reason)
    except Exception as e:
        return SequentialClass("recognized_unsupported", (), "", "",
                               "internal: %s" % e)


def classify(graph: DeviceGraph, cell_name="") -> SequentialClass:
    """Graph entry point: extract the storage view, then classify. Never raises."""
    try:
        view = build_storage_view(graph)
    except Exception as e:
        return SequentialClass("recognized_unsupported", (), "", "",
                               "internal: %s" % e)
    return classify_cores(view.cores, cell_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py -v`
Expected: PASS (17 passed)

- [ ] **Step 5: ASCII guard**

Run: `grep -rPn '[\x80-\xff]' engine/stages/stage1b_classify.py tests/engine/test_stage1b_classify.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add engine/stages/stage1b_classify.py tests/engine/test_stage1b_classify.py
git commit -m "feat(b2): verdict + advisory name cross-check (classify)"
```

---

### Task 5: Migrate `tools/seq_probe.py` onto the shared classifier

**Files:**
- Modify: `tools/seq_probe.py`
- Test: `tests/engine/test_seq_probe_migration.py` (new)

**Interfaces:**
- Consumes: `build_storage_view` (Task 1), `classify` (Task 4).
- Produces: no signature change to the probe's public `analyze(...)` entry point (it still returns its `(report, guess, bucket)`-style tuple), but its core extraction + heuristic are now delegated to the shared functions so probe verdicts and engine verdicts cannot diverge.

**Note to implementer:** Read `tools/seq_probe.py` in full first. Its current `_partition_by_cone`, `_reachable_outputs`, `_heuristic`, and `_bucket` re-implement (with the scan-chain bug) exactly what `build_storage_view` + `classify` now do correctly. Replace the inline influence-graph build and `_partition_by_cone` union-find with a call to `build_storage_view(graph)` and map `classify(...).verdict` onto the probe's existing bucket vocabulary. Preserve the probe's report text/anon behavior and CLI. Do NOT change `analyze`'s return contract. If the exact mapping from the new `verdict` to the old bucket strings is ambiguous, surface it rather than guessing (never fail silently).

- [ ] **Step 1: Write the failing characterization test**

Create `tests/engine/test_seq_probe_migration.py`:

```python
import os
from tools.seq_probe import analyze

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SDFX = os.path.join(_REPO, "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt")


def test_probe_sdfx_reports_ff_chain():
    # After migration the probe delegates to classify(); SDFX is a depth-1
    # master/slave FF-chain.
    report, guess, bucket = analyze(_SDFX, "SDFX_LPE_PLACEHOLDER", anon=True)
    assert "ff_chain" in (guess + " " + bucket + " " + report).lower()
```

- [ ] **Step 2: Run test to verify it fails or errors**

Run: `python3.12 -m pytest tests/engine/test_seq_probe_migration.py -v`
Expected: FAIL (pre-migration probe wording differs / does not emit `ff_chain`). If `analyze`'s signature differs from `(netlist_path, cell, anon=...)`, adjust the call in this test to match the real signature discovered in Step 1's read -- but keep the assertion that the SDFX probe surfaces the FF-chain verdict.

- [ ] **Step 3: Perform the migration**

Edit `tools/seq_probe.py`: replace the inline influence-graph construction and `_partition_by_cone`/`_heuristic` core logic with:

```python
from engine.stages.storage_view import build_storage_view
from engine.stages.stage1b_classify import classify
```

Route `analyze` through `build_storage_view(graph)` for the per-core report rows and through `classify(graph, cell)` for the verdict. Map `verdict` to the probe's existing bucket labels (`latch`/`ff_chain`/`multibit`/`recognized_unsupported`/`combinational`). Delete the now-orphaned `_partition_by_cone`, `_reachable_outputs`, `_heuristic`, and `_bucket` helpers only if they become unused by your changes (surgical -- do not remove code your changes did not orphan).

- [ ] **Step 4: Run the migration test + the full engine suite**

Run: `python3.12 -m pytest tests/engine/test_seq_probe_migration.py tests/engine/test_storage_view.py tests/engine/test_stage1b_classify.py -v`
Expected: PASS.

Run the stage1_ccc safety net to confirm it is untouched:
Run: `python3.12 -m pytest tests/engine/ -q`
Expected: all green (no regression).

- [ ] **Step 5: ASCII guard**

Run: `grep -rPn '[\x80-\xff]' tools/seq_probe.py tests/engine/test_seq_probe_migration.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add tools/seq_probe.py tests/engine/test_seq_probe_migration.py
git commit -m "refactor(b2): migrate seq_probe onto build_storage_view + classify"
```

---

## Self-Review

**1. Spec coverage** (design doc Sections 1-8):
- S3 output contract (`Stage`/`BitClass`/`SequentialClass`) -- Task 2 (types) + Task 3/4 (population). ✓
- S4.1 `build_storage_view` -- Task 1. ✓
- S4.2 `peel_bits` nested-cone -- Task 2. ✓
- S4.3 pairing + per-bit depth -- Task 3. ✓
- S4.4 verdict + name cross-check -- Task 4. ✓
- S5 placement (two new modules, seq_probe migrated, stage1_ccc unchanged) -- Tasks 1/2/4/5; stage1_ccc never in a Modify list. ✓
- S6 error handling (never raises, nothing silently dropped, ASCII) -- Task 4 (`classify` try/except, dangling reason, odd reason) + ASCII guard steps. ✓
- S7 testing (latch/DFF/sync/MB8/odd/dangling/divergence/internal-error pure tests; synth-latch + SDFX extraction) -- Tasks 1-4 cover every listed case. ✓
- S8 out of scope (B3 wiring, stage1_ccc rewire, RETN fingerprinting) -- none attempted. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases". Every code step shows complete code; every run step shows the exact command and expected result. ✓

**3. Type consistency:** `StorageCore(nets, dist_to_out, cone)` and `StorageView(cores, outputs, notes)` defined in Task 1 and consumed identically in Tasks 2-5. `peel_bits` returns `(bits, dangling)` with `bits` = list of `{"cores": set, "outputs": list}` in Task 2 and consumed exactly so in Task 3 (`_pair`) and Task 4 (`classify_cores`). `BitClass` fields (`outputs, stages, latch_stages, ff_depth, paired_cleanly`) match between Task 2 definition and Task 3/4 construction. `SequentialClass` fields (`verdict, bits, name_hint, divergence, reason`) consistent across Tasks 2 and 4. `classify_cell(...).cell_class.value` (verified values: `flop`, `mb`, `latch`, `unknown`) matches `_NAME_TO_VERDICT` keys. ✓

Expected test counts verified against the real code by inline prototype: synth-latch -> 1 core / cone {Q} / dist 1; SDFX -> 2 cores dist {1,2}; MB8 hand-built vector -> 8 bits depth 1; `classify_cell("DFFX1")` -> `flop`, `classify_cell("MB8...")` -> `mb`.
