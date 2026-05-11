# B Audit: D5 Gap and D3 "unknown" Arc Type

## D5 Numbering Gap

### Finding: Formatting error, not data omission.

Re-deriving the top discriminating groups by num_templates descending:

| Rank | Signature | Rules | Templates |
|------|-----------|------:|----------:|
| D1 | (hold, CP, rise, rise, len_1) | 34 | 30 |
| D2 | (hold, CP, rise, fall, len_1) | 33 | 29 |
| D3 | (unknown, [], null, null, none) | 16 | 16 |
| D4 | (min_pulse_width, CP, null, rise, none) | 10 | 10 |
| **D5** | **(min_pulse_width, CP, null, fall, none)** | **9** | **9** |
| D6 | (nochange_high_high, CP, rise, rise, none) | 8 | 8 |
| D7 | (nochange_high_high, CP, fall, fall, none) | 8 | 8 |
| D8 | (hold, E, fall, rise, none) | 8 | 7 |
| D9 | (nochange_low_high, CP, rise, fall, none) | 6 | 6 |
| D10 | (nochange_low_high, CP, fall, rise, none) | 6 | 6 |

D5 is the min_pulse_width / CP / fall complement of D4 (rise). The Task B
narrative described D4 in detail, then stated "D5: Mirror of D4 for
constr_pin_dir=fall" but labeled the next section D6, creating the visual
gap. The data was present; only the heading numbering was skipped.

**Correction**: The D5 label was mentioned in the narrative text but the
heading jumped from D4 to D6. No data was omitted.

---

## D3 "unknown" Arc Type

### Finding: Extraction pipeline artifact, not genuinely missing arc_type.

The `template_rules.json` contains **37 rules** with `arc_type: "unknown"`
(not 16 as stated in the Task B narrative -- 16 was one signature subgroup
using coarser probe abstraction).

### What these rules actually are

All 37 rules have `arc_type` explicitly set to `"unknown"` in the JSON.
The `arc_type` key exists in every rule (it is not missing). The value
`"unknown"` was inserted by the extraction pipeline when it could not
determine the arc type from the source code structure.

### Source code investigation

These rules come from sections of `getHspiceTemplateName` (in
`mcqc_flow/2-flow/funcs.py`) where the arc_type is not tested as an
explicit condition. Instead, the code branches on cell_pattern and/or
pin names without first checking arc_type. The extraction script, which
expects `arc_type ==` conditions, defaults to `"unknown"` when none is
found.

### Breakdown by actual category

| True category | Rules | Source lines | Template directory | Evidence |
|---------------|------:|-------------|--------------------|----------|
| gclk hold | 4 | 369-471 | hold/, nochange/ | Templates named `gclk__*`, `ckg__*` |
| nochange (ckg) | 6 | 393-471 | nochange/ | Templates named `ckg__setup__*`, `ckg__hold__*` |
| retention nochange | 5 | 12331-12379 | nochange_low_low/, nochange_high_low/ | Templates named `retn__nonseqhold__*` |
| retention removal | 2 | 12401-12409 | hold/ | Templates named `retn__removal__*` |
| CKLH hold | 1 | 12555 | hold/ | Template named `latch__fall__fall__*` |
| SYNC mpw | 10 | 13677-13787 | min_pulse_width/ | Templates named `sync2-6__CP__*`, `CP__sync2-6__D__*` |
| sync1p5 mpw | 4 | 13713-13748 | min_pulse_width/ | Templates named `sync1p5__*` |
| DRDF mpw | 2 | 14197-14223 | min_pulse_width/ | Templates named `DRDF__CP__*` |
| DET mpw | 1 | 14407 | min_pulse_width/ | Template named `DET__CP__*` |
| gclk hold (clkdivrst) | 2 | 723-751 | hold/ | Templates named `gclk__rise__clkdivrst__*` |
| **Total** | **37** | | | |

### Root cause

The extraction script (which produced `template_rules.json` from the
18K-line if-chain) uses a pattern-matching approach to identify arc_type
conditions. In the source code, these 37 rules appear in sections where:

1. The enclosing `if` block checks cell_pattern or pin names but not arc_type
2. The arc_type is implicit from context (e.g., all rules after line 13677
   are in the min_pulse_width section of the function, but the function
   does not re-test `arc_type == "min_pulse_width"` for each sub-block)
3. The extraction script assigns `"unknown"` when it cannot find an explicit
   `arc_type ==` condition in the enclosing block

### Impact assessment

- **No incorrect template selection**: The `"unknown"` rules still have
  correct cell_pattern, pin, direction, and template path values. Only the
  arc_type label is wrong.
- **Match rate affected**: `core/template_rules.py` in DeckGen filters on
  arc_type first. Rules with `arc_type: "unknown"` will never match any
  real arc query, creating 37 false negatives (5.4% of 688 rules).
- **Affected cells**: SYNC2-6 (mpw), DRDF (mpw), DET (mpw), sync1p5 (mpw),
  CKLH (hold), retention (nochange/removal), gclk (hold/nochange)

### Proposed fix (not applied)

In `template_rules.json`, replace the `arc_type: "unknown"` values with
the correct arc types derived from the template directory prefix:

```
Lines 369-471:    "unknown" -> infer from template path (hold or nochange)
Lines 723-751:    "unknown" -> "hold"
Lines 12331-12379: "unknown" -> infer from template path (nochange_low_low or nochange_high_low)
Lines 12401-12409: "unknown" -> "removal"
Lines 12555:       "unknown" -> "hold"
Lines 13677-13787: "unknown" -> "min_pulse_width"
Lines 13713-13748: "unknown" -> "min_pulse_width"
Lines 14197-14223: "unknown" -> "min_pulse_width"
Lines 14407:       "unknown" -> "min_pulse_width"
```

This fix should be applied in Phase 2 when the rule engine is refactored.
It is a data fix, not a logic change.

### Other affected rules

A broader scan for extraction quality: beyond the 37 `unknown` rules, Task A
found 4/30 (13.3%) sampled rules with incomplete OR-alternative extraction.
These are separate issues (OR-alternatives affect pin matching, not arc_type).
No other arc_type values appear suspect -- all non-"unknown" values
correspond to valid Liberate arc types.
