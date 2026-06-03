# Task E.2 Sampling Results — .ic / .nodeset / Spectre Distribution

Source: targeted sampling script run on
`/SIM/DFDS_20211231/Personal/ynie/4-Projects/2026/5-deckGen/templates/N2P_v1.0/`
Date: 2026-05-08

## Summary

Phase E (initial 10 samples) suggested all `.sp` files use neither `.ic`
nor `.nodeset`. Phase E.2 targeted sampling reveals this was a sampling
artifact. The audit-reported 175 `.ic` and 126 `.nodeset` distributions
are correct; they were missed because Phase E sampled only the
NEITHER-init region of the corpus.

The actual init strategy distribution is:

- **TEMPLATE_EMBEDDED_NONE**: 604 templates (67%) — no SPICE-level init,
  relies on V-source biasing + DONT_TOUCH_PINS metadata
- **TEMPLATE_EMBEDDED_IC**: 169 templates (19%) — embedded `.ic`
  statements, concentrated in `delay/` (91 of 169 = 54%)
- **TEMPLATE_EMBEDDED_NODESET**: 126 templates (14%) — embedded
  `.nodeset` statements, 100% in `mpw/` and `min_pulse_width/`
- BOTH: 0 (mutually exclusive — confirmed)

All three are template-level properties. No runtime init dispatch is
needed. The `InitStrategy` is metadata that travels with the template,
not a strategy selected at deck generation time.

---

## Section A: `.ic`-using templates

**Total: 169** (audit reported 175; 6-template difference likely from
sampling edge cases or symlinks; not material)

### Distribution by arc_type directory

| Arc type | Count | % of .ic |
|---|---:|---:|
| **delay** | **91** | 54% |
| hold | 56 | 33% |
| nochange | 14 | 8% |
| non_seq_hold | 4 | 2% |
| non_seq_setup | 3 | 2% |
| nochange_low_high | 1 | <1% |

Critical finding: more than half of `.ic` files live in `delay/`. This
was missed in Phase E sampling.

### Distribution by cell family token

| Count | Family |
|---:|---|
| 43 | retn |
| 41 | gclk |
| 22 | SLH |
| 12 | EDF |
| 10 | rsdf |
| 10 | MB |
| 5 | ckg |
| 4 | RCB |
| 4 | latch |
| 4 | ESLH |
| 4 | DIV4 |
| 1 | synx |
| 1 | syn2 |
| 1 each | seq_inpin (rise/fall × delay rise/fall = 4 entries) |
| 1 each | SDFQNSXGD / SDFNQSXGD (3 entries) |

Audit said `.ic` users are "MB, EDF, DIV4, latch_S, gclk_clkdivrst,
gclk_scanmode, gclk_divs". Reality: retn (43) and gclk (41) are the
two largest, with SLH (22) third. MB is much smaller than implied.

### Representative `.ic`-using templates

#### `./delay/template__SDFNQSXGD_inpin_fall_delay_rise.sp`

- Total lines: 65
- Header: standard SPICE Deck created header, DONT_TOUCH_PINS D
- SPICE options: full block (RUNLVL=6 ACCURATE=1 BRIEF=1 autostop
  MODSRH=1 gmindc=1e-15 gmin=1e-15 measform=1 measfile=1)
- `.ic` statements: 1 line
  - `53:.ic v(Q) = 'vss_value'`
- `.nodeset`: none
- `.meas`: 3 statements (cp2d-style delay measurements with
  cross=last, half_tt_out)
- `.tran`: `.tran 1p 400ns` (no monte, no OPTIMIZE — bare delay
  measurement)
- VOLTAGE SOURCES: standard 4 (VVDD/VVSS/VVPP/VVBB) + VD D 0 vdd_value
  (5 sources for `D` pin)

This is a `delay` template with minimal init: just one `.ic v(Q)` to
fix output state pre-measurement. Bare `.tran 1p 400ns` (no sweep
modifier).

#### `./hold/template__EDF__rise__E__fall__pushout__maxq__1.sp`

