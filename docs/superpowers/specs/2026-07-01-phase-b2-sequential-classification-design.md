# Phase B2 -- Structural Sequential Classification + Depth (Design)

**Status:** approved-approach (Approach A), design of record for the B2 plan.
**Branch:** claude/lucid-noether-cat8lr. Base: point2a-non-cons.
**Depends on:** Phase A (measurement grammar), B1 (combinational emitter) -- complete.
**Feeds:** B3 (sequential recipe emitter; fixes stage3 hardcoded `precycle_count=1`).

## 1. Goal

Given a sequential cell's structural decomposition, decide **what kind of
sequential element it is** and **how deep**, so B3 can emit the right
initialization/precycle recipe. Output one `SequentialClass`.

Positive (supported) verdicts -- only shapes we can structurally verify:
- `latch` -- one bistable storage core.
- `ff_chain` -- a master/slave pipeline of depth N (DFF=1, sync=2..12).
- `multibit` -- N independent output bits, each its own (usually depth-1) flop.

Non-positive:
- `recognized_unsupported` -- structure cannot be cleanly classified (dangling
  core, inconsistent partition), or a known-unsupported family (RETN/DET/DRDF/
  DIV4/EDF) whose defining signal lives in a flattened power/scan domain the
  structural graph cannot see. Reported with `reason`; never silently dropped.

RETN and similar power-domain edge cases are explicitly out of scope for the
demo; they land in `recognized_unsupported` with an explanatory reason.

## 2. Why the naive discriminator fails (the research nugget)

The MB8 cell `MB8SRLSDFQSXGZ2422MZD1BWP130HPNPN3P48CPD` (8-bit scan multibit,
16 storage cores, outputs Q1..Q8) proved that **forward output-cone
reachability cannot separate multibit bits**: the scan daisy-chain
(SI -> bit1 -> bit2 -> ... -> bit8) structurally links every earlier bit to
every later bit's Q, because SE is an undistinguished gate net in the influence
graph. Naive cone-connectivity merges all 16 cores into one group and misreads
the cell as a single depth-8 FF-chain.

But the structure is not lost -- it is recoverable from the **influence sets
themselves**, which nest exactly because of the scan chain (verified against the
real MB8 report):

```
reachers(Q1) = {slave1, master1}                       size 2
reachers(Q2) = {slave1,master1, slave2,master2}        size 4
...
reachers(Q8) = all 16 cores                            size 16
```

`stage1_ccc`'s master/slave/stageN role labels are WRONG on multibit (they
hallucinate a 16-deep chain). Therefore B2 does **not** consume those labels; it
re-derives bits and per-bit depth from the raw cores + cones (Approach A).

## 3. Output contract (= B2 -> B3 interface)

Depth is per-bit; the top-level verdict only says the shape. `latch`,
`ff_chain`, `multibit` all share one data shape.

```python
# engine/stages/stage1b_classify.py

@dataclass(frozen=True)
class Stage:
    nets: frozenset          # the storage core's nets (from build_storage_view)
    role: str                # "latch" | "master" | "slave" | "unpaired"
    dist_to_out: int         # BFS influence-hops to nearest output

@dataclass(frozen=True)
class BitClass:
    outputs: tuple           # Q port(s) this bit drives, e.g. ("Q1",)
    stages: tuple            # ordered Stage list, master ... slave
    latch_stages: int        # == len(stages); latch=1, DFF=2, sync6=12
    ff_depth: int            # master/slave pair count; latch=0; k//2 otherwise
    paired_cleanly: bool     # False = odd core count / could not pair (sync1p5)

@dataclass(frozen=True)
class SequentialClass:
    verdict: str             # "latch" | "ff_chain" | "multibit"
                             #   | "recognized_unsupported" | "combinational"
    bits: tuple              # BitClass list; len==1 for latch/ff_chain
    name_hint: str           # family from name regex (family_types); advisory
    divergence: str          # "" if structure agrees with name; else one line
    reason: str              # human-readable; required for unsupported/review
```

Verdict -> shape:

| shape | verdict | bits | per bit |
|---|---|---|---|
| 1 core | `latch` | 1 | stages=[latch], latch_stages=1, ff_depth=0 |
| 2N cores, 1 output cone | `ff_chain` | 1 | stages=[master..slave], ff_depth=N |
| M independent bits | `multibit` | M | each usually ff_depth=1 |
| dangling/inconsistent | `recognized_unsupported` | maybe empty | reason names anomaly |
| no storage cores | `combinational` | empty | guard; caller should not call B2 |

