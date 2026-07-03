# Generative Measurement Grammar (Phase G) -- Design Spec

Date: 2026-07-02
Status: Draft for review
Owner: Yuxuan

## Context

Phase A mined the template corpus into `config/measurement_grammar.json`:
55 distinct recipe regions, each a **verbatim block of lines** keyed by
`(arc_type, rel_dir, other_dir, cluster_tag)` with file-level provenance.
Phase B routes a new cell to an entry **structurally** (S0 parse -> S1 CCC ->
classify family + depth -> cluster_tag), so an unseen cell already generates
without a per-cell template.

What is still missing -- and what this phase exists for -- is stated by the
product owner (2026-07-02):

> Every deck, regardless of cell or arc type, must let a reviewer quickly
> understand where each part came from and WHY it is done that way. This is
> the key to Demo 1 actually being adopted.

Today the answer to "why is this line here" is only *provenance* ("it was in
template X"). The recipe blobs are opaque: the `cross=4` in `cp2q_del1`, the
`t01..t04` wiring, the `OPT1` search block -- none carry their meaning. The
selection is explainable; the content is not.

Priority frame (owner, 2026-07-02): fast + accurate first, then usable, then
debuggable. Therefore the **non-negotiable gate for every step below is
byte-parity**: explainability must not move a single deck byte.

## Goal

Turn the mined grammar from "canonicalized verbatim regions" into a
**generative, explainable, auditable grammar**:

1. Every recipe line is *produced by a named rule* (semantic primitive), not
   copied from a blob.
2. Every generated deck ships a machine-written **audit sidecar** mapping each
   line to {source, rule, inputs, why, provenance}.
3. Families that differ only by a parameter (mpw `sync{N}`, delay direction
   variants) collapse into **one parameterized generator**, so coverage and
   review effort scale with the number of RULES, not the number of templates.

## Non-goals

- No change to deck bytes, ever, at any phase boundary (parity gates below).
- No inline comments in the deck as the explanation vehicle (that would break
  byte-parity vs the template flow). The explanation is a sidecar.
- No extrapolation-by-default beyond the mined corpus: a depth-7 hold cell
  still refuses (`SeqScope`) unless an explicit flag is set (see G2). A wrong
  deck is worse than a refusal.
- Not a SPICE methodology redesign: the grammar reproduces the three-party
  methodology; it does not invent measurement schemes.

## Design

### 1. IR: semantic primitives (what a recipe IS)

Decompose each recipe region into an ordered list of typed primitives. The
taxonomy comes from reading the 55 real entries, not speculation:

| Primitive | Owns | Example `why` |
|---|---|---|
| `SimOptions` | `.options` / `.option sampling` / `.save` | simulator accuracy + LHS sampling policy (methodology constants) |
| `Param` | `max_slew`, `related_pin_t0x`, `constrained_pin_t0x` wiring | timing skeleton: where each stimulus edge sits in the transient window |
| `OptSearch` | `opt_init/lb/ub`, `OPT1(...)`, `constr_pin_offset`, optmod | the bisection search that finds the constraint value (hold/mpw only) |
| `Nodeset` | `.option ptran_nodeset` + pattern `.nodeset` block | initialize storage nodes so cycle 1 starts from a known state |
| `Stimulus` | `XV<pin> ... stdvs_* ...` sources | which pin toggles, with which multi-phase waveform, anchored to which t0x |
| `Meas` | `.meas` statements (`prop_delay`, `out_transition`, `cp2q`, `cp2cp`) | what is measured, between which edges; `cross=N` = which cycle |
| `Tran` | `.tran ... monte=...` | transient length covering all phases + MC sweep |
| `VerbatimBlock` | anything the decompiler cannot parse | explicit escape hatch -- listed, never silent |

Each primitive has: parameters, a deterministic `emit() -> lines` (exact
formatting), and a `why` template (one human-readable sentence referencing the
methodology, with the arc's actual pins/values substituted).

### 2. Decompiler, not hand-authoring (how we get there safely)

The IR for each of the 55 entries is produced by an extended miner
(`core/measurement/decompile.py`), NOT written by hand. Correctness oracle:

- **Grammar-parity gate:** for every entry, `emit(decompile(entry)) ==
  entry.recipe_lines` byte-for-byte. A CI test; any mismatch names the entry.
- Unparseable lines land in `VerbatimBlock` -- explicitly listed in a coverage
  report ("N% of recipe lines semantically owned, M lines verbatim in entries
  X, Y"). The verbatim residue is burned down over time; it is a metric, not
  a failure.

This mirrors the Phase A airgap posture: on the full airgap corpus, novel line
shapes degrade to verbatim (kept, listed) -- never dropped, never approximated.
The miner/decompiler runs unchanged there (stdlib, ASCII).

### 3. Parameterized generators (the truly generative step)

Once entries are IR, families that differ only by a parameter merge:

- **delay family:** 4 entries -> 1 generator x (rel_dir, out_dir).
- **mpw `sync{N}.CP` / hold `CP.sync{N}.D`:** the phase count, `t0x` ladder,
  and `cross=` indices are *functions of depth N*. One generator + N replaces
  ~12 entries.
- Named one-off clusters (`WWL*`, `DET.*`, `retn.CP`, ...) stay as single
  entries until a second family member justifies a generator.

A generator's parity gate: for every (family, N) inside the mined corpus, the
generated recipe must byte-match the mined entry. **Outside** the corpus
(depth 7+), the default stays refusal; generation-by-extrapolation is allowed
only behind an explicit `--allow-extrapolation` flag AND is stamped
`extrapolated: true` in the audit sidecar, so a reviewer can never mistake an
extrapolated deck for a corpus-validated one.

### 4. Audit sidecar (the surface the reviewer sees)

Per generated deck, the SAME assembly pass (never a second parser -- no drift
by construction) writes `nominal_sim.explain.json` next to `nominal_sim.sp`:

```jsonc
{
  "arc_id": "hold_DFFQ1_Q_fall_CP_rise_NO_CONDITION_1_1",
  "selection": {                         // why THIS recipe
    "family": "hold", "depth": 3, "cluster_tag": "CP.sync3.D",
    "evidence": "S1 storage core: master={...} slave={...}; depth via ...",
    "extrapolated": false
  },
  "lines": [
    {"n": 12, "src": "collateral", "rule": "corner.vdd",
     "inputs": {"corner": "ssgnp_0p450v_m40c_..."},
     "why": "supply from corner name (0p450 -> 0.45V)"},
    {"n": 31, "src": "engine", "rule": "p1.side_bias",
     "inputs": {"pin": "SE", "value": 0},
     "why": "P1 sensitization: SE=0 selects functional D path",
     "provenance": "S2 proof, sensitizing state ..."},
    {"n": 47, "src": "grammar", "rule": "Meas.cp2cp",
     "inputs": {"rel": "CP", "constr": "D", "cross": [3, 4]},
     "why": "launch-to-constraint separation the OPT1 search shrinks",
     "provenance": ["template__CP__sync3__D__fall__rise__1.sp"]}
  ]
}
```

`src` is one of `grammar | collateral | engine | instance` -- exactly the four
origins of today's five deck sections. Surfaces:

- CLI: `--explain` prints a one-screen per-section summary (screenshot-safe).
- GUI: deck viewer gains a side panel / hover showing the record for the line
  under the cursor; the run report links each generated deck to its sidecar.

## Phasing (each phase independently shippable, each gated by parity)

- **G0 -- sidecar over the CURRENT mined grammar.** No IR yet: `src` +
  entry-level provenance + section-level `why` (the classify evidence, the P1
  proof, the resolved collateral paths are all already computed -- persist
  them). Cheap; immediate audit value.
- **G1 -- decompiler + IR.** 100% byte round-trip on the local corpus;
  verbatim-residue report; per-line semantic `why` replaces section-level.
- **G2 -- generators.** delay family + `sync{N}` ladders; grammar entries for
  those families become generated artifacts checked against the mined corpus;
  extrapolation flag lands (default off).
- **G3 -- airgap run.** Decompile the full hold+delay corpus; review verbatim
  residue; decide extrapolation policy with real depth distribution in hand.

## Success criteria

1. Deck bytes unchanged at every phase boundary (existing deck-parity suite +
   the new grammar-parity test stay green).
2. G1: 100% of the 55 local entries round-trip; verbatim residue enumerated.
3. G2: generated families byte-match every mined (family, N) instance.
4. Every generated deck has a sidecar whose line count covers 100% of deck
   lines (conservation check, like `partition()` today).
5. A reviewer can answer "why is this line here" for any line of any deck
   from the sidecar alone, without opening a template.
6. stdlib-only, ASCII-only, runs unchanged in the airgap.

## Risks

- **Over-normalization silently changing bytes** -> the round-trip gate plus
  VerbatimBlock escape hatch; formatting is owned by `emit()`, asserted
  byte-exact.
- **Explanation drift vs deck content** -> sidecar is emitted by the same
  pass that emits the deck; there is no second code path to diverge.
- **Taxonomy churn** -> start with the eight primitives above, extend only
  when a real corpus line forces it (same "decided empirically" rule as
  Phase A cluster keys).
- **`why` text wrong in methodology terms** -> the `why` templates are a
  reviewable, greppable table in one file; methodology owner review is a
  listed deliverable of G1, not an afterthought.

## Open questions (resolve during planning)

- Should MC decks share the nominal sidecar or get their own?
- GUI rendering form: hover vs split panel (defer to a design pass; the JSON
  contract above is the stable part).
- Whether `selection.evidence` should embed the full S1/S2 proof or link to
  the existing verify sidecar (`core/verify_sidecar.py`) to avoid duplication.
