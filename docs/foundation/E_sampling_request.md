# E: Targeted Server-Side Sampling Request

## Context

DeckGen ships 63 templates, all in `min_pulse_width/` (MPW). The 688 HSPICE
rules reference 457 unique templates across 10 directories. The 404 unshipped
templates span 9 directories that have **zero local representatives**:

| Directory | Unshipped | Shipped |
|-----------|----------|---------|
| hold | 204 | 0 |
| nochange | 130 | 0 |
| non_seq_hold | 39 | 0 |
| setup | 10 | 0 |
| non_seq_setup | 8 | 0 |
| nochange_low_low | 8 | 0 |
| delay | 2 | 0 |
| nochange_high_low | 2 | 0 |
| nochange_low_high | 1 | 0 |
| min_pulse_width | 0 | 63 |

## Selection Criteria

Each template below:
1. Is in `template_rules.json` but NOT in `templates/N2P_v1.0/mpw/`
2. Belongs to a Task C cluster with no shipped representative
3. Has a specific structural prediction that, if wrong, invalidates the
   principle hypothesis for its cluster

## Sampling List (10 templates)

### 1. `hold/template__common__rise__fall__1.sp`

**Cluster**: hold / common (simplest hold template, fallback for standard FFs)
**Prediction**: `stdvs_rise/fall` waveform (NOT `stdvs_mpw_*`); glitch
measurement present (`.meas` with glitch threshold); ~7 timing variables
(t01-t07); `.ic` statements for Q/QN initialization; NO `constr_pin_offset`;
pushout measurement present.
**Why it matters**: This is the hold fallback template -- if its structure
differs from prediction, the entire hold measurement methodology model is wrong.

### 2. `hold/template__latch__rise__fall__glitch__minq__1.sp`