B3 consumption (fixes hardcoded `precycle_count=1`):
- `ff_chain` -> `precycle_count = bits[0].ff_depth` (sync6 -> 6, not 1)
- `multibit` -> emit per bit; `precycle_count = bit.ff_depth` (usually 1)
- `latch` -> no precycle
- `recognized_unsupported` -> B3 emits nothing, returns structured ERROR with
  `reason`. Never silently dropped.

## 4. Algorithms

### 4.1 Storage view (shared extraction)

`build_storage_view(graph) -> StorageView` in a new module
`engine/stages/storage_view.py`. It lifts the influence-graph + storage-core
logic already proven on 2175 cells (currently inline in `stage1_ccc.decompose`
and re-implemented in `tools/seq_probe.py`) into ONE place.

```python
@dataclass(frozen=True)
class StorageCore:
    nets: frozenset          # cross-coupled gate-controlling nets (the SCC core)
    dist_to_out: int         # min BFS influence-hops to any output port
    cone: frozenset          # output ports forward-reachable in influence graph

@dataclass(frozen=True)
class StorageView:
    cores: tuple             # StorageCore list
    outputs: tuple           # output ports (driven, non-rail)
    notes: tuple             # provenance
```

Construction mirrors `stage1_ccc` exactly (RAILS boundary, influence =
gate->drain + source->drain, Tarjan SCC>=2 intersected with gate-nets, BFS
distance). `cone` per core = `{q in outputs : _min_dist(influence, core, {q}) <
INF}`. Reuses `stage1_ccc._sccs`, `_min_dist`, `RAILS`.

`stage1_ccc.decompose` is NOT rewired in B2 (protects its green tests); the
~15-line duplication is noted for a later unification. `tools/seq_probe.py` is
migrated onto `build_storage_view` in this phase.

### 4.2 Peel bits (uses cones only, no extra BFS)

Transpose cones to `reachers(q) = {core : q in core.cone}`. Sort outputs by
`|reachers|` ascending; peel each output's not-yet-assigned cores. One ascending
loop covers scan-nested multibit, disjoint independent multibit, single-bit
chains, and complementary Q/QN outputs.

```python
def peel_bits(cores):
    reachers = {}                                   # q -> set(core index)
    for i, c in enumerate(cores):
        for q in c.cone:
            reachers.setdefault(q, set()).add(i)
    assigned, bits = set(), []
    for q in sorted(reachers, key=lambda q: (len(reachers[q]), q)):
        new = reachers[q] - assigned
        if not new:
            _attach_output(bits, q)                 # Q/QN: no new cores -> same bit
            continue
        bits.append({"cores": new, "outputs": [q]})
        assigned |= new
    dangling = set(range(len(cores))) - assigned     # cores with empty cone
    return bits, dangling
```

Validated against real MB8: yields bit_k = {slave_k, master_k} / {Q_k} for
k=1..8.

### 4.3 Pair master/slave + per-bit depth

Within a bit, sort cores by `dist_to_out` ascending. 1 core -> `latch`
(ff_depth 0). >=2 -> pair consecutive cores; in each pair the smaller distance
is `slave`, larger is `master`; `ff_depth = k // 2`. Odd k -> last core
`unpaired`, `paired_cleanly=False`, `ff_depth = k // 2`, reason notes odd count.
`stages` are emitted master-first (cores sorted by `dist_to_out` descending).

Validated: sync depth2 distances [1,2,3,4] -> pairs (1,2)(3,4) -> depth 2;
MB8 bit [slave=1, master=4] -> depth 1.

### 4.4 Verdict + name cross-check

```python
def classify(graph, cell_name=""):
    try:
        view = build_storage_view(graph)
        if not view.cores:
            return SequentialClass("combinational", (), name_hint(cell_name), "",
                                   "no storage core -- combinational (not B2's job)")
        raw_bits, dangling = peel_bits(view.cores)
        bits = tuple(_pair(view.cores, b) for b in raw_bits)
        if dangling:
            return _unsupported(cell_name, bits,
                                "cores drive no output: %s" % sorted(dangling))
        if len(bits) == 1:
            verdict = "latch" if bits[0].latch_stages == 1 else "ff_chain"
        else:
            verdict = "multibit"
        nh, div = _name_crosscheck(cell_name, verdict, bits)
        return SequentialClass(verdict, bits, nh, div, "")
    except Exception as e:
        return SequentialClass("recognized_unsupported", (), "", "",
                               "internal: %s" % e)
```

