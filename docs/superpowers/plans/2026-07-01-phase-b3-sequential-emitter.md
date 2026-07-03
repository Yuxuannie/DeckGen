# Phase B3 -- Sequential Deck Emitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble a runnable SPICE deck for a sequential arc (hold + mpw families) from collateral + Phase-A recipe + engine-derived bias, selected by B2 structural depth.

**Architecture:** New `assemble_sequential()` in `core/deck_assemble.py`, the sequential sibling of `assemble_combinational`. It classifies the cell (B2), maps structural depth to a grammar cluster-tag (hold: `CP.sync{N}.D`; mpw: `sync{N}.CP`/`CPN`), emits the recipe via Phase-A `emit()`, and wraps it in the same collateral + instance + bias scaffold B1 uses. A shared `depth_of()` in the B2 module is the single source of truth for depth. `tools/lib_deckgen.py` is repointed at the new function.

**Tech Stack:** Python 3.12, stdlib + in-repo `engine`/`core` only. No simulator.

## Global Constraints

- ASCII-only in `.py`/`.json`/`.sp`/`.spi` (latin-1 safety). Verify: `grep -rPn '[\x80-\xff]' <files>` empty.
- stdlib + `engine`/`core` imports only. Simulator-free. Tests run under `python3.12`.
- **Never raises / never drops:** a bad or unsupported arc is a named ERROR dict (`status="ERROR"`, `deck_text=None`, `error=<reason>`), never an exception, never a silent skip.
- **Never weaken a test assertion** to pass. Changing an existing assertion needs Yuxuan's explicit approval.
- Config/artifact paths relative to script location; never hardcode absolute paths.
- Mirror existing style in `core/deck_assemble.py` (the `_err` helper, `collateral_section`, `engine_bias_section`).

---

### Task 1: Shared `depth_of()` + commit the kept precycle wiring

The working tree already contains uncommitted, green "precycle from structural depth" wiring (`engine/stages/stage3_initialize.py`, `engine/pipeline.py`, `tests/engine/test_stage3_precycle.py`). This task extracts the depth arithmetic into one shared helper and commits the wiring as a reviewed unit.

**Files:**
- Modify: `engine/stages/stage1b_classify.py` (add `depth_of`)
- Modify: `engine/stages/stage3_initialize.py` (`_precycle_from_seq` uses `depth_of`)
- Test: `tests/engine/test_stage1b_classify.py` (add `depth_of` unit tests), `tests/engine/test_stage3_precycle.py` (already present, must stay green)

**Interfaces:**
- Produces: `depth_of(seq) -> int` in `engine.stages.stage1b_classify`. `ff_chain -> seq.bits[0].ff_depth`; `multibit -> max(b.ff_depth for b in seq.bits)`; everything else (`latch`, `combinational`, `recognized_unsupported`, `None`) `-> 0`.

- [ ] **Step 1: Write the failing test for `depth_of`**

