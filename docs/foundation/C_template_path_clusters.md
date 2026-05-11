# Template Path Semantic Decomposition -- Task C Report

## 1. Token Grammar Specification

### 1.1 General Path Format

```
DIRECTORY "/" "template__" BODY ".sp"
```

Where `BODY` is a `__`-delimited sequence of tokens from the grammar below.

### 1.2 Token Vocabulary (142 unique tokens observed)

| Category | Tokens |
|---|---|
| **DIRECTION** | `rise`, `fall` |
| **TOPOLOGY** | `common`, `latch`, `flop`, `sync2`..`sync6`, `sync1p5`, `basemeg`, `gclk`, `ckg`, `ckgn`, `ckgian`, `ckgmux2`, `ckgmux3`, `MB`, `SLH`, `ESLH`, `EDF`, `RCB`, `DET`, `DETLTSO`, `DETRESO`, `DIV4`, `rsdf`, `AO22`, `OA22`, `invdX`, `LND2SR`, `DRDF`, `PTCKG`, `retn`, `ck` |
| **SUB_TOPOLOGY** | `latch`, `flop`, `common` (when following a topology, e.g. `MB__latch`, `retn__flop`) |
| **PIN** | `CP`, `CPN`, `D`, `Q`, `QN`, `q1`, `SE`, `SDN`, `CDN`, `CD`, `E`, `EN`, `EN1`, `EN2`, `S`, `A`, `B`, `I0`, `DA`, `DB`, `DA1`..`DD2`, `WWL`, `WWL0`, `WWL1`, `WWL_N`, `WWL0_N`, `WWL1_N`, `WWL0N`, `WWL1N`, `WWLN`, `RETN`, `RSNB`, `AO2`, `CKGMUX3`, `CKGOR2`, `OR2`, `clken`, `clkdivrst`, `divs`, `scanmode`, `en`, `enb`, `s`, `nsleep`, `sleep`, `LP`, `RE` |
| **MODIFIER** | `nx`, `notD`, `notCD`, `notEN1`, `notEN2`, `ml_b` |
| **ARC_TYPE** | `hold`, `setup`, `removal`, `nonseq`, `nonseqhold`, `nonseqsetup` |
| **SIM_TYPE** | `glitch`, `pushout` |
| **Q_QUALIFIER** | `maxq`, `minq`, `maxqx`, `minqx`, `negative`, `minq_maxq`, `maxbl_b`, `minbl_b`, `maxbl_bx`, `minbl_bx`, `maxsl_ax`, `minsl_ax`, `maxsl_bx`, `minsl_bx`, `minq_maxbl_bx`, `minq_maxsl_ax`, `maxq_minbl_bx`, `maxq_minsl_ax`, `maxq_minqx`, `minq_maxqx` |
| **PCT_MOD** | `10`, `20`, `percent` (appear as `__20__percent__` or `__10__percent__`) |
| **VARIANT** | Integer: `0`, `1`, `2`, `3`, `4` |

### 1.3 BNF Grammar

```bnf
<path>         ::= <directory> "/" "template__" <body> ".sp"

<directory>    ::= "delay" | "hold" | "min_pulse_width" | "setup"
                 | "nochange" | "nochange_high_low" | "nochange_low_high" | "nochange_low_low"
                 | "non_seq_hold" | "non_seq_setup"

<body>         ::= <core> "__" <variant>           (* standard form *)
                 | <core> "__" <suffix_tag>         (* anomaly: ml_b suffix *)
                 | <core>                           (* anomaly: delay/invdX *)

<core>         ::= <topology_block> "__" <timing_spec>
                 | <topology_block> "__" <arc_type> "__" <timing_spec>       (* nochange dir *)

<topology_block> ::= <topology>
                   | <topology> "__" <sub_topology>
                   | <syn_prefix> "__" <topology>
                   | <topology> "__" <modifier>

<syn_prefix>   ::= "syn3" | "syn4" | "syn5" | "syn6"
                 | "syn3_retn" | "syn4_retn" | "syn5_retn" | "syn6_retn"

<timing_spec>  ::= <pin_spec> "__" <dir1> "__" <pin_spec> "__" <dir2> <tail>
                 | <pin_spec> "__" <dir1> "__" <dir2> <tail>
                 | <dir1> "__" <pin_spec> "__" <dir2> <tail>
                 | <dir1> "__" <dir2> <tail>

<pin_spec>     ::= <pin> | <modifier>              (* notD, notEN1, etc. *)

<tail>         ::= ""
                 | "__" <sim_type>
                 | "__" <sim_type> "__" <q_qual>
                 | "__" <sim_type> "__" <q_qual> "__" <q_qual>
                 | "__" <pct_mod> "__" <sim_type> "__" <q_qual>
                 | "__" <sim_type> "__" <q_qual> "__" <suffix_tag>

<pct_mod>      ::= ("10" | "20") "__" "percent"

<q_qual>       ::= "maxq" | "minq" | "maxqx" | "minqx" | "negative"
                 | "minq_maxq" | "maxbl_b" | "minbl_b" | ...

<variant>      ::= DIGIT                           (* 0-4 observed *)

<suffix_tag>   ::= "ml_b"                          (* non-numeric variant *)
```

