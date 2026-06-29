# Phase A — Measurement Grammar — Final Whole-Branch Review

Range c2a9906..7fe8a42 (9 impl commits). Read-only review.
Scope read: review-final-phaseA.diff (full), regions.py / mine.py / emit.py (full),
design spec, and the two ground-truth templates the tests reference
(`mpw/template__CP__syncx__D__fall__rise__1.sp`, `delay/template_common_inpin_rise_delay_fall.sp`).

## Overall verdict

**Ready to merge for the LOCAL deliverable; one cheap fix and one doc/strengthening
item should land before the AIRGAP run** (which is where the feature actually earns
its value). The three modules compose cleanly, the key shapes align across seams,
the grammar faithfully captures every template's recipe region, and the full suite
is green. Nothing is broken. The reservation is conceptual, not functional: the
headline "proves completeness by byte-exact round-trip" is materially weaker than
advertised (the round-trip is structurally tautological — see I-1), so on the airgap
corpus the real comprehensiveness guarantee rests entirely on the classifier's
safe-default behaviour, not on the round-trip net. That is *mostly* fine because the
classifier defaults unknown lines to `recipe` (won't drop novel hold lines), but it
means one greedy collateral prefix (`.param cl`, I-2) is the kind of thing that would
fail silently there.

## Cross-cutting findings

### Critical
None. The branch does not contain a defect that breaks the local deliverable.

### Important

**I-1 — The round-trip "proof" is tautological; it cannot catch a misclassification.**
`mine.py:126-167`. `mine()` stores `recipe_lines = extract_recipe(text)` verbatim.
`validate()` recomputes `original = extract_recipe(text)` and compares it to the
stored `entry["recipe_lines"]`, where the entry is found by provenance
(`_select_for_template`). By construction the stored lines ARE the extraction of that
same file (dedup only collapses files whose extractions are byte-identical), so
`emitted == original` is **always** true: `coverage` is always 100.0 and `mismatches`
is always `[]`, regardless of whether `classify_line` is correct. `validate()` never
calls `emit()`, so it exercises neither the emitter nor the placeholder round-trip.
The only way it can fail is a non-deterministic `extract_recipe` or pointing mine and
validate at different dirs — neither a real condition.

Root cause: the spec's round-trip presumed mining *concrete decks* with a lossy
de-parameterization step (`v(CP) -> v($REL_PIN)`), with `emit()` re-parameterizing.
But the corpus is *templates that already contain `$REL_PIN`/`$PROBE_PIN_1`/...*, so
"templatization" is a no-op and there is no lossy step for a round-trip to validate.

Impact: this is exactly the blind spot the brief asked about. A recipe line wrongly
dropped to `collateral` is dropped identically in mine and validate, so it round-trips
clean while being absent from the grammar — silently. The "comprehensiveness proof"
proves only that `glob` is stable. The genuine protection against missing recipe lines
is the classifier's default-to-`recipe` (good — see Airgap section), not this check.

Recommendation (before trusting airgap output): add a real, independent oracle. The
cheapest is a **conservation check** in `validate()` — assert that every source line
lands in exactly one bucket and `recipe ∪ collateral ∪ bias ∪ blank == original`
(catches drops/dupes), plus have `validate()` actually call `emit(entry, {})` so the
emitter is on the validated path. Neither makes round-trip catch a *semantic*
misclassification (nothing here can, given a single shared classifier), so at minimum
**document** that the airgap net is human inspection of the per-arc-type entry diff,
not the 100% number. Soften the "byte-exact round-trip proves completeness" claim in
the module docstrings/spec to "reproduces the captured region" — it does not validate
that the captured region is the *right* region.

**I-2 — `.param cl` is a greedy collateral prefix; airgap (hold) clock params could be
silently dropped.** `regions.py:218`. `_COLLATERAL_PREFIXES` contains `".param cl"`
(no trailing space), matched via `low.startswith(...)`. The real line is
`.param cl = '$OUTPUT_LOAD'`, so the safe prefix is `".param cl "` or `".param cl ="`.
As written it also swallows any recipe `.param cl<x>` — `clk_period`, `clock_*`,
`cl_offset`, etc. The airgap corpus is **hold + delay**, where clock-named params are
plausible. Combined with I-1 (no net), such a line would vanish from the grammar with
no diagnostic. One-character-class fix; should land before the airgap run.

### Minor

**M-1 — Comment-prefix collision: `"* waveform"` swallows the recipe header
`"* Waveform timestamps"`.** `regions.py:222-227,238`. `_COLLATERAL_COMMENTS` has
`"* waveform"`; `classify_line` uses `startswith`, so the recipe-region section header
`* Waveform timestamps` (mpw line 47, delay line 40) classifies as `collateral` and is
dropped from the grammar, while sibling headers (`* SPICE options`, `* Optimization
settings`, `* Measurements`, ...) are kept. Purely cosmetic (the `.param` lines beneath
it are kept; comments don't affect simulation), but it shows the comment heuristics are
collision-prone and, per I-1, invisible. If byte-faithful recipe regions ever matter
downstream, tighten to the exact known headers.

**M-2 — Delay filename parser is hardcoded to the `common_inpin...delay` scheme.**
`regions.py:268-274`. Only `template_common_inpin_*_delay_*` delay names get real
dirs/tag; any other delay cluster in the airgap corpus falls through to the degenerate
fallback (`rel_dir=""`, `other_dir=""`, `cluster_tag=<stem>`). Such templates are still
mined and still "round-trip" (provenance-keyed), but their `select_entry` keys are
unusable for Phase B. Not breaking; worth a comment that delay-side clustering is
local-corpus-shaped. (mpw/hold via the `template__...` branch generalize fine; arc_type
derives from the dir name, so a `hold/` dir auto-keys `arc_type="hold"` — good.)

**M-3 — `select_entry` returns `matches[0]` when `cluster_tag` is omitted.**
`emit.py:70-82`. Two clusters sharing `(arc_type, rel_dir, other_dir)` are
disambiguated only by `cluster_tag`; without it the first wins silently. Phase A's
round-trip selects by provenance (not `select_entry`), so this only bites the Phase B
seam — acceptable now, but the ambiguity should be a documented precondition.

**M-4 — `grammar["entries"]` unguarded.** `emit.py:74,78` raises bare `KeyError` on a
malformed grammar rather than a typed error — a soft "never fail silently" gap on the
public `select_entry`. Low impact (internal contract).

**M-5 — `open()` without `with` in several spots** (`mine.py:130,156,189`;
`test_artifact.py:308`) and `errors="replace"` on template reads (`mine.py:130,156`):
non-ASCII template bytes become U+FFFD identically on both sides, so I-1 hides it and
the JSON's `ensure_ascii=True` masks it in the artifact. Resource-hygiene / latent-data
issues only; defer.

**M-6 — Dead/cosmetic bits from task reviews:** `regions.py:270` `_delay` unused and the
inner `"_delay" in head` test is redundant with the branch guard; `regions.py:285`
empty-`toks` fallback uses the whole stem as tag; `test_artifact.py:299,302` unused
`json` import and `_REPO`; `test_artifact.py` has no entry-count assertion (pinning
`== 55` would guard against silent grammar shrinkage); `test_emit` default case asserts
`$REL_PIN` replaced but does not positively assert `$CONSTR_PIN`/`$PROBE_PIN_1` got
replaced. All defer. Note: T7's "m-1 lowercase `vdd_value` dead branch" is **not present**
in the committed `emit.py` (54 lines, no such branch) — already resolved or never in
this seam.

## Airgap-generalization assessment (deep)

This is the load-bearing question, and the answer is **moderately reassuring, for a
non-obvious reason** — and it is *not* the round-trip.

The architecture generalizes to a hold+delay corpus without code change in the ways
that matter:
- `arc_type` is derived from the parent directory name (`regions.py:265`), so a `hold/`
  directory yields `arc_type="hold"` automatically — nothing hardcodes delay/mpw.
- Family-2 templates (hold, setup, removal, recovery, mpw) share the
  `template__<tag>__<d1>__<d2>__<N>.sp` scheme, which the `"template__"` branch parses
  generically (multi-token tags, trailing index drop, dir-pair detection). Hold will
  parse like mpw.
- Mining is provenance-keyed, so even a template whose key degrades still gets captured.

The crucial safety property is the classifier's **default-to-`recipe`**
(`regions.py:242`): a novel hold line that matches no collateral prefix and no bias/
collateral comment is *kept*. So the dangerous direction (dropping a real recipe line)
can only happen when a recipe line **accidentally matches a collateral signature**.
Enumerating the prefixes against plausible hold recipe lines, almost all are safe or
fail in the *over-inclusive* direction (extra rails like `VVNW`/`VVPW`, or differently
named slew params, would leak INTO recipe — harmless verbatim reproduction, not a
drop). The genuinely dangerous collisions are narrow:
1. `.param cl` (I-2) — the one real drop risk; fix before airgap.
2. `* waveform` vs `* Waveform timestamps` (M-1) — cosmetic comment drop.

So the comprehensiveness claim is **likely to hold on airgap** — but it holds because
of the safe default, not because anything verifies it. The flip side: because the
round-trip is tautological (I-1), if a hold idiom *does* trip a collateral prefix, the
airgap operator sees "100% reproduced" and ships an incomplete grammar. The mitigation
the spec leans on ("validate report is the comprehensiveness proof," success criterion
4) is the part that doesn't actually work. Recommended airgap protocol: don't trust the
100%; eyeball the per-arc-type entry count and one emitted hold recipe against a known
template, and add the conservation check from I-1.

Net: airgap generalization is **sound by construction for the common case, with two
sharp edges (one to fix: `.param cl`) and a proof mechanism that should be relabeled,
not relied on.**

## Minor-findings triage

**Should fix before the AIRGAP run (cheap, value-protecting):**
- I-2 `.param cl` -> `.param cl ` / `.param cl =`. One line. Directly protects the
  hold-corpus claim.
- I-1 mitigation: at minimum relabel the "proof" in docstrings/spec; ideally add the
  line-conservation assertion and route `validate()` through `emit()`. Do before
  anyone treats the airgap 100% as a gate.

**Defer (cosmetic / non-blocking, fine to merge as-is):**
- M-1, M-2, M-3, M-4, M-5, M-6 — none affect the local deliverable or the suite.
- Optional nicety worth doing opportunistically: pin `test_artifact` to the known entry
  count (55) so a future silent grammar shrinkage fails a test.

## Strengths

- **Clean seams.** `parse_template_key` emits `{arc_type, rel_dir, other_dir,
  cluster_tag}`; `select_entry` keys on exactly those; `emit` consumes `entry["key"]`
  and `entry["recipe_lines"]`. No shape mismatch across the three modules. The
  `_DEFAULT` path that `emit` reads is the path `mine` writes — consistent.
- **The right safety default.** Unknown line -> `recipe` is the correct bias for a
  "must be comprehensive" miner: it errs toward keeping, so novel airgap recipe lines
  survive. This single decision is what makes the feature plausibly airgap-safe.
- **Content-based (not positional) classification** genuinely handles the interleaved
  layout (recipe options at top, collateral in the middle, nodeset/meas at the bottom),
  verified against the real mpw template where the init block sits under a `* Pin
  definitions` header yet classifies correctly line-by-line.
- **Provenance dedup** is a tidy, honest model of "grammar size = number of distinct
  recipes," and the provenance list makes the round-trip selection exact without a
  Phase-B cell->cluster mapping leaking in early — the seam is kept clean per the spec.
- **Discipline kept:** stdlib-only, ASCII-only, typed `SelectionError` listing tried +
  closest keys, value-substitution correctly delegated to `deck_builder` rather than
  re-implemented. The emit default (identity-only fill, value placeholders left intact)
  is correctly consumable by downstream `$`-substitution — and the recipe lines'
  reliance on collateral-defined params (`vdd_value`, `cl`, `rel_pin_slew`) is by design
  (Phase B supplies the collateral section), not a latent bug.

## Fixes applied

### I-2: `.param cl` greedy collateral prefix (regions.py)

Added trailing space to all `.param` entries in `_COLLATERAL_PREFIXES`:
`.param cl` -> `.param cl `, and similarly for `vdd_value`, `vss_value`,
`rel_pin_slew`, `constr_pin_slew`. Now matches only at a word boundary (e.g.
`.param cl = '...'` classifies as `collateral`; `.param clk_period = '5n'`
classifies as `recipe`). Non-`.param` prefixes left unchanged.

New test `test_cl_boundary_fix` in `tests/measurement/test_regions.py` asserts
both cases.

### I-1: validate() strengthened + round-trip claim relabeled (mine.py, regions.py, spec)

**2a — emit() on the validated path:** `validate()` now imports and calls
`emit(entry, {})` (empty arc_info, no substitution) instead of reading
`entry["recipe_lines"]` directly. Exercises the emitter on every validation call.

**2b — Conservation regression guard:** Added `partition(text) -> dict` to
`regions.py` (returns all 4 buckets with raw lines). In `validate()`, checks
`sum(len(v) for v in partition(text).values()) == len(text.splitlines())` for
every template, surfacing any future classify_line divergence as a mismatch entry.
New test `test_conservation_mpw` in `tests/measurement/test_roundtrip.py` asserts
conservation on all 63 mpw templates.

**2c — Honest relabeling:** Module docstring in `mine.py` drops
"Comprehensive-by-construction" and states clearly that round-trip validates the
*captured* region, not semantic completeness. Spec
`docs/superpowers/specs/2026-06-28-measurement-grammar-phase-a-design.md` updated
in four places: airgap constraint section, Miner description, round-trip validation
description, and success criterion 4.

### Verification results

- `tests/measurement/` (19 tests): all passed (19/19)
- `python3.12 -m pytest -q`: **677 passed** (was 675; +2 new tests)
- Round-trip: delay 4/4 (100%), mpw 63/63 (100%)
- Grammar byte-identical: diff shows trailing-newline only (committed file has
  one extra `\n` as predicted by brief; entries are identical)
- ASCII guard: clean (no hits on core/measurement, grammar JSON, spec)