Add to `tests/engine/test_stage1b_classify.py` (reuse that file's existing `classify_cores`/StorageCore helpers -- import `depth_of` at top):

```python
def test_depth_of_covers_every_verdict():
    from engine.stages.stage1b_classify import depth_of, SequentialClass, BitClass
    def bit(depth):
        return BitClass(outputs=("Q",), stages=(), latch_stages=2 * depth,
                        ff_depth=depth, paired_cleanly=True)
    ff = SequentialClass("ff_chain", (bit(3),), "", "", "")
    mb = SequentialClass("multibit", (bit(1), bit(4), bit(2)), "", "", "")
    latch = SequentialClass("latch", (bit(0),), "", "", "")
    comb = SequentialClass("combinational", (), "", "", "")
    assert depth_of(ff) == 3
    assert depth_of(mb) == 4
    assert depth_of(latch) == 0
    assert depth_of(comb) == 0
    assert depth_of(None) == 0
```

(If `BitClass`/`SequentialClass` positional fields differ, construct them the way the existing tests in this file already do -- match that call style exactly.)

- [ ] **Step 2: Run it, verify it fails**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py::test_depth_of_covers_every_verdict -v`
Expected: FAIL with `ImportError: cannot import name 'depth_of'`.

- [ ] **Step 3: Implement `depth_of`**

Add to `engine/stages/stage1b_classify.py` (near the top of the module-level functions, after the dataclasses):

```python
def depth_of(seq) -> int:
    """Structural pipeline depth -- single source of truth for the P3 precycle
    oracle and the B3 deck emitter. ff_chain -> the bit's master/slave pair
    count; multibit -> the deepest bit; latch / combinational /
    recognized_unsupported / None -> 0. Duck-typed on .verdict and
    .bits[i].ff_depth so callers need no new import."""
    if seq is None:
        return 0
    if seq.verdict == "ff_chain":
        return seq.bits[0].ff_depth
    if seq.verdict == "multibit":
        return max(b.ff_depth for b in seq.bits)
    return 0
```

- [ ] **Step 4: Route `_precycle_from_seq` through `depth_of`**

In `engine/stages/stage3_initialize.py`, add `depth_of` to the existing classify import site (or a local import inside the function to avoid an import cycle -- match how `_precycle_from_seq` currently references `seq`), and replace the `ff_chain`/`multibit` arithmetic branches so they call `depth_of(seq)` instead of recomputing `seq.bits[0].ff_depth` / `max(...)`. The returned `Derivation` **values must not change** (latch 0, ff_chain depth, multibit deepest, unsupported/None 1). Concretely, the two middle branches collapse to:

```python
    if v in ("ff_chain", "multibit"):
        from engine.stages.stage1b_classify import depth_of
        n = depth_of(seq)
        return Derivation(n, "%s: %d pre-cycle(s) push the datum through %d "
                             "master/slave stage(s) before capture" % (v, n, n),
                          STAGE)
```

Leave the `seq is None`, `latch`, and final unsupported/`combinational` branches exactly as they are (they return 1/0 with their existing reasons).

- [ ] **Step 5: Run the precycle + classify suites, verify green**

Run: `python3.12 -m pytest tests/engine/test_stage1b_classify.py tests/engine/test_stage3_precycle.py -v`
Expected: PASS (the 7 precycle tests unchanged; new `depth_of` test passes).

- [ ] **Step 6: ASCII check + commit**

```bash
grep -rPn '[\x80-\xff]' engine/stages/stage1b_classify.py engine/stages/stage3_initialize.py engine/pipeline.py tests/engine/test_stage3_precycle.py || echo clean
git add engine/stages/stage1b_classify.py engine/stages/stage3_initialize.py engine/pipeline.py tests/engine/test_stage3_precycle.py tests/engine/test_stage1b_classify.py
git commit -m "feat(b3): precycle from structural depth + shared depth_of()"
```

---

### Task 2: `_seq_cluster_tag()` depth->recipe mapping

**Files:**
- Modify: `core/deck_assemble.py` (add `SeqScope` + `_seq_cluster_tag`)
- Test: `tests/test_deck_assemble_sequential.py` (new)

**Interfaces:**
- Produces: `_seq_cluster_tag(family: str, depth: int, rel_dir: str) -> tuple[str, str, str]` returning `(cluster_tag, sel_rel_dir, sel_other_dir)`. Raises `SeqScope(reason)` for out-of-corpus depth or unknown family. `family` is `"hold"` or `"mpw"`. `rel_dir` is used only by the mpw family.
- Produces: `class SeqScope(Exception)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deck_assemble_sequential.py`:

```python
import pytest
from core.deck_assemble import _seq_cluster_tag, SeqScope


def test_hold_family_depth_mapping():
    assert _seq_cluster_tag("hold", 1, "fall") == ("CP.syncx.D", "fall", "rise")
    assert _seq_cluster_tag("hold", 2, "fall") == ("CP.sync2.D", "fall", "rise")
    assert _seq_cluster_tag("hold", 6, "fall") == ("CP.sync6.D", "fall", "rise")


def test_mpw_family_depth_mapping():
    assert _seq_cluster_tag("mpw", 1, "rise") == ("CPN", "rise", "fall")
    assert _seq_cluster_tag("mpw", 3, "fall") == ("sync3.CP", "fall", "rise")
    assert _seq_cluster_tag("mpw", 3, "rise") == ("sync3.CP", "rise", "fall")


def test_depth_beyond_corpus_raises_named_scope():
    with pytest.raises(SeqScope) as e:
        _seq_cluster_tag("hold", 7, "fall")
    assert "7" in str(e.value) and "6" in str(e.value)
    with pytest.raises(SeqScope):
        _seq_cluster_tag("mpw", 0, "rise")


def test_unknown_family_raises():
    with pytest.raises(SeqScope):
        _seq_cluster_tag("removal", 2, "rise")
```

- [ ] **Step 2: Run, verify fail**

Run: `python3.12 -m pytest tests/test_deck_assemble_sequential.py -v`
Expected: FAIL with `ImportError: cannot import name '_seq_cluster_tag'`.

- [ ] **Step 3: Implement the mapping**

Add to `core/deck_assemble.py` (after the `_DIR` constant, before `assemble_combinational`):

```python
class SeqScope(Exception):
    """Raised when a sequential arc falls outside the mined recipe corpus
    (depth range or family). Caught by assemble_sequential -> named ERROR."""


def _seq_cluster_tag(family, depth, rel_dir):
    """Map a structural (family, depth) to the grammar cluster-tag and the
    rise/fall variant to select. hold -> CP.sync{N}.D (depth-1 = CP.syncx.D,
    fall->rise only); mpw -> CPN (depth 1) / sync{N}.CP (2..6), variant follows
    the arc's rel_dir. Corpus depth ceiling is 6. Never returns silently on a
    miss -- raises SeqScope with a reason."""
    if family == "hold":
        if depth == 1:
            tag = "CP.syncx.D"
        elif 2 <= depth <= 6:
            tag = "CP.sync%d.D" % depth
        else:
            raise SeqScope("depth %d beyond mined hold corpus (syncx=1..sync6=6)"
                           % depth)
        return tag, "fall", "rise"
    if family == "mpw":
        other = {"rise": "fall", "fall": "rise"}.get(rel_dir)
        if other is None:
            raise SeqScope("mpw needs rel_dir rise|fall, got %r" % rel_dir)
        if depth == 1:
            tag = "CPN"
        elif 2 <= depth <= 6:
            tag = "sync%d.CP" % depth
        else:
            raise SeqScope("depth %d beyond mined mpw corpus (CPN=1, sync2..6)"
                           % depth)
        return tag, rel_dir, other
    raise SeqScope("unknown deck family %r (want hold|mpw)" % family)
```

- [ ] **Step 4: Run, verify pass**

Run: `python3.12 -m pytest tests/test_deck_assemble_sequential.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
grep -rPn '[\x80-\xff]' core/deck_assemble.py tests/test_deck_assemble_sequential.py || echo clean
git add core/deck_assemble.py tests/test_deck_assemble_sequential.py
git commit -m "feat(b3): depth->cluster_tag mapping for hold+mpw families"
```

---

### Task 3: `assemble_sequential()` emitter

**Files:**
- Modify: `core/deck_assemble.py` (add `_subckt_ports`, `assemble_sequential`)
- Test: `tests/test_deck_assemble_sequential.py` (extend), fixtures under `engine/fixtures/`

**Interfaces:**
- Consumes: `_seq_cluster_tag`/`SeqScope` (Task 2); `depth_of` (Task 1); `classify` from `engine.stages.stage1b_classify`; `stage0_parse.parse`, `stage1_ccc.decompose`, `stage2_sensitize.derive` from `engine.stages`; `Arc` from `engine.types`; `select_entry`/`emit`/`SelectionError` from `core.measurement.emit`; existing `collateral_section`, `engine_bias_section`, `_err` in this module.
- Produces: `assemble_sequential(arc_info: dict, netlist_src: str, grammar: dict) -> dict`. OK dict has keys `status="OK", deck_text, bias, verdict, depth, cluster_tag, family, error=None`. ERROR via `_err(...)` with the same shape.
- `sens.side_biases` is `{pin: Derivation}` with `.value` in `{0,1}`; convert to `{pin: value}` before `engine_bias_section` (which maps `1->vdd_value`, `0->vss_value`).

- [ ] **Step 1: Write the failing tests**

Extend `tests/test_deck_assemble_sequential.py` (append). These use the in-repo SDFX fixture; read it as text and pass it as `netlist_src`. Build `arc_info` inline with placeholder collateral values so `emit(fill_values=True)` and `collateral_section` resolve.

```python
import os
from core.deck_assemble import assemble_sequential
from core.measurement.emit import load_grammar

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDFX = os.path.join(_REPO, "engine", "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
_LATCH = os.path.join(_REPO, "engine", "fixtures", "SYNTH_LATCH.spi")


def _arc_info(cell, arc_type, rel_dir="fall"):
    return {
        "CELL_NAME": cell, "ARC_TYPE": arc_type,
        "REL_PIN": "CP", "REL_PIN_DIR": rel_dir,
        "CONSTR_PIN": "D", "CONSTR_PIN_DIR": "fall", "PROBE_PIN_1": "Q",
        "WHEN": "NO_CONDITION",
        "WAVEFORM_FILE": "std_wv.spi", "INCLUDE_FILE": "MODEL.inc",
        "NETLIST_PATH": cell + ".spi", "VDD_VALUE": "0.450",
        "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2e-10",
        "INDEX_2_VALUE": "5e-16", "MAX_SLEW": "1e-9", "OUTPUT_LOAD": "5e-16",
    }


def test_assemble_sequential_hold_sdfx_ok():
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "hold"), src, grammar)
    assert r["status"] == "OK", r["error"]
    assert r["family"] == "hold" and r["cluster_tag"] == "CP.syncx.D"
    assert "$" not in r["deck_text"]                       # no unresolved placeholder
    assert "cp2q_del1" in r["deck_text"]                   # recipe present
    assert "X1 " in r["deck_text"] and "SDFX_LPE_PLACEHOLDER" in r["deck_text"]
    assert any(l.startswith("VSE ") or l.startswith("VSI ")
               for l in r["deck_text"].splitlines())       # engine bias present