Name cross-check reuses `core/principle_engine/family_types` (regex CellClass).
Map name family -> expected verdict (LATCH->latch, FLOP/SYNC->ff_chain,
MB->multibit, RETN/DET/DRDF/DIV4/EDF->recognized_unsupported). Mismatch sets
`divergence` to one line; it never overrides the structural verdict.

## 5. Placement

- New: `engine/stages/storage_view.py` -- `build_storage_view` + `StorageView`,
  `StorageCore`.
- New: `engine/stages/stage1b_classify.py` -- `classify` + `SequentialClass`,
  `BitClass`, `Stage`, and internal `peel_bits` / `_pair` / `_name_crosscheck`.
- Modify: `tools/seq_probe.py` -- call `build_storage_view` and `classify`
  instead of its own core extraction + heuristic (probe becomes the real
  classifier's front-end, not a separate guess).
- Unchanged: `engine/stages/stage1_ccc.py` (its tests are the safety net; a
  later phase may rewire it onto `build_storage_view`).

`classify` is inserted between stage1 and stage3 by B3, which reads the recipe
shape. B2 delivers the module + tests only; B3 does the pipeline wiring.

## 6. Error handling

- `classify` never raises: any internal failure -> `recognized_unsupported`
  with `reason` (mirrors B1's never-raises contract).
- Nothing silently dropped: dangling cores, odd-core leftovers, and name
  divergence all surface in `reason` / `paired_cleanly` / `divergence`.
- ASCII-only, stdlib-only, simulator-free. Verify:
  `grep -rPn '[\x80-\xff]' engine/stages/storage_view.py engine/stages/stage1b_classify.py tools/seq_probe.py` empty.

## 7. Testing (TDD, python3.12)

Classification logic is a pure function of `StorageCore` lists -- tested
exhaustively on hand-built cores, including the MB8 nested-cone vector
transcribed from the real report. Structural extraction is tested on 1-2
netlists.

**Pure-logic tests** (`tests/engine/test_stage1b_classify.py`), building
`StorageCore` inputs directly:
- latch: 1 core, cone {Q} -> verdict `latch`, 1 bit, ff_depth 0.
- DFF: slave(dist1,{Q}) + master(dist2,{Q}) -> `ff_chain`, ff_depth 1.
- sync depth2: 4 cores dist 1..4, cone {Q} -> `ff_chain`, ff_depth 2.
- MB8 vector (16 cores, nested cones Q1..Q8 exactly per the report) ->
  `multibit`, 8 bits, each ff_depth 1, each `outputs` == ("Qk",).
- sync1p5 odd: 3 cores dist 1..3, cone {Q} -> `ff_chain`, `paired_cleanly` False,
  ff_depth 1, reason mentions odd count.
- dangling: a core with empty cone -> `recognized_unsupported`, reason names it.
- name divergence: cell "DFFX1" but structure single latch core -> verdict
  `latch`, `divergence` non-empty.
- internal error: malformed input -> `recognized_unsupported`, never raises.

**Extraction tests** (`tests/engine/test_storage_view.py`):
- synth latch `.spi` (one cross-coupled inverter pair, one output) ->
  `build_storage_view` returns 1 core, cone {Q}.
- real SDFX master-slave scan-DFF fixture
  (`engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt`) -> 2 cores, distinct
  distances, cone {Q}; end-to-end `classify` -> `ff_chain`, ff_depth 1.

Test discipline: never weaken an assertion to pass; fix the implementation
(CLAUDE.md). Changing an expected value requires Yuxuan's approval.

## 8. Out of scope (B2)

- B3 pipeline wiring / recipe emission (consumes `SequentialClass`).
- Rewiring `stage1_ccc` onto `build_storage_view`.
- Positive structural fingerprinting of RETN/DET/DRDF (needs power/scan-domain
  info the RAILS-flattened graph does not carry).
