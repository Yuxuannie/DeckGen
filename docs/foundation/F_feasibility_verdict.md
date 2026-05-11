# F: Feasibility Verdict and v2 Target Rule Count

## 1. Trivial-Side Estimate

### Raw data

228 trivial signatures covering 236 rules (34.3% of 688). Each signature
maps to exactly one template regardless of cell pattern.

### Dedup by (directory, topology_tag)

Many trivial signatures differ only in pin name or direction but share
the same structural template family. Grouping by `(directory, first_token)`:

| Directory | Topologies | Examples |
|-----------|----------:|---------|
| hold | 10 | common, latch, SLH, ESLH, MB, RCB, basemeg, gclk, rsdf, ckg_nx |
| min_pulse_width | 11 | CP, CPN, WWL, WWL0, WWL1, WWL_N, WWL0_N, WWL1_N, EN, E, I0 |
| nochange | 3 | ckg, ckgmux2, ckgmux3 |
| nochange_high_low | 1 | retn |
| nochange_low_high | 1 | retn |
| nochange_low_low | 1 | retn |
| non_seq_hold | 2 | latch, retn |
| non_seq_setup | 1 | retn |
| setup | 1 | common |
| delay | 1 | invdX |

**32 trivial template families** cover 228 signatures (236 rules).

### Further compression

Several of these families are direction pairs of the same principle:
- `hold/common` rise/fall + rise/rise = 1 principle with direction parameter
- `min_pulse_width/WWL*` 6 pin variants = 1 principle with pin parameter
- `nochange_*/retn` 3 directories = 1 retention-nochange principle

After parameterizing direction and pin:

**~20 trivial principles** cover 236 rules.

---

## 2. Discriminating-Side Estimate

452 rules across 115 discriminating signatures. Task B identified 8
discrimination categories, 6 confirmed.

### Sub-principle count per category

| Category | Rules | Status | Sub-principles | Reasoning |
|----------|------:|--------|---------------:|-----------|
| Internal topology | ~250 | CONFIRMED | 15 | MB, EDF, SYNC(as-one), DET, SLH, DIV4, DRDF, retn, rsdf, ESLH, RCB, flop, AO22, OA22, common(fallback) |
| Gate-type logic | ~80 | CONFIRMED | 6 | ckg, ckgn, ckgian, ck-complex, ckgmux2, ckgmux3 |
| Output polarity | ~40 | CONFIRMED | 2 | maxq, minq (parameterizable, arguably 1 principle with a flag) |
| Retention depth | ~36 | CONFIRMED | 6 | syn2, syn3, syn4, syn5, syn6, base -- but parameterizable as `depth=N`, so arguably 1 principle |
| Multi-input expansion | ~32 | CONFIRMED | 1 | One principle: "for each data input pin, generate a template" -- the 8 pins are enumerated from the cell, not from rules |
| MUX port count | ~24 | CONFIRMED | 2 | ckgmux2 (20% threshold), ckgmux3 (10% threshold) |
| Scan/test variants | ~12 | SPECULATIVE | 4 | clken, clkdivrst, scanmode, divs |
| Per-cell overrides | ~8 | SPECULATIVE | 2 | variant_0, variant_1 (escape-hatch entries) |

**Raw sum: 38 discriminating sub-principles.**

### Compression opportunities

- **Output polarity** (maxq/minq): One principle with a polarity parameter.
  Reduces 2 -> 1.
- **Retention depth** (syn2-6): One principle with a depth parameter.
  Reduces 6 -> 1.
- **Multi-input expansion**: Already 1 principle (enumerate pins from cell
  definition). No reduction needed.
- **Gate-type logic**: ckg and ckgn differ only in polarity inversion.
  ckgmux2 and ckgmux3 differ only in threshold. Reduces 6 -> 3.

**Compressed: ~30 discriminating principles.**

---

## 3. Residual: SPECULATIVE Categories