def test_assemble_sequential_mpw_sdfx_ok():
    grammar = load_grammar()
    src = open(_SDFX, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SDFX_LPE_PLACEHOLDER", "mpw", rel_dir="rise"),
                            src, grammar)
    assert r["status"] == "OK", r["error"]
    assert r["family"] == "mpw" and r["cluster_tag"] == "CPN"
    assert "cp2cp" in r["deck_text"]
    assert "cp2q_del2" not in r["deck_text"]               # mpw has no del2


def test_assemble_sequential_combinational_is_named_error():
    grammar = load_grammar()
    src = open(os.path.join(_REPO, "engine", "fixtures", "XOR2_RECON.subckt"),
               encoding="ascii").read()
    r = assemble_sequential(_arc_info("XOR2_RECON", "hold"), src, grammar)
    assert r["status"] == "ERROR" and r["deck_text"] is None
    assert "combinational" in r["error"].lower()


def test_assemble_sequential_latch_is_named_error():
    grammar = load_grammar()
    src = open(_LATCH, encoding="ascii").read()
    r = assemble_sequential(_arc_info("SYNTH_LATCH", "hold"), src, grammar)
    assert r["status"] == "ERROR" and "latch" in r["error"].lower()
```

Before writing code, confirm the two fixture cells' verdicts and the SYNTH_LATCH cell name:
Run: `python3.12 tools/lib_deckgen.py --dir engine/fixtures --dry-run` and read the verdict column; and `grep -i '^.subckt\|^.SUBCKT' engine/fixtures/SYNTH_LATCH.spi` for the exact cell name. If `SYNTH_LATCH` is not the cell name, fix the `_LATCH` cell string in the test. If XOR2_RECON is not `combinational`, pick another combinational fixture from the dry-run histogram.

- [ ] **Step 2: Run, verify fail**

Run: `python3.12 -m pytest tests/test_deck_assemble_sequential.py -k assemble_sequential -v`
Expected: FAIL with `ImportError: cannot import name 'assemble_sequential'`.

- [ ] **Step 3: Implement `_subckt_ports` + `assemble_sequential`**

Add to `core/deck_assemble.py`:

```python
def _subckt_ports(netlist_src, cell):
    """Port order from the `.subckt <cell> <p1> <p2> ...` header, for the X1
    instance line. Empty string if not found (assembly then reports it)."""
    for line in netlist_src.splitlines():
        toks = line.split()
        if len(toks) >= 2 and toks[0].lower() in (".subckt", ".subckt:") \
                and toks[1] == cell:
            return " ".join(toks[2:])
    return ""


