# B: Rule Set Group-By Analysis

## Full Tables

The complete machine-readable data lives in `docs/foundation/B_tables/`:

- `B1_trivial.csv` -- all 228 trivial signatures (236 rules)
- `B2_discriminating.csv` -- all 115 discriminating signatures (452 rules),
  including JSON column with `(cell_pattern -> template)` pairs per group
- `README.md` -- column schema and join instructions

Note: the CSV tables use a more granular probe abstraction than the narrative
below (e.g., `contains_Q|len_1` vs `contains_Q`), producing 343 total
signatures vs the 315 in the narrative. The narrative coarsened probe patterns
for readability; the CSV is the authoritative source.

## Overview

This document analyzes the 688 HSPICE rules from `config/template_rules.json`
(those with `function="getHspiceTemplateName"`), grouping them by **arc signature**
to reveal which template selections are purely determined by the arc's electrical
characteristics versus those that additionally depend on the cell's structural
identity.

## Methodology

### Arc Signature Definition

Each rule is mapped to a 5-tuple signature:

```
(arc_type, rel_pin, rel_pin_dir, constr_pin_dir, probe_pattern)
```

Where:
- `arc_type` -- hold, setup, min_pulse_width, removal, nochange_*, etc.
- `rel_pin` -- normalized: lists joined with `|`, empty list as `[]`
- `rel_pin_dir` -- rise, fall, or null
- `constr_pin_dir` -- rise, fall, or null
- `probe_pattern` -- abstracted from probe field:
  - `none` -- null/empty probe
  - `contains_Q1` -- probe.contains includes "Q1"
  - `contains_bl_b` -- probe.contains includes "bl_b"
  - `len_N` -- probe.len == N (no contains)
  - Compound descriptions for other cases

### Classification

- **Trivial** -- signature maps to exactly 1 template (cell pattern is irrelevant)
- **Discriminating** -- signature maps to 2+ templates (cell pattern matters)

---

## Headline Numbers

| Metric | Count | % of 688 Rules |
|--------|------:|---------------:|
| Total arc signatures | 315 | -- |
| Trivial signatures | 192 | 29.1% (200 rules) |
| Discriminating signatures | 123 | 70.9% (488 rules) |

**Key finding:** Nearly 71% of HSPICE rules live in discriminating groups where
the cell pattern is the deciding factor for template selection. The arc signature
alone is insufficient for 123 of 315 signature classes.

**Implication for v2:** The 50-rule principle engine target requires a cell
topology classifier, not just arc signature matching. Pure signature-based
selection covers only 29% of rules. However, the discrimination is structured
(see analysis below) -- it follows ~8 categorizable patterns, not arbitrary
per-cell overrides.

---

## Table B1: Trivial Groups (1 template per signature)

Sorted by num_rules descending. 192 signatures, 200 rules total.

Top entries (full table truncated for readability):

| arc_type | rel_pin | rel_pin_dir | constr_pin_dir | probe_pattern | rules | template |
|----------|---------|-------------|----------------|---------------|------:|----------|
| hold | E | rise | rise | len_2 | 3 | `hold/template__SLH__rise__SE__rise__pushout__2.sp` |
| hold | CLKIN | rise | rise | none | 2 | `hold/template__latch__rise__rise__glitch__maxq__1.sp` |
| hold | CLKIN | rise | fall | none | 2 | `hold/template__latch__rise__fall__pushout__1.sp` |
| nochange_low_high | I0 | rise | fall | none | 2 | `nochange/template__ckgmux2__setup__rise__s__fall__pushout__1.sp` |
| nochange_low_high | I0 | fall | rise | none | 2 | `nochange/template__ckgmux2__hold__fall__s__rise__pushout__1.sp` |
| hold | CLK\|CP | rise | rise | len_1 | 2 | `hold/template__common__rise__rise__1.sp` |
| hold | CLK\|CP | rise | fall | len_1 | 2 | `hold/template__common__rise__fall__1.sp` |
| setup | CP | rise | rise | len_1 | 1 | `setup/template__common__rise__rise__1.sp` |
| setup | CP | rise | fall | len_1 | 1 | `setup/template__common__rise__fall__1.sp` |
| setup | CPN | fall | rise | none | 1 | `setup/template__common__fall__rise__1.sp` |
| setup | E | fall | rise | none | 1 | `setup/template__common__LH__fall__rise__1.sp` |

Notable patterns:
- **All 10 setup rules are trivial** (6 signatures) -- setup template selection
  depends only on pin/direction, never on cell topology