**Cluster**: hold / latch / glitch_minq
**Prediction**: Same waveform family as #1; glitch `.meas` with `minq`
threshold check (output must not dip below threshold); `.ic` for internal
latch state (more `.ic` lines than #1 due to latch transparency); probe at
Q pin.
**Why it matters**: Tests whether latch topology adds `.ic` statements vs
flop topology. If no extra `.ic`, the latch/flop distinction in templates
is cosmetic, not structural.

### 3. `nochange/template__ckg__hold__fall__en__fall__pushout__negative__0.sp`

**Cluster**: nochange / ckg / hold sub-arc / pushout negative
**Prediction**: Nochange-specific waveform (different from `stdvs_rise/fall`
and `stdvs_mpw_*`); both pushout AND percentage-glitch measurements; EN pin
as constrained pin with enable-specific stimulus; `negative` pushout direction
encoded in measurement.
**Why it matters**: Nochange templates are 130 of 404 unshipped. If their
structure is fundamentally different from hold/setup (different waveform
model, different measurement semantics), a separate principle branch is needed.

### 4. `non_seq_hold/template__latch__fall__rise__pushout__1.sp`

**Cluster**: non_seq_hold / latch / pushout (async control)
**Prediction**: Multi-phase waveform with async pin (CD or SDN) stimulus;
pushout measurement; NO glitch in this variant (pushout-only); `.ic` for
latch initialization; differs from hold/latch by having async control
timing instead of clock-data timing.
**Why it matters**: Non-seq hold is the third largest unshipped category
(39 templates). If async stimulus structure matches hold structure (just
different pins), the principle engine can unify them. If fundamentally
different (different `.tran` structure), they need separate treatment.

### 5. `setup/template__common__rise__fall__1.sp`

**Cluster**: setup / common (all 10 setup rules are trivial per Task B)
**Prediction**: `stdvs_rise/fall` waveform; pushout measurement only (NO
glitch -- setup checks margin, not glitch); ~7 timing variables; `.ic` for
Q/QN; structurally identical to hold/common except for timing point
definitions and measurement direction.
**Why it matters**: If setup templates are structurally identical to hold
templates (differing only in timing parameters), the principle engine can
use a single template family with parameterized timing points. Task B
confirmed setup is fully trivial -- this validates whether structural
simplicity matches.

### 6. `delay/template__invdX__fall.sp`

**Cluster**: delay / invdX (only 2 delay templates exist)
**Prediction**: Minimal template -- `stdvs_fall` single-direction waveform;
`cp2q_del1` delay measurement only; ~3 timing variables (t01-t03); NO
glitch, NO `.ic`, NO pushout; NO `constr_pin_offset`; possibly no
`$CONSTR_PIN` (delay arcs have no constraint pin).
**Why it matters**: If delay templates are this minimal, the principle engine
needs almost no logic for delay arcs. If they're complex, the 2 delay rules
hide unexpected structure.

### 7. `hold/template__retn__removal__fall__rise__glitch__minq__2.sp`

**Cluster**: hold / retn / removal (retention + removal arc)
**Prediction**: Retention-mode `.ic` statements (RETN pin state + internal
latch state); RETN pin stimulus in waveform; glitch `.meas` with minq
threshold; multi-phase waveform (more phases than standard hold due to
retention entry/exit); variant `_2` suggests dual-probe or deeper pipeline.
**Why it matters**: Retention templates are the most structurally complex
family (Task C: up to 13 tokens in path). If `.ic` count and waveform
phases match the predicted scaling, the principle engine can parameterize
retention depth. If not, retention needs per-variant templates.

### 8. `hold/template__MB__common__rise__fall__2.sp`

**Cluster**: hold / MB / common (multi-bank sequential)
**Prediction**: Multi-bank `.ic` initialization (more `.nodeset` or `.ic`
lines than standard hold); MB-specific internal probe paths (X1.MB*);
glitch measurement; standard hold waveform but with additional bank-select
pin biasing.
**Why it matters**: MB (multi-bank) is a major discriminating category in
Task B (D1/D2 groups, 67 rules). If MB templates differ from standard hold
only in `.ic` count and pin biasing, the principle engine can generate them
by parameterizing the initialization block. If they have fundamentally
different waveform structure, MB needs its own template family.

### 9. `hold/template__SLH__rise__SE__rise__pushout__1.sp`

**Cluster**: hold / SLH (scan latch hold)
**Prediction**: SE (scan enable) pin as constraint pin; pushout measurement
(no glitch in this variant); scan-path-specific waveform timing; `.ic` for
scan latch state.
**Why it matters**: SLH templates appear in trivial Task B groups (E/rise
signatures), suggesting they're structurally unique to scan latches. If
their structure is just "hold + SE pin", no new principle is needed. If they
have scan-specific waveform phases, scan cells need their own branch.

### 10. `non_seq_hold/template__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__2.sp`

**Cluster**: non_seq_hold / retn / nonseqhold (retention + async + glitch)
**Prediction**: Most complex template family -- RETN pin + CD pin stimulus;
glitch measurement at `minq` threshold with `bl_b` (bitline) probe; `.ic`
for retention state + latch state; multi-phase waveform with retention
entry, async assertion, and observation phases; variant `_2` for dual-probe.
**Why it matters**: This is the deepest nesting in the template namespace
(Task C: 13 tokens). If it matches the predicted additive structure
(retention `.ic` + async stimulus + glitch `.meas` + bl_b probe), the
principle engine can compose templates from orthogonal building blocks. If
it's monolithic, composition is not viable.

---

## Instructions for Yuxuan

For each template above, please provide (photograph or transcribe):
1. The first 10 lines (header + DONT_TOUCH_PINS + metadata comments)
2. All `.meas` statements
3. All `.ic` or `.nodeset` lines
4. The `.tran` line
5. The waveform `.inc` line (which `stdvs_*` model)
6. Total line count

This is sufficient to confirm or invalidate each prediction. Full file
content is welcome but not required.

If any template path does not exist on the server, report which ones are
missing -- this indicates the rule extraction has stale paths.