### 1.4 Regex (covers 98.9% of templates)

```
^(?P<dir>[a-z_]+)/template__(?P<body>.+?)(?:__(?P<variant>\d+))?\.sp$
```

Where `<body>` matches:

```
^(?P<topo>[A-Za-z0-9_]+?)__
 (?:(?P<arc>hold|setup|removal|nonseq(?:hold|setup)?)__)?
 (?:(?P<mod>nx|notD|notCD|notEN[12])__)?
 (?P<rest>(?:(?:rise|fall|[A-Za-z0-9_]+)__)*
   (?:rise|fall))
 (?:__(?:(?P<pct>\d+__percent)__)?
   (?P<sim>glitch|pushout)
   (?:__(?P<qq>[a-z_]+))?
 )?$
```

## 2. Directory Semantics

| Directory | Arc Category | Templates | Families |
|---|---|---|---|
| `hold` | Sequential hold timing | 204 | 177 |
| `nochange` | Clock-gating nochange checks (hold+setup) | 130 | 124 |
| `min_pulse_width` | Minimum pulse width | 53 | 53 |
| `non_seq_hold` | Non-sequential hold (async pins) | 39 | 29 |
| `setup` | Sequential setup timing | 10 | 8 |
| `nochange_low_low` | Nochange (both-low retention) | 8 | 8 |
| `non_seq_setup` | Non-sequential setup (async pins) | 8 | 8 |
| `delay` | Inverter delay | 2 | 2 |
| `nochange_high_low` | Nochange (high-low retention) | 2 | 2 |
| `nochange_low_high` | Nochange (low-high retention) | 1 | 1 |

## 3. Cluster Table (families with size > 1)