def assemble_sequential(arc_info: dict, netlist_src: str, grammar: dict) -> dict:
    """Assemble a runnable sequential deck (hold or mpw family). Never raises: a
    bad/unsupported arc is a named ERROR row. Family from ARC_TYPE
    (hold -> CP.sync{N}.D; mpw|min_pulse_width -> sync{N}.CP/CPN); depth from the
    B2 structural class."""
    from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
    from engine.stages.stage1b_classify import classify, depth_of
    from engine.types import Arc
    from core.measurement.emit import select_entry, emit, SelectionError

    cell = arc_info.get("CELL_NAME", "")
    rel = arc_info.get("REL_PIN", "CP")
    constr = arc_info.get("CONSTR_PIN", "D")
    probe = arc_info.get("PROBE_PIN_1", "Q")
    rel_dir = _DIR.get(arc_info.get("REL_PIN_DIR", "fall"), "fall")
    constr_dir = _DIR.get(arc_info.get("CONSTR_PIN_DIR", "fall"), "fall")

    at = (arc_info.get("ARC_TYPE") or "").lower()
    if at in ("hold", "setup"):
        family = "hold"
    elif at in ("mpw", "min_pulse_width"):
        family = "mpw"
    else:
        return _err("unsupported ARC_TYPE %r for sequential emitter "
                    "(want hold|mpw)" % at)

    try:
        graph = stage0_parse.parse(netlist_src, cell)
        ccc = stage1_ccc.decompose(graph)
    except Exception as e:
        return _err("netlist parse failed: %s" % e)

    try:
        seq = classify(graph, cell)
        if seq.verdict in ("combinational", "recognized_unsupported"):
            return _err("not an assemblable sequential arc: verdict=%s (%s)"
                        % (seq.verdict, seq.reason or "no storage core"))
        if seq.verdict == "latch":
            return _err("latch not yet supported by the sequential emitter "
                        "(transparent; distinct methodology) -- %s"
                        % (seq.reason or "verdict=latch"))
        depth = depth_of(seq)
        try:
            tag, sel_rel, sel_other = _seq_cluster_tag(family, depth, rel_dir)
        except SeqScope as e:
            return _err("out of recipe corpus: %s" % e)

        arc = Arc(cell=cell, arc_type=at, rel_pin=rel, rel_dir=rel_dir,
                  constr_pin=constr, constr_dir=constr_dir,
                  when=arc_info.get("WHEN", "NO_CONDITION"),
                  measurement="", raw={"probe_pin": probe})
        sens = stage2_sensitize.derive(graph, arc, ccc)
        bias = {p: d.value for p, d in sens.side_biases.items()}

        try:
            entry = select_entry(grammar, arc_type="mpw", rel_dir=sel_rel,
                                 other_dir=sel_other, cluster_tag=tag)
        except SelectionError as e:
            return _err("no grammar entry for %s: %s" % (tag, e))

        header = arc_info.get("HEADER_INFO") or "%s %s %s->%s depth=%d" % (
            cell, at, rel, probe, depth)
        recipe = [l.replace("$HEADER_INFO", header)
                  for l in emit(entry, arc_info, fill_values=True)]

        pins = arc_info.get("NETLIST_PINS") or _subckt_ports(netlist_src, cell)
        deck_lines = (
            collateral_section(arc_info)
            + ["* ===== INSTANCE =====", "X1 %s %s" % (pins, cell)]
            + engine_bias_section(bias)
            + recipe
        )
        return {"status": "OK", "deck_text": "\n".join(deck_lines) + "\n",
                "bias": bias, "verdict": seq.verdict, "depth": depth,
                "cluster_tag": tag, "family": family, "error": None}
    except Exception as e:
        return _err("internal error during assembly: %s" % e)