### Scan/test mode variants (~12 rules, 4 sub-principles)

These are functional sub-arcs of GCLK divider cells (DCCKDIV2, DCCKSDIV2).
Each variant (clken, clkdivrst, scanmode, divs) needs a different stimulus
waveform. This is **not compressible** into fewer principles because each
represents a physically different timing path.

**Recommendation**: Keep as 4 explicit principles. These cells are rare
(2 cell families) but the measurement methodology genuinely differs.

### Per-cell silicon overrides (~8 rules, 2 sub-principles)

Specific TSMC cell names (e.g., `CKGAN2CCHD1BWP143M169H3P45CPD*`) map to
`_0` variant templates instead of the default `_1`. This appears to be
a measurement parameter tweak (different timing threshold) for specific
silicon variants.

**Recommendation**: Keep as escape-hatch entries in the rule engine.
These are irreducibly empirical -- they exist because specific cells
exhibited unexpected behavior in silicon. A principle engine should have
an explicit override mechanism for these (~2-5 entries). Do not try to
derive a principle.

---

## 4. Verdict

### Three numbers

| Bound | Principle count | Assumptions |
|-------|----------------:|-------------|
| **Lower bound** | **35** | Aggressive parameterization: output polarity, retention depth, and gate-type logic all collapsed to parameterized principles; scan variants folded into GCLK; overrides as escape-hatch list |
| **Expected** | **45-55** | Realistic: most compressions above hold, but some topology sub-principles need to stay separate (EDF vs SLH vs RCB each have different measurement structure); escape-hatch list of ~5 entries |
| **Upper bound** | **70** | Conservative: if some topology distinctions are structural rather than parametric (confirmed by Task E sampling), and scan/test variants each need distinct templates |

### Assessment of the original "50 rules" target

The original Phase 2 target of "50 rules" was set before data existed.
The data supports **45-55 as the expected range**, which brackets 50.
The target is **plausible but tight**. Specifically:

- 50 is achievable if output polarity, retention depth, and MUX port count
  are parameterized (which they should be -- these are numeric parameters,
  not structural differences).
- 50 is not achievable if every topology sub-principle (15 from internal
  topology alone) turns out to require separate templates. Task E sampling
  will resolve this.

**Recommendation**: Retain 50 as the target with an explicit escape-hatch
mechanism for residual empirical entries (per-cell overrides). Track the
actual count during Phase 3 implementation. If it exceeds 60, re-evaluate
whether the topology classifier needs finer granularity.

---

## 5. What This Means for Phase 2 Architecture

Task C found that templates almost never repeat (average cluster size 1.11 --
412 families for 457 templates). This means the MCQC approach of selecting
from a large pre-built template library is essentially a 1:1 lookup with
extra steps. A principle engine has two viable architectures:

**(A) Select + parameterize**: Keep a reduced template library (~50-70
templates organized by the families from Task C) and have the principle
engine select the correct family, then parameterize direction, polarity,
depth, pin names, and thresholds. This preserves the ability to diff
against MCQC output (regression testing) and is lower-risk.

**(B) Generate from scratch**: Derive the deck structure from first
principles (waveform model + measurement type + pin topology + initialization
requirements). More principled but harder to validate against MCQC ground
truth, and the near-1:1 template-to-family ratio means the "library" is
already near-minimal.

**Recommendation**: Architecture (A) -- select + parameterize. The template
families are well-structured (Task C grammar covers 98.9%) and the
parameterization axes are clear from Task B (direction, polarity, depth,
pin names, threshold). This gets the benefit of principle-driven selection
without the risk of generating structurally incorrect decks. The template
library shrinks from 457 to ~50-70 parameterized families.

**Caveat**: This recommendation depends on Task E results. If the 10
sampled templates reveal that templates within the same family differ in
unexpected structural ways (not just parameterizable differences), then
architecture (B) or a hybrid may be needed. Final decision after Task E
review.