- **All specific-pin min_pulse_width rules are trivial** (WWL*, CPN, EN, E, I0)
- **All nochange with `contains_iq3_iq4_preZ_tgo` probe are trivial** (16 rules)
- **All basemeg hold rules with specific WWL pins are trivial** (16 rules)
- **All delay_arc_types rules are trivial** (2 rules)

---

## Table B2: Discriminating Groups (>1 template per signature)

123 signatures, 488 rules total. Top groups by num_templates:

### D1: (hold, CP, rise, rise, len_1) -- 34 rules, 30 templates

| Cell Pattern | Template |
|-------------|----------|
| `*DFDET*` | `hold/template__SLH__rise__SE__rise__pushout__3.sp` |
| `*EDF*D*` | `hold/template__EDF__D__rise__rise__glitch__1.sp` |
| `*EDF*D*` | `hold/template__EDF__notD__rise__rise__glitch__1.sp` |
| `*EDFCNSPQ*D*` | `hold/template__EDF__D__rise__rise__glitch__minq__1.sp` |
| `CKLNQAO22*` | `hold/template__latch__rise__rise__glitch__maxq__1.sp` |
| `DCCKDIV4*` | `hold/template__DIV4__rise__rise__1.sp` |
| `MB*` | `hold/template__MB__common__rise__rise__2.sp` |
| `MB*EDF*ITL*` | `hold/template__EDF__rise__E__rise__glitch__maxq__1.sp` |
| `MB*SRLSDF*` | `hold/template__MB__rise__E__rise__glitch__maxq__1.sp` |
| `MB*SRLSDF*ICG*` | `hold/template__MB__notD__rise__E__rise__glitch__minq__1.sp` |
| `MB2SRLSDFAO22*` | 8 templates (DA1..DD2 rise) |
| `MB2SRLSDFOA22*` | 8 templates (DA1..DD2 rise) |
| `MB8SRLSDFOR2*` | 2 templates (DA, DB rise) |
| `[]` (fallback) | `hold/template__common__rise__rise__1.sp` |

### D2: (hold, CP, rise, fall, len_1) -- 33 rules, 29 templates

Mirror of D1 for constr_pin_dir=fall. Same cell patterns, corresponding fall
templates.

### D3: (unknown, [], null, null, none) -- 16 rules, 16 templates

| Cell Pattern | Template |
|-------------|----------|
| `*CKLH*` | `hold/template__latch__fall__fall__glitch__minq__1.sp` |
| `*DET*` | `min_pulse_width/template__DET__CP__fall__rise__1.sp` |
| `*DRDF*` | 2 templates (CP fall/rise) |
| `*SYNC2*`..`*SYNC6*` | 2 templates each (sync CP + D) |
| `[]` (fallback) | 2 templates (gclk clkdivrst) |

### D4: (min_pulse_width, CP, null, rise, none) -- 10 rules, 10 templates

| Cell Pattern | Template |
|-------------|----------|
| `*AO2*` | `min_pulse_width/template__AO2__rise__fall__1.sp` |
| `*DETQNLTSO*` | 2 templates (LP D/notD) |
| `*DETQNRESO*` | 2 templates (RE D/notD) |
| `*OA2*, *OR2*` | `min_pulse_width/template__OR2__rise__fall__1.sp` |
| `CKGNR*, CKGOA*, CKGOR*` | `min_pulse_width/template__CKGOR2__rise__fall__1.sp` |
| `PTCKG*` | `min_pulse_width/template__PTCKG__CP__rise__fall__1.sp` |
| `[]` (fallback) | 2 templates (CP rise/fall, DA rise/rise) |

### D6-D13: nochange groups (CP/CLK, 4 direction combos)

8 groups of 5-8 rules each. Cell patterns discriminate:
- `*CKG*AN*, *CKG*OR*` -- standard AND/OR clock gater
- `*CKG*ND*, *CKG*NR*` -- inverted NAND/NOR clock gater
- `*CKGIAN*` -- isolated AND gater
- Specific TSMC cell names -- per-cell overrides
- `RLH*` -- retention latch cells
- `RS*NBNSP*`, `RS*NBSP*` -- retention flop variants

### D14-D21: nochange/CLK groups

8 groups of 5 rules each. Cell patterns discriminate:
- `CK*ND3*` -- 3-input NAND clock gaters
- `CK*OAI21*` / `CK*AOI21*` / `CK*NR3*` -- complex-gate clock gaters
- `CK*RCB*D*, DCCK*RCB*D*` -- RCB-based clock gaters

