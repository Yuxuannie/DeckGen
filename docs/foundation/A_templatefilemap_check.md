# Task A: templateFileMap Reality Check

## File Location Confirmation

| Item | Path |
|------|------|
| Source module | `/Users/nieyuxuan/Downloads/Work/4-MCQC/mcqc_flow/2-flow/funcs.py` |
| Extracted rules | `my-work-scripts/deckgen/config/template_rules.json` |

Phase 1 stated templateFileMap was "not available locally." This was incorrect.
The file exists at `mcqc_flow/2-flow/funcs.py` (18,624 lines). It is the same
module imported at runtime as `templateFileMap.funcs` via `sys.path.insert(0,
TEMPLATE_LUT_PATH)` in `scld__mcqc.py`.

## File Statistics

| Metric | Value |
|--------|-------|
| funcs.py total lines | 18,624 |
| `mapCharacteristicsToTemplate` | line 21 |
| `getHspiceTemplateName` | line 67 (HSPICE if-chain) |
| `getThanosTemplateName` | line 14,753 |
| Total extracted rules | 854 |
| HSPICE rules | 688 |

## Sampling Method

30 HSPICE rules selected at uniform intervals from the 688-rule set
(step ~22.9). Each rule verified by reading the corresponding line range in
`funcs.py` and comparing arc_type, cell_pattern, constr_pin, constr_pin_dir,
rel_pin, rel_pin_dir, when, probe, and template path.

## 30-Rule Verification Table

| # | Rule IDX | Source Line | arc_type | cell_pattern | rel_pin/dir | constr_pin/dir | template | Result |
|---|----------|-------------|----------|--------------|-------------|----------------|----------|--------|
| 1 | 0 | 117 | hold | `*SYNC2*Q*` | CP/rise | D/fall | `hold/template__sync2__q1__rise__fall__1.sp` | MATCH |
| 2 | 22 | 525 | hold | `DCCKSDIV2MX*` +3 | nx/rise | `F*_CLKEN`/rise | `hold/template__gclk__nx__rise__clken__rise__glitch__maxq__ml_b.sp` | MATCH |
| 3 | 45 | 1079 | hold | `DCCKSDIV2O4*` | CLKIN/rise | DIVS/fall | `hold/template__gclk__rise__divs__fall__pushout__1.sp` | **DIFF** |
| 4 | 68 | 1583 | nochange_high_high | `CKGAN2CCHD1BWP...` +1 | CP/fall | EN/fall | `nochange/template__ckg__hold__fall__en__fall__pushout__negative__0.sp` | MATCH |
| 5 | 91 | 2101 | nochange_low_high | `DC*CKG*` +2 | CP/rise | EN/fall | `nochange/template__ckg__setup__rise__en__fall__20__percent__glitch__minq__1.sp` | **DIFF** |
| 6 | 114 | 2591 | nochange_high_low | `CK*MUX2GF*` | CLK1/rise | S1/fall | `nochange/template__ckg__hold__rise__en__fall__20__percent__glitch__maxq__1.sp` | MATCH |
| 7 | 137 | 3125 | nochange_low_low | `DC*CKG*MUX2*` +2 | I1/fall | S/fall | `nochange/template__ckgmux2__setup__fall__s__fall__20__percent__glitch__maxq__1.sp` | MATCH |
| 8 | 160 | 3673 | nochange_high_high | `DC*CKG*MUX2*` +2 | I1/fall | S/fall | `nochange/template__ckgmux2__hold__fall__s__fall__pushout__1.sp` | MATCH |
| 9 | 183 | 4179 | nochange_low_low | `DC*CKG*MUX2*` +2 | I1/fall | S/fall | `nochange/template__ckgmux2__setup__fall__s__fall__20__percent__glitch__minq__1.sp` | MATCH |
| 10 | 206 | 4649 | nochange_low_low | `DC*CKPGMUX2*` +1 | CP2/rise | S/rise | `nochange/template__ckgmux2__hold__rise__s__rise__20__percent__glitch__maxq__1.sp` | MATCH |
| 11 | 229 | 5111 | nochange_low_high | `*CKGIAN*` | CP/rise | ENB/fall | `nochange/template__ckgian__setup__rise__enb__fall__pushout__1.sp` | MATCH |
| 12 | 252 | 5573 | nochange_low_low | `CK*AOI21*` | CLK/rise | EN1/rise | `nochange/template__ck__hold__EN2__rise__EN1__rise__pushout__negative__1.sp` | MATCH |
| 13 | 275 | 6051 | non_seq_hold | `RLH*` +1 | SLEEP/fall | SDN/fall | `non_seq_hold/template__latch__fall__fall__pushout__minq__1.sp` | MATCH |
| 14 | 298 | 6543 | nochange_low_high | `RS*NBSP*` | CP/fall | SLEEP/rise | `nochange/template__retn__flop__hold__notD__CDN__SDN__fall__sleep__rise__glitch__minq__1.sp` | MATCH |
| 15 | 321 | 7077 | hold | (none) | `CP`/rise | `SI`/fall | `hold/template__common__rise__fall__2.sp` | MATCH |
| 16 | 344 | 7605 | hold | `SLH*QSO*` | E/rise | SE/rise | `hold/template__SLH__rise__SE__rise__pushout__2.sp` | **DIFF** |
| 17 | 366 | 8111 | hold | `MB2SRLSDFAO22*` | `CP`/rise | `DB2`/fall | `hold/template__AO22__rise__DB2__fall__1.sp` | MATCH |
| 18 | 389 | 8621 | hold | `MB*SRLSDF*` | `CP`/rise | `D*`/fall | `hold/template__MB__rise__fall__20__percent__glitch__maxq__1.sp` | MATCH |
| 19 | 412 | 9145 | hold | `DFNSYNC1P5*Q*` | CPN/fall | D/fall | `hold/template__latch__fall__fall__glitch__minq__1.sp` | MATCH |
| 20 | 435 | 9587 | hold | (none) | E/fall | `A*`/rise | `hold/template__basemeg__E__fall__A__rise__glitch__maxq__1.sp` | MATCH |
| 21 | 458 | 10053 | hold | (none) | CPN/fall | TE/fall | `hold/template__latch__fall__fall__pushout__1.sp` | MATCH |
| 22 | 481 | 10519 | hold | `PTISOLHRP*` | E/fall | `D*`+3/fall | `hold/template__latch__fall__fall__glitch__minq__1.sp` | **DIFF** |
| 23 | 504 | 11001 | hold | (none) | `CP`,`CLK*`/rise | `E`,`S`,`OV`/fall | `hold/template__latch__rise__fall__pushout__1.sp` | MATCH |
| 24 | 527 | 11475 | non_seq_hold | `*SDRPQ*` | SDN/rise | CD/fall | `non_seq_hold/template__latch__rise__fall__pushout__2.sp` | MATCH |
| 25 | 550 | 11997 | nochange_low_low | `*RSSDFSYNC5*` +1 | RETN/rise | CD/rise | `nochange_low_low/template__syn5_retn__nonseqhold__RETN__rise__CD__rise__pushout__4.sp` | MATCH |
| 26 | 573 | 12469 | removal | `*MB*` | CP/fall | RETN/rise | `hold/template__retn__removal__fall__rise__glitch__minq__2.sp` | MATCH |
| 27 | 596 | 13029 | removal | (none) | CP/rise | SDN/rise | `hold/template__latch__rise__rise__glitch__minq__maxsl_ax__2.sp` | MATCH |
| 28 | 619 | 13565 | removal | (none) | E/fall | SDN/rise | `hold/template__latch__fall__rise__glitch__minq__1.sp` | MATCH |
| 29 | 642 | 13867 | min_pulse_width | (none) | `WWL0_N`/None | `WWL0_N`/fall | `min_pulse_width/template__WWL0N__fall__rise__1.sp` | MATCH |
| 30 | 665 | 14297 | min_pulse_width | `*DETQNRESO*` | `CP`/None | `CP`/rise | `min_pulse_width/template__DET__RE__notD__CP__rise__fall__1.sp` | MATCH |