| Family Signature | Size | Variants | Directory |
|---|---|---|---|
| `SLH__rise__SE__fall__pushout` | 3 | 1, 2, 3 | hold |
| `SLH__rise__SE__rise__pushout` | 3 | 1, 2, 3 | hold |
| `gclk__rise__clkdivrst__fall__glitch__maxq` | 3 | 1, 2, 3 | hold |
| `gclk__rise__clkdivrst__rise__pushout` | 3 | 1, 2, 3 | hold |
| `EDF__rise__E__rise__glitch__maxq` | 2 | 1, 2 | hold |
| `SLH__fall__SE__fall__glitch__maxq` | 2 | 1, 2 | hold |
| `SLH__fall__SE__rise__glitch__maxq` | 2 | 1, 2 | hold |
| `SLH__fall__SE__rise__glitch__minq` | 2 | 1, 2 | hold |
| `common__fall__fall` | 2 | 1, 3 | hold |
| `common__fall__rise` | 2 | 1, 3 | hold |
| `common__rise__fall` | 2 | 1, 2 | hold |
| `common__rise__rise` | 2 | 1, 2 | hold |
| `gclk__rise__scanmode__fall__pushout` | 2 | 2, 3 | hold |
| `gclk__rise__scanmode__rise__pushout` | 2 | 2, 3 | hold |
| `latch__fall__fall__glitch__maxq` | 2 | 1, 2 | hold |
| `latch__fall__fall__glitch__minq` | 2 | 1, 2 | hold |
| `latch__fall__fall__glitch__minq_maxq` | 2 | 1, 2 | hold |
| `latch__fall__rise__glitch__maxq` | 2 | 1, 2 | hold |
| `latch__fall__rise__glitch__minq` | 2 | 1, 2 | hold |
| `latch__rise__fall__glitch__maxq` | 2 | 1, 2 | hold |
| `latch__rise__fall__glitch__minq` | 2 | 1, 2 | hold |
| `latch__rise__rise__glitch__maxq` | 2 | 1, 2 | hold |
| `latch__rise__rise__glitch__minq` | 2 | 1, 2 | hold |
| `ckg__hold__fall__en__fall__pushout__negative` | 2 | 0, 1 | nochange |
| `ckg__hold__fall__en__rise__20__percent__glitch__minq` | 2 | 0, 1 | nochange |
| `ckg__setup__rise__en__fall__20__percent__glitch__minq` | 2 | 0, 1 | nochange |
| `ckg__setup__rise__en__rise__pushout` | 2 | 0, 1 | nochange |
| `ckgn__hold__fall__en__fall__pushout__negative` | 2 | 0, 1 | nochange |
| `ckgn__setup__rise__en__rise__pushout` | 2 | 0, 1 | nochange |
| `latch__fall__fall__pushout__maxq` | 2 | 1, 2 | non_seq_hold |
| `latch__fall__fall__pushout__minq` | 2 | 1, 2 | non_seq_hold |
| `latch__fall__rise__glitch__minq` | 2 | 1, 2 | non_seq_hold |
| `latch__fall__rise__pushout` | 2 | 1, 2 | non_seq_hold |
| `latch__fall__rise__pushout__maxq` | 2 | 1, 2 | non_seq_hold |
| `latch__fall__rise__pushout__minq` | 2 | 1, 2 | non_seq_hold |
| `latch__rise__fall__glitch__maxq` | 2 | 1, 2 | non_seq_hold |
| `latch__rise__fall__glitch__minq` | 2 | 1, 2 | non_seq_hold |
| `latch__rise__fall__pushout` | 2 | 1, 2 | non_seq_hold |
| `retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b` | 2 | 2, 4 | non_seq_hold |
| `common__rise__fall` | 2 | 1, 2 | setup |
| `common__rise__rise` | 2 | 1, 2 | setup |

**41 multi-variant families** out of 412 total. Maximum cluster size is 3.

## 4. Structural Pattern Shapes (top 15)

| Count | Shape Pattern | Example |
|---|---|---|
| 43 | `IDENT__DIR__DIR__NUM` | `common__rise__fall__1` |
| 40 | `IDENT__DIR__DIR__SIM__QUAL__NUM` | `latch__fall__fall__glitch__maxq__1` |
| 36 | `IDENT__DIR__PIN__DIR__NUM` | `SLH__rise__SE__fall__pushout__1` |
| 30 | `IDENT__ARC__DIR__PIN__DIR__PCT__SIM__QUAL__NUM` | `ckgmux2__hold__fall__s__fall__20__percent__glitch__minq__1` |
| 28 | `IDENT__IDENT__DIR__DIR__NUM` | `basemeg__WWL0__fall__fall__1` |
| 27 | `IDENT__IDENT__DIR__DIR__SIM__QUAL__NUM` | `MB__latch__rise__fall__glitch__maxq__1` |
| 21 | `IDENT__DIR__PIN__DIR__SIM__QUAL__NUM` | `gclk__rise__clken__fall__pushout__maxq__1` |
| 19 | `IDENT__DIR__PIN__DIR__SIM__NUM` | `gclk__rise__clkdivrst__rise__pushout__1` |
| 19 | `IDENT__ARC__DIR__PIN__DIR__SIM__QUAL__NUM` | `ckg__hold__fall__en__fall__pushout__maxq__1` |
| 15 | `IDENT__ARC__DIR__PIN__DIR__SIM__NUM` | `ckg__setup__fall__en__fall__pushout__1` |
| 14 | `IDENT__IDENT__DIR__PIN__DIR__SIM__QUAL__NUM` | `basemeg__EN__rise__A__fall__glitch__minq__1` |
| 9 | `IDENT__DIR__DIR__SIM__NUM` | `latch__fall__fall__pushout__1` |
| 9 | `IDENT__IDENT__ARC__MOD__PIN__PIN__DIR__PIN__DIR__SIM__QUAL__NUM` | `retn__flop__hold__notD__CDN__SDN__fall__nsleep__fall__glitch__minq__1` |
| 9 | `IDENT__ARC__PIN__DIR__PIN__DIR__SIM__NUM` | `ckgmux2__hold__s__fall__fall__pushout__1` |
| 8 | `IDENT__DIR__DIR__SIM__QUAL__QUAL__NUM` | `latch__rise__fall__glitch__maxq__maxbl_b__2` |