### Remaining ~90 groups (2-8 rules each)

Cover SYNC2-6 probe_Q1 hold, retention RETN non_seq, GCLK divider hold,
latch E-pin hold with QN probes, CPN-based hold/removal, MUX-based nochange.

---

## Why Cell Pattern Matters: Discrimination Hypotheses

### Category 1: Internal Topology (250+ rules) -- CONFIRMED (M4 from Phase 1)

The cell's flip-flop/latch topology dictates:
- **Nodeset initialization**: MB* needs multi-latch init; SYNC needs pipelined
  Q1 init; AO22/OA22 need per-data-input init
- **Measurement points**: EDF measures through embedded logic; DIV4 has
  divider-specific timing
- **Waveform phasing**: SYNC needs multi-cycle stimulus; DET needs pulse-detect

Template names directly encode topology (template__MB__, template__EDF__,
template__sync2__, template__SLH__, etc.).

### Category 2: Gate-Type Logic Family (80+ rules) -- CONFIRMED (M7)

Clock gater enable logic determines glitch behavior:
- AND/OR -> `__ckg__` templates (standard polarity)
- NAND/NOR -> `__ckgn__` templates (inverted polarity)
- Complex (AOI21, OAI21, NR3, ND3) -> `__ck__` with per-enable measurement

### Category 3: Multi-Input Data Path (32+ rules) -- CONFIRMED (M5)

AO22/OA22/OR2 cells have multiple data inputs (DA1..DD2). Each input needs
its own template with the correct constraint pin wired. One AO22 cell
generates 8 separate hold templates.

### Category 4: Output Pin Polarity (40+ rules) -- CONFIRMED (M3)

Probe pin determines maxq (Q rises to VDD) vs minq (QN falls to VSS).
Many 2-template discriminating groups are simply the maxq/minq split.

### Category 5: Retention State Machine Depth (36+ rules) -- CONFIRMED (M8)

Retention cells with SYNC2-6 need progressively deeper pipeline
initialization. Template names encode depth (syn2, syn3, ..., syn6).

### Category 6: MUX Port Count (24+ rules) -- CONFIRMED

CKGMUX2 uses 20% glitch threshold; CKGMUX3 uses 10% glitch threshold.
Different MUX sizes require different measurement sensitivity.

### Category 7: Scan/Test Mode Variants (12+ rules) -- SPECULATIVE

DCCKDIV cells have multiple hold-arc variants for clken, clkdivrst,
scanmode, divs. These may represent different functional modes of the same
cell rather than topology differences.

### Category 8: Per-Cell Silicon Overrides (8+ rules) -- SPECULATIVE

Some groups contain rules for exact TSMC cell names mapping to `_0` suffix
templates, suggesting cell-specific measurement parameter overrides.

---

## Summary

| Discrimination Category | Rules | Status | Phase 1 Ref |
|------------------------|------:|--------|-------------|
| Internal topology (MB/EDF/SYNC/DET/SLH) | ~250 | CONFIRMED | M4 |
| Gate-type logic family (AND/OR vs NAND/NOR) | ~80 | CONFIRMED | M7 |
| Output pin polarity (maxq/minq) | ~40 | CONFIRMED | M3 |
| Retention state machine depth (syn2-6) | ~36 | CONFIRMED | M8 |
| Multi-input data path (AO22/OA22/OR2) | ~32 | CONFIRMED | M5 |
| MUX port count (2 vs 3 input) | ~24 | CONFIRMED | -- |
| Scan/test mode variants | ~12 | SPECULATIVE | -- |
| Per-cell silicon overrides | ~8 | SPECULATIVE | -- |

### Implications for DeckGen v2

1. **Arc signature alone covers only 29% of rules.** A principle engine must
   include a cell topology classifier.

2. **The discrimination is structured, not arbitrary.** 6 of 8 categories are
   confirmed physical principles. The 50-rule target requires encoding these
   categories as classifier axes, not as 688 individual pattern matches.

3. **Setup rules are fully trivial.** Setup template selection needs no cell
   topology -- only pin identity and direction.

4. **The largest groups (D1/D2: hold/CP/rise) are the most important** to
   classify correctly -- 67 rules (9.7%) with 30 distinct templates each.

5. **The `[]` fallback entries provide safe defaults.** Every discriminating
   group has a wildcard fallback, ensuring graceful degradation when no
   specific cell pattern matches.