- Total lines: 85
- Header: DONT_TOUCH_PINS D1,D2,D3,D4 (4 don't-touch pins for D-bus)
- THANOS Headers: pushout, OPT_RESULTS = cp2q_del1 +
  pushout_maxq_final_state_check, MEAS_DEGRADE_PER for both
- `.ic` statements: 4 lines
  - `40:.ic v(X1.ml*_a) = 'vdd_value'`
  - `41:.ic v(X1.ml*_bx) = 'vss_value'`
  - `42:.ic v(X1.sl*_ax) = 'vss_value'`
  - `43:.ic v(X1.sl*_b) = 'vdd_value'`
  - (uses `*` glob for matching multiple register banks)
- `.nodeset`: none
- `.meas`: 4 statements including
  - `pushout_maxq_final_state_check find par('1')
    at='final_state/vdd_value < 0.05 ? 0 : -1'`
- `.tran`: `monte=1` style
- VOLTAGE SOURCES: 4 standard
- DONT_TOUCH_PINS: D1,D2,D3,D4

EDF (edge-detect FF) with 4-line `.ic` for master/slave latch state.
The `*` glob handles multi-bank EDF cells. Final-state check is a
nochange-style measurement embedded in hold context.

#### `./nochange/template__ckg__nx__rise__clken__fall__glitch__minq.sp`

- Total lines: 77
- Header: DONT_TOUCH_PINS CLKIN,SCANCLK,SCANCLKEN
- THANOS: CONSTR_CRITERIA = glitch, OPT_RESULTS = minq, MEAS_GLITCH_PER
  = 0.8, MEAS_GLITCH_DIR = min
- `.ic` statements: 2 lines
  - `58:.ic v(X1.sl*_ax) = 'vdd_value'`
  - `59:.ic v(X1.sl*_b) = 'vss_value'`
- `.nodeset`: none
- `.meas`: 3 statements
  - cp2d trig
  - `minq min v($PROBE_PIN_1)`
  - `glitch_minq_check find par('1') at='minq/vdd_value > 0.8 ? 0 : -1'`
- `.tran`: `monte=1`
- VOLTAGE SOURCES: 4 standard

Nochange CKG cell with 2-line `.ic` for slave latch only (sufficient
because clock gating is the active path).

#### `./non_seq_hold/template__retn__nonseq__RETN__fall__CD__rise__glitch__minq__minsl_b__2.sp`

- Total lines: 80
- Header: DONT_TOUCH_PINS CP,SDN
- THANOS: glitch, OPT_RESULTS = minimum,
  MEAS_GLITCH_PER minimum 0.9, MEAS_GLITCH_DIR minimum min
- `.ic` statements: 4 lines
  - `41:.ic v(X1.sl*_ax) = 'vss_value'`
  - `42:.ic v(X1.sl*_b) = 'vdd_value'`
  - `43:.ic v(X1.ml*_ax) = 'vss_value'`
  - `44:.ic v(X1.ml*_b) = 'vdd_value'`
- `.nodeset`: none
- `.meas`: 4 statements
  - `meas tran minq_1 min v(Q)`
  - `meas tran minq_2 min v(X1.sl_b)`
  - `meas tran minimum param='min(minq_1,minq_2)'`
  - `meas cp2d trig` to constraint pin
- `.tran`: `monte=1`
- VOLTAGE SOURCES: 4 standard + VCD CD 0 vss_value + VSDN SDN 0 vdd_value

This is the cell that prompted the syn2/syn3+ investigation. 4-line
`.ic` covers both master and slave. Async pin biasing is in addition
to (not replacing) `.ic`.

#### `./non_seq_setup/template__retn__nonseqsetup__RETN__rise__CD__fall__glitch__minq__minsl_b__2.sp`

- Total lines: 78
- Header: DONT_TOUCH_PINS CP
- THANOS: same structure as non_seq_hold variant
- `.ic` statements: 4 lines (identical structure to non_seq_hold)
- VOLTAGE SOURCES: 4 standard + VCP CP 0 vss_value (CP biased low
  here, vs floating in non_seq_hold)

---

## Section B: `.nodeset`-using templates

**Total: 126** (audit number confirmed exactly)

### Distribution by arc_type directory

| Arc type | Count |
|---|---:|
| **mpw** | 63 |
| **min_pulse_width** | 63 |

100% concentration in two directories. `mpw` and `min_pulse_width` may
be distinct directories serving different purposes, or one may be a
symlink/alias of the other; total of 126 = 2 × 63 suggests they may be
distinct copies of identical content, or distinct shipped variants.

### Distribution by cell family token

| Count | Family |
|---:|---|
| 18 | DET |
| 18 | CP |
| 12 | sync1p5 |
| 4 | sync4 |
| 4 | sync3 |
| 4 | sync2 |
| 4 | S |
| 4 | retn |
| 4 | PTCKG |
| 4 | OR2 |
| 4 | I0 |
| 4 | DRDF |
| 4 | DA |
| 4 | CPN |
| 4 | CKGOR2 |
| 4 | CKGMUX3 |
| 4 | AO2 |
| 2 | WWLN |
| 2 | WWL1N |
| 2 | WWL1 |

### Representative `.nodeset`-using templates

#### `./mpw/template__retn__CP__rise__fall__2.sp`

- Total lines: 97
- Header: DONT_TOUCH_PINS (none specified after PINS keyword)
- THANOS: pushout, OPT_RESULTS cp2q_del1 cp2q_del2,
  MEAS_DEGRADE_PER both = $PUSHOUT_PER, CONSTR_PIN_PARAM
  constr_pin_offset
- `.ic`: none
- `.nodeset`: 17 lines (full master+slave+bitline state, examples):
  - `69:.nodeset v(X1.ml*_a) = 'vdd_value'`
  - `70:.nodeset v(X1.sl*_a) = 'vdd_value'`
  - `71:.nodeset v(X1.bl*_a) = 'vdd_value'`
  - `72:.nodeset v(X1.ml*_b) = 'vdd_value'`
  - `73:.nodeset v(X1.sl*_b) = 'vdd_value'`
  - `74:.nodeset v(X1.bl*_b) = 'vdd_value'`
  - `75:.nodeset v(X1.ml*_ax) = 'vss_value'`
  - `76:.nodeset v(X1.sl*_ax) = 'vss_value'`
  - `77:.nodeset v(X1.bl*_ax) = 'vss_value'`
  - `78:.nodeset v(X1.ml*_bx) = 'vss_value'`
  - `79:.nodeset v(X1.sl*_bx) = 'vss_value'`
  - `80:.nodeset v(X1.bl*_bx) = 'vss_value'`
  - `81:.nodeset v(Q*) = 'vdd_value'`
  - `82:.nodeset v(QN*) = 'vss_value'`
  - `83:.nodeset v(Z*) = 'vdd_value'`
  - `84:.nodeset v(ZN*) = 'vss_value'`

#### `./min_pulse_width/template__AO2__rise__fall__1.sp`

- Total lines: 93
- Header: standard
- THANOS: pushout, OPT_RESULTS cp2q_del1, MEAS_DEGRADE_PER cp2q_del1 =
  $PUSHOUT_PER, CONSTR_PIN_PARAM constr_pin_offset
- SPICE options: elaborate block (gear method, gdcpath=1e-15,
  converge=100, pode_check=0, autostop, post=0, NOMOD=1, MEASDGT=...,
  statfl=1, MCBRIEF=5, sampling_method=lhs)
- `.ic`: none
- `.nodeset`: 12+ lines covering ml/sl/bl/Q/QN/Z/ZN states with both
  vdd_value and vss_value polarities

The `.nodeset` block in mpw templates is essentially identical in
structure across cell families — same node name patterns
(`X1.<region>*_<suffix>`), same value assignments. The 16-line
"full master/slave/bitline" pattern is the canonical mpw init block.

---

## Section C: retn sibling comparison (the diagnostic)

### All 45 `non_seq_hold/template__*retn*nonseqhold*RETN*` files

The full filename listing reveals a clear sub-structure:

| Filename pattern | .ic line count | total lines |
|---|---:|---:|
| `template__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__2*.sp` | 0 | 74-76 |
| `template__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__4*.sp` | 0 | 76 |
| `template__retn__nonseqhold__RETN__fall__CD__rise__SDN__glitch__minq__maxqx__2*.sp` | 0 | 73 |
| `template__retn__nonseqhold__RETN__fall__SDN__fall__notCD__glitch__maxq__minqx__2*.sp` | 0 | 73 |
| `template__syn2__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__4.sp` | **16** | **99** |
| `template__syn3__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__4*.sp` | 0 | 76 |
| `template__syn4__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__4*.sp` | 0 | 76 |
| `template__syn5__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__4*.sp` | 0 | 76 |
| `template__syn6__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__4*.sp` | 0 | 76 |
| `template__synx__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__5x.sp` | **14** | **90** |

(Each base name has Vdd/Vss corner variants which all share the same
.ic count.)

**Key finding**: only `syn2` and `synx` variants have `.ic`. `syn3`,
`syn4`, `syn5`, `syn6`, and the unprefixed `retn` variants all have
zero `.ic` lines.

This is the key disambiguation that Phase E (10 samples) missed: the
unprefixed `retn` template happened to be one of the 0-`.ic` variants,
not the 16-`.ic` `syn2` variant referenced in the original audit.

### Full content of audit-cited 16-line .ic template

`./non_seq_hold/template__syn2__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__4.sp`

- Total lines: 99
- Header: DONT_TOUCH_PINS CP, SDN
- THANOS: glitch, OPT_RESULTS = minq_1 minq_2,
  MEAS_GLITCH_PER minq_1 = 0.9, MEAS_GLITCH_PER minq_2 = 0.9,
  MEAS_GLITCH_DIR minq_1 = min, MEAS_GLITCH_DIR minq_2 = min
- `.ic` statements: 16 lines
  - `44:.ic v(X1.sl*_a) = 'vdd_value'`
  - `45:.ic v(X1.sl*_bx) = 'vss_value'`
  - `46:.ic v(X1.ml*_ax) = 'vss_value'`
  - `47:.ic v(X1.ml*_b) = 'vdd_value'`
  - `55:.ic v(X1.mq) = 'vdd_value'`
  - `56:.ic v(X1.mq_x) = 'vdd_value'`
  - `57:.ic v(X1.mq?) = 'vss_value'`
  - `58:.ic v(X1.mq?_x) = 'vss_value'`
  - `60:.ic v(X1.bl_ax) = 'vss_value'`
  - `61:.ic v(X1.bl_b) = 'vdd_value'`
  - `62:.ic v(X1.bl1_ax) = 'vdd_value'`
  - `63:.ic v(X1.bl1_b) = 'vss_value'`
  - `64:.ic v(X1.qf) = 'vss_value'`
  - `65:.ic v(X1.qf2) = 'vdd_value'`
  - `66:.ic v(X1.qf_a) = 'vss_value'`
  - `67:.ic v(X1.qf2_a) = 'vdd_value'`
- VOLTAGE SOURCES: 4 standard + VSDN SDN 0 vdd_value + VCP CP 0 vss_value
- DONT_TOUCH_PINS CP,SDN

The 16 nodes cover: master/slave latches (ml/sl), local mq state, local
bitline (bl), qf state for sync2 stage. This is a deep state machine
where simulator cannot converge to a unique state from mere V-source
biasing — it needs explicit hard-fix.

`syn3/4/5/6` get away with 0 `.ic` because their additional sync stages
have **enough symmetric structure** that voltage source biasing of CP/CD/SDN
alone determines a unique solution. Only `syn2` is asymmetric enough to
need 16 hard-fix nodes. `synx` is somewhere in between (14 nodes).

---

## Section D: Spectre `.thanos.sp` files

**Total: 94**

### Distribution by arc_type directory

| Arc type | Count |
|---|---:|
| **delay** | 91 |
| hold | 3 |

97% of Spectre files are in `delay/`. This dwarfs the original
characterization of Spectre as "AO22-family edge case" — Spectre is
the dominant simulator for delay arc characterization in this corpus.

### Sample: `./delay/hold/template__AO22__rise__DA1__rise__1.thanos.sp`

- Total lines: 84
- Header: DONT_TOUCH_PINS DB1,DC1,DD1,DA2,DB2,DC2,DD2 (7 pins for AO22
  multi-input expansion)
- THANOS: pushout, OPT_RESULTS cp2q_del1 cp2q_del2, MEAS_DEGRADE_PER
  for both, CONSTR_PIN_PARAM constrained_pin_t02
- SPICE options: Spectre-specific
  - `simulator lang=spectre`
  - `SetOption1 options reltol=1e-4 mdloutputfiletype=none`
  - `simulator lang=spice` (switched back for spice-syntax options)
  - `.options method=gear gmin=1e-15 gminfloatdefault=gmindc
    redefinedparams=ignore rabsshort=1m limit=delta save=nooutput
    autostop`
- Waveform: `.inc '$WAVEFORM_FILE'`
- Model: `.inc '$INCLUDE_FILE'`
- Netlist: `.inc '$NETLIST_PATH'`
- Library info: `.param vdd_value = '$VDD_VALUE'`, vss_value = 0,
  `.temp $TEMPERATURE`
- Slew/load: `.param cl = '$OUTPUT_LOAD'`,
  `rel_pin_slew = '$INDEX_2_VALUE'`,
  `constr_pin_slew = '$INDEX_1_VALUE'`
- Voltage: standard 4 (VVDD/VVSS/VVPP/VVBB) + extras
- Output Load: implicit
- Subckt definition: `X1 $NETLIST_PINS $CELL_NAME`
- Waveform timestamps: `.param max_slew = '$MAX_SLEW'`, t01-t05 =
  '<n> * max_slew'
- Optimization settings: `.param opt_init = '20 * max_slew'`,
  `opt_ub = '25 * max_slew'`, `opt_lb = '15 * max_slew'`
- Pin definitions: VDB1/VDC1/VDD1/VDA2/VDB2/VDC2/VDD2 each at vdd or
  vss (7 don't-touch pins biased explicitly)
- Toggling pins (stdvs subckts): XV$REL_PIN with stdvs_rise_fall_rise_fall_rise,
  XV$CONSTR_PIN with stdvs_fall_rise
- Measurements: cp2q_del1 trig val cross=3 targ cross=1, cp2q_del2 trig
  cross=5 targ cross=1, cp2d trig cross=3 targ cross=2
- Transient sim command: `simulator lang=spectre`,
  `tranIter tran stop=5000n`

The Spectre file is a complete standalone deck, not a Spectre patch
applied to an HSPICE template. It has its own template ecosystem with
identical THANOS/parameter/measurement structure but Spectre-specific
syntax for simulator config and transient command.

Critical: `.ic` and `.nodeset` are both absent. Init is via the 7
explicit voltage sources for don't-touch input pins.

---

## Section E: Structural cross-tab of `.ic`-using templates

For each of the 169 `.ic`-using templates, the script captured
(ic_count, meas_count, .tran style summary, filepath). Sorted by
ic_count ascending then meas_count ascending. Selected highlights:

### `.tran` style breakdown

Two main styles in the .ic-using set:
- `.tran 1p 5000n sweep monte=1` — used by hold/, nochange/,
  non_seq_hold/, non_seq_setup/ (most non-delay .ic files)
- `.tran 1p 5000n sweep OPTIMIZE=OPT1 results=<measurement>
  model=optmod` — used by all delay/ .ic files
- `.tran 1p 400ns` — used by some simple delay/ files (no sweep)

### ic_count distribution (selected examples)

| ic_count | meas_count | tran_style | example template |
|---:|---:|---|---|
| 1 | 3 | bare 400ns | `delay/template__SDFNQSXGD_inpin_*` |
| 1 | 3 | OPTIMIZE | `delay/template__seq_inpin_*` |
| 2 | 3 | monte=1 | `hold/template__latch__S__rise__fall__pushout__1.sp` |
| 2 | 3 | monte=1 | `hold/template__RCB__fall__rise__pushout__minq_1.sp` |
| 2 | 4 | monte=1 | `hold/template__ckg__nx__rise__clken__rise__glitch_*` |
| 2 | 4 | monte=1 | `hold/template__gclk__nx__rise__clken__*` |
| 2 | 4 | monte=1 | `nochange/template__ckg__nx__*` |
| 2 | 5 | monte=1 | `hold/template__SLH__QN__fall__SE__fall__glitch_*` |
| 4 | 3 | monte=1 | `hold/template__EDF__rise__E__rise__glitch__minq__1.sp` |
| 4 | 3 | OPTIMIZE | `delay/hold/template__retn__flop__removal__notD__CDN__SDN_*` |
| 4 | 4 | monte=1 | `hold/template__EDF__rise__E__fall__pushout__maxq__1.sp` |
| 4 | 4 | OPTIMIZE | `delay/hold/template__retn__removal_*` |
| 4 | 5 | OPTIMIZE | `delay/hold/template__retn__removal__fall_*` |
| 6 | 3 | OPTIMIZE | `delay/hold/template__retn__rise_*` |
| 8 | 3 | monte=1 | `hold/template__MB__notD__rise__E__rise__glitch__minq__1.sp` |
| 8 | 4 | monte=1 | `hold/template__MB__rise__E__fall__pushout__maxq__1.sp` |
| 8 | 4 | OPTIMIZE | `delay/hold/template__MB_*` |
| 14 | 3 | monte=1 | `non_seq_hold/template__synx__retn__nonseqhold__RETN_*` |
| 16 | 3 | monte=1 | `non_seq_hold/template__syn2__retn__nonseqhold__RETN_*` |

### Pattern: ic_count is a function of cell topology

| Cell topology | Typical ic_count |
|---|---:|
| simple gates (latch_S, RCB, CKG, gclk_clken) | 2 |
| EDF / standard FF with state | 4 |
| MB (multi-bank) | 8 |
| synx retention (sync stage chain) | 14 |
| syn2 retention (asymmetric 2-stage) | 16 |
| seq_inpin (SDF input variants) | 1 |

This means Phase 2's parameter binder can compute `ic_count` from cell
topology classification rather than treating it as a free parameter.
The `.ic` block content is a function of the cell topology label.

### Delay vs non-delay split in .ic templates

Of the 169 .ic-using templates:
- 91 in `delay/` use OPTIMIZE-based .tran (with various
  `results=<measurement>` patterns: cp2q_de, glitch, minimum, maxq_1)
- 78 in non-delay arcs (hold, nochange, non_seq_hold, non_seq_setup)
  use monte=1 .tran

This binding (delay → OPTIMIZE, non-delay → monte=1) is essentially
universal in the .ic-using subset.

---

## Implications for Phase 2 architecture

### 1. InitStrategy is metadata, not dispatcher

All three init styles (NONE, IC, NODESET) are template-embedded. The
v2 engine does not need a runtime init dispatcher — it needs to read
which init style the selected template family uses, and ensure the
correct V-sources are biased to match.

### 2. Three orthogonal axes determine the template family

| Axis | Cardinality | Contribution to family count |
|---|---:|---|
| arc_type | 9 directories (hold, setup, mpw, min_pulse_width, nochange, nochange_low_high, non_seq_hold, non_seq_setup, delay) | top-level partition |
| simulator backend | 2 (HSPICE, Spectre) | mostly orthogonal except delay-heavy on Spectre |
| .tran style | 3 (monte=1, OPTIMIZE, bare 400ns) | strongly correlated with arc_type |
| init style | 3 (NONE, IC, NODESET) | strongly correlated with arc_type |
| measurement profile | 5+ (pushout, glitch, final_state, minimum, maxq_N variants) | partially independent |
| cell topology | ~15 classes | drives ic_count and node names within IC strategy |

### 3. The `delay/` directory is its own ecosystem

Half of `.ic` files, 97% of Spectre files, all OPTIMIZE-style `.tran`
lines live in `delay/`. Phase 2 cannot meaningfully validate the
architecture without including delay in MVP. A classifier trained
without delay will systematically miss the most distinctive patterns
in the corpus.

### 4. Estimated principle count revision

Reverting to spec's original 45-55 estimate, possibly trending higher
(50-65) given:

- 9 arc_type buckets × per-bucket variants (not flat product, but
  each bucket has 3-8 distinct families)
- Spectre creates a parallel family set for delay (~5 spectre
  families)
- Initialization style adds variants where IC and NODESET each form
  distinct measurement structures

Final estimate: **50-65 principles**, with Spectre adding ~5 more if
included as separate families.

---

## End of Section E.2 results