```

Note: `_err` currently sets combinational-flavored keys (`chosen_when`, `output`, `out_dir`, `kit_match`). Those extra keys are harmless here; do not change `_err`. The OK dict returns the sequential keys above.

- [ ] **Step 4: Run the sequential tests, verify pass**

Run: `python3.12 -m pytest tests/test_deck_assemble_sequential.py -v`
Expected: PASS (all mapping + assembly tests). If `select_entry` fails for `CPN` with `rel_dir=rise/other=fall`, confirm that variant exists (`sync5.CP`/`sync6.CP` are rise/fall-only; `CPN` has both) -- adjust the test's `rel_dir` to a variant that exists, not the assertion of an existing one.

- [ ] **Step 5: Full engine + core suite regression**

Run: `python3.12 -m pytest tests/ -q`
Expected: PASS (no prior test regressed; B1 `assemble_combinational` untouched).

- [ ] **Step 6: ASCII check + commit**

```bash
grep -rPn '[\x80-\xff]' core/deck_assemble.py tests/test_deck_assemble_sequential.py || echo clean
git add core/deck_assemble.py tests/test_deck_assemble_sequential.py
git commit -m "feat(b3): assemble_sequential emitter (hold+mpw runnable decks)"
```

---

### Task 4: Repoint `tools/lib_deckgen.py` at `assemble_sequential`

**Files:**
- Modify: `tools/lib_deckgen.py`
- Test: `tests/test_lib_deckgen_smoke.py` (new)

**Interfaces:**
- Consumes: `assemble_sequential` (Task 3).

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_lib_deckgen_smoke.py`:

```python
import os, subprocess, sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args):
    return subprocess.run([sys.executable, "tools/lib_deckgen.py"] + args,
                          cwd=_REPO, capture_output=True, text=True)


def test_lib_deckgen_hold_writes_real_recipe_deck(tmp_path):
    out = str(tmp_path / "decks")
    p = _run(["--netlist", "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt",
              "--arc-type", "hold", "--out", out])
    assert p.returncode == 0, p.stderr
    deck = os.path.join(out, "SDFX_LPE_PLACEHOLDER.sp")
    assert os.path.exists(deck)
    text = open(deck, encoding="ascii").read()
    assert "cp2q_del1" in text and "$" not in text        # real recipe, resolved


def test_lib_deckgen_reports_combinational_without_deck(tmp_path):
    p = _run(["--dir", "engine/fixtures", "--arc-type", "hold",
              "--out", str(tmp_path / "d"), "--dry-run"])
    assert p.returncode == 0
    assert "combinational" in p.stdout                     # reported, never dropped
```

- [ ] **Step 2: Run, verify fail**

Run: `python3.12 -m pytest tests/test_lib_deckgen_smoke.py -v`
Expected: FAIL (current `lib_deckgen` has no `--arc-type` and writes `res.deck.text`, which contains the placeholder `.inc` collateral but the assertion `"$" not in text` may still pass -- the real failing signal is the missing `--arc-type` arg causing a non-zero exit).

- [ ] **Step 3: Repoint the driver**

In `tools/lib_deckgen.py`:
1. Add the CLI arg: `ap.add_argument("--arc-type", default="hold", choices=["hold", "mpw"], help="sequential deck family (default hold)")`.
2. Import the emitter and grammar loader at top (after the existing engine imports):
   ```python
   from core.deck_assemble import assemble_sequential      # noqa: E402
   from core.measurement.emit import load_grammar          # noqa: E402
   ```