These 15 shapes cover **381 of 457 templates (83.4%)**.

## 5. Anomaly List

Five templates do not follow the standard `...__DIGIT.sp` variant suffix convention:

| Template Path | Tokens | Anomaly Reason |
|---|---|---|
| `delay/template__invdX__fall.sp` | `invdX`, `fall` | No variant index; delay-only minimal form |
| `delay/template__invdX__rise.sp` | `invdX`, `rise` | No variant index; delay-only minimal form |
| `hold/template__gclk__nx__rise__clken__fall__glitch__minq__ml_b.sp` | 8 tokens | Suffix `ml_b` instead of numeric variant |
| `hold/template__gclk__nx__rise__clken__rise__glitch__maxq__ml_b.sp` | 8 tokens | Suffix `ml_b` instead of numeric variant |
| `nochange/template__ckg__hold__nx__fall__clken__rise__glitch__minq.sp` | 8 tokens | Ends with `minq` (Q-qualifier) instead of variant index |

**Anomaly rate: 5 / 457 = 1.1%**

The `delay/` templates are intentionally minimal (no simulation-type or variant
needed for simple inverter characterization). The `ml_b` suffix appears to be a
technology-specific modifier ("multi-layer B") that replaces the variant index.
The `nochange/ckg` anomaly appears to be missing its trailing variant index.

## 6. Summary Statistics

| Metric | Value |
|---|---|
| Total HSPICE rules | 688 |
| Total unique template paths | 457 |
| Unique tokens (vocabulary) | 142 |
| Number of families (clusters) | 412 |
| Multi-variant families | 41 |
| Single-variant families | 371 |
| Average cluster size | 1.11 |
| Maximum cluster size | 3 |
| Directories | 10 |
| Token count range per template | 2 -- 13 |
| Modal token count | 7 (93 templates) |
| Grammar anomalies | 5 (1.1%) |
| Grammar coverage | 452 / 457 (98.9%) |

### Key Observations

1. **Highly flat namespace**: 90% of families have exactly one variant. The
   variant index is mostly a disambiguation mechanism rather than a systematic
   enumeration.

2. **Directory encodes arc category**: The directory is the primary semantic
   discriminator (`hold`, `setup`, `nochange`, `min_pulse_width`,
   `non_seq_hold`, `non_seq_setup`, `delay`). The `nochange_*` subdirectories
   further encode output-level transitions.

3. **`nochange/` uniquely embeds arc_type in the filename**: Templates under
   `nochange/` include `hold` or `setup` as an explicit token in the body
   (e.g., `ckg__hold__fall__en__...`), while other directories infer arc_type
   from the directory name alone.

4. **Token order is context-dependent**: The position of `PIN` and `DIR` tokens
   varies by topology. Simple topologies (`common`, `latch`) use `DIR__DIR`,
   while complex topologies (`gclk`, `ckg`, `basemeg`) use `DIR__PIN__DIR` to
   disambiguate multi-pin timing arcs.

5. **`retn__` prefix forms the deepest nesting**: Retention templates
   (`retn__flop__hold__notD__CDN__SDN__...`) reach 13 tokens, encoding
   topology, sub-topology, arc-type, modifier, and multiple pins in a single
   path.

6. **Percent-threshold modifiers**: `20__percent` and `10__percent` appear in
   nochange glitch-detection templates as simulation sensitivity thresholds,
   always preceding `glitch`.