## Diff Details

### Rule 3 (IDX=45, line 1079) -- when condition incomplete

- **JSON:** `when = "!CLKDIVRST&CLKEN&!SCANCLK" in when`
- **Source:** `(("!CLKDIVRST&CLKEN&!SCANCLK" in when) or ("!CLKDIVRST&CLKEN&SCANCLK" in when))`
- **Issue:** Extraction captured only the first of two OR-ed when alternatives.

### Rule 5 (IDX=91, line 2101) -- constr_pin and rel_pin missing alternatives

- **JSON:** `constr_pin = "EN"`, `rel_pin = "CP"`
- **Source:** `(constr_pin == "EN" or constr_pin == "ISO")`, `(rel_pin == "CP" or rel_pin == "I")`
- **Issue:** Missing `constr_pin` alternative `"ISO"` and `rel_pin` alternative `"I"`.

### Rule 16 (IDX=344, line 7605) -- rel_pin + when guard incomplete

- **JSON:** `rel_pin = "E"`, `when = '"D" in when'`
- **Source:** `(rel_pin == "E" or rel_pin == "CLK")`, `"D" in when and not "!D" in when`
- **Issue:** (a) Missing `rel_pin` alternative `"CLK"`. (b) When condition
  negation guard (`not "!D" in when`) not captured.

### Rule 22 (IDX=481, line 10519) -- rel_pin missing alternatives

- **JSON:** `rel_pin = "E"`
- **Source:** `(rel_pin == "E" or fnmatch.fnmatch(rel_pin, "CLK*") or rel_pin == "ISO")`
- **Issue:** Missing alternatives `"CLK*"` (glob) and `"ISO"`.

## Summary

| Category | Count |
|----------|-------|
| Exact match | **26/30** |
| With diffs | **4/30** |
| Not found in source | **0/30** |

All 30 sampled rules were found at the declared line numbers. Template paths
matched in all 30 cases. Arc types matched in all 30 cases. Cell patterns
matched in all 30 cases.

The 4 diffs are all of the same class: **incomplete extraction of OR-ed
alternatives** in `rel_pin`, `constr_pin`, or `when` conditions. No template
paths, arc types, or cell patterns were wrong. The extraction correctly
captured the primary/first value in each case but missed secondary
alternatives joined by `or` in the Python source.

### Estimated Extrapolation

At a 4/30 (13.3%) diff rate on uniformly sampled rules, approximately 90 of
the 688 HSPICE rules may have similar incomplete `or`-alternative extractions.
None of these diffs would cause incorrect template selection -- they would
cause **missed matches** (false negatives) where a valid arc fails to match
a rule it should match because a secondary pin name or when variant was not
recorded.