3. In `process(...)`, add `arc_type` and `grammar` parameters. Replace the deck-writing branch (the `res.deck.text` write) so that for a sequential verdict it builds an `arc_info` and calls `assemble_sequential`:
   ```python
   if seq.verdict in _SEQUENTIAL:
       if dry_run:
           return (cell, seq.verdict, base + "  deck=(dry-run)")
       arc_info = {
           "CELL_NAME": cell, "ARC_TYPE": arc_type,
           "REL_PIN": rel, "REL_PIN_DIR": "fall" if arc_type == "hold" else "rise",
           "CONSTR_PIN": constr, "CONSTR_PIN_DIR": "fall", "PROBE_PIN_1": "Q",
           "WHEN": when or "NO_CONDITION",
           "WAVEFORM_FILE": "std_wv.spi", "INCLUDE_FILE": "MODEL.%s.inc" % arc_type,
           "NETLIST_PATH": "%s.spi" % cell, "VDD_VALUE": "0.450",
           "TEMPERATURE": "-40", "INDEX_1_VALUE": "1.2e-10",
           "INDEX_2_VALUE": "5e-16", "MAX_SLEW": "1e-9", "OUTPUT_LOAD": "5e-16",
       }
       asm = assemble_sequential(arc_info, open(path, encoding="ascii").read(),
                                 grammar)
       if asm["status"] != "OK":
           return (cell, seq.verdict, base + "  NO DECK (%s)" % asm["error"])
       os.makedirs(out_dir, exist_ok=True)
       deck_path = os.path.join(out_dir, "%s.sp" % cell)
       with open(deck_path, "w", encoding="ascii") as fh:
           fh.write(asm["deck_text"])
       return (cell, seq.verdict,
               base + "  deck=%s [%s/%s]" % (deck_path, asm["family"], asm["cluster_tag"]))
   ```
4. Load the grammar once in `main` (`grammar = load_grammar()`) and thread `args.arc_type` + `grammar` into each `process(...)` call.

Keep the combinational/unsupported reporting branch and the histogram exactly as they are (never drop a cell).

- [ ] **Step 4: Run the smoke test, verify pass**

Run: `python3.12 -m pytest tests/test_lib_deckgen_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Manual prototype confirmation**

Run: `python3.12 tools/lib_deckgen.py --dir engine/fixtures --arc-type hold --out proto_out`
Expected: SDFX writes a deck tagged `[hold/CP.syncx.D]`; combinational cells reported with reason; histogram printed. Repeat with `--arc-type mpw` (SDFX -> `[mpw/CPN]`).

- [ ] **Step 6: ASCII check + commit**

```bash
grep -rPn '[\x80-\xff]' tools/lib_deckgen.py tests/test_lib_deckgen_smoke.py || echo clean
git add tools/lib_deckgen.py tests/test_lib_deckgen_smoke.py
git commit -m "feat(b3): lib_deckgen emits real recipe decks via assemble_sequential"
```

---

## Self-Review

- **Spec coverage:** assemble_sequential (Task 3), hold+mpw depth mapping (Task 2), never-raises gating for latch/combinational/unsupported/out-of-corpus (Tasks 2+3), precycle wiring absorbed + single depth source (Task 1), lib_deckgen prototype repointed (Task 4), measurement pass-through via `emit()` (Task 3). All spec sections covered.
- **Type consistency:** `depth_of` (Task 1) consumed in Task 3; `_seq_cluster_tag`/`SeqScope` (Task 2) consumed in Task 3; `assemble_sequential` (Task 3) consumed in Task 4. `sens.side_biases[p].value` -> `bias` dict -> `engine_bias_section` (existing `{pin:0|1}` contract) is explicit.
- **Placeholder scan:** no TBD/TODO; every code step carries full code. The one runtime-verify step (Task 3 Step 1 fixture-name confirmation) has an explicit command and fallback instruction.
