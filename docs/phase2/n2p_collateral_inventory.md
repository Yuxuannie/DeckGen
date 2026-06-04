# N2P_v1.0 Collateral Inspection Reference

This document captures the structural facts about the `N2P_v1.0/` collateral
that were discovered by the second-pass inspection script (May 2026). It is
the source of truth for cell-name parsing, sub-library layout, and corner
discovery used by the DeckGen Phase 2B fixture-generation pipeline.

Inspection was performed against the live collateral on the TSMC server
(`f15eods2a.tsmc.com`). Output is captured here so future development on
the MacBook (or any host without server access) does not need to re-scan.

## 1. Sub-library layout

```
N2P_v1.0/
+-- tcbn02p_bwph130nppnl3p48cpd_base_elvt_c221227_400i/
+-- tcbn02p_bwph130nppnl3p48cpd_base_svt_c221227_400i/
+-- tcbn02p_bwph130pnnpl3p48cpd_base_elvt_c221227_400i/
+-- tcbn02p_bwph130pnnpl3p48cpd_base_svt_c221227_400i/
+-- tcbn02p_bwph130pnpnl3p48cpd_base_elvt_c221227_400i/
+-- tcbn02p_bwph130pnpnl3p48cpd_base_svt/                 (legacy / mirror)
+-- tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i/
+-- tcbn02p_bwph130pnpnl3p48cpd_mb_elvt_c221227_400i/     <- multi-bank
+-- tcbn02p_bwph130pnpnl3p48cpd_mb_svt_c221227_400i/
+-- tcbn02p_bwph130pnpnl3p48cpd_pm_elvt_c221227_400i/     <- power management
+-- tcbn02p_bwph130pnpnl3p48cpd_pm_svt_c221227_400i/
+-- tcbn02p_bwph130pnpnl3p48cpd_psw_lvt_c221227_400i/     <- power switch
+-- tcbn02p_bwph130pnpnl3p48cpd_psw_svt_c221227_400i/
+-- tcbn02p_bwph130ppnnl3p48cpd_base_elvt_c221227_400i/
+-- tcbn02p_bwph130ppnnl3p48cpd_base_svt_c221227_400i/
```

Key observations:
- Four tracks: `NPPN`, `PNNP`, `PNPN`, `PPNN`.
- Only the `PNPN` track has the full sub-library set
  (`base`, `mb`, `pm`, `psw`). The other three tracks ship `base` only.
- Three VT flavors appear in directory names: `svt` (no suffix on cell
  filenames), `elvt`, `lvt`. `lvt` only occurs in `psw_lvt`.

## 2. Cell-name structure

Decoded pattern (filename, less the `.spi` extension):

```
<FUNC><DRIVE_OPT>MZD<STRENGTH>BWP130H<TRACK>3P48CPD[<VT>]
                                                  L "" (SVT) | ELVT | LVT
                                            L NPPN | PNNP | PNPN | PPNN
                                  L library family marker (constant 'BWP130H...3P48CPD')
                  L M1 | MD | MDL | MDLI | MDLILLKG | M1LIDH | ...
       L AIOI21 / AOI21 / AN2 / DFQ / MB2SRLSDFQ / LHCNQ / SDFSYNC1Q / ISOCHSNK / HDR27 / ...
```

Regex (anchored, terminator-agnostic since extension is stripped before match):

```
^([A-Z][A-Z0-9]+?)(M[A-Z0-9]+)?MZD(\d+P?\d*)BWP130H(NPPN|PNNP|PNPN|PPNN)3P48CPD(ELVT|LVT)?$
```

Drive-strength field `MZD<n>`:
- PNPN track ships sub-unit and low drives: `0P7`, `0P8`, `1`, `2`, `4`.
- NPPN/PNNP/PPNN tracks ship higher drives: `3`, `6`, `9`, `12`, `15`, `21`.
- Drives appear track-specialized; do not assume a drive seen in one track
  exists in another.

## 3. Cell prefix frequency (Top 30, across all Netlist .spi files)

Pure combinational logic dominates the library.

```
 997  OAI
 989  AOI
 677  NR
 658  ND
 385  AN
 373  INR
 354  IND
 350  FILL
 337  BUFFSR
 297  OR
 207  MUX
 192  CKNM
 192  CKBM
 168  DCCKNM
 150  INVM
 124  XOR
 120  DCCKBM
 114  OA
 114  MB
 114  AO
 109  XNR
  99  IOA
  94  BUFFSKRM
  88  BUFFM
  78  IAO
  64  INVSKRM
  64  INVSKFM
  64  BUFFSKFM
  61  FA
  59  IIND
```

Sequential cell counts confirmed by relaxed-regex match:
- FF / DFF / D-flop: 150 unique
- Latch: 42 unique
- Multi-bank (MB): 114 unique
- Sync (SYNC / SYN<n>): 24 unique
- Retention (RSDF / RETN / RET): 24 unique
- Scan-latch (SLH / SDLH / SCAN*LAT): **0 matches**
- Clock gater (CKG / GATE / CLKG): 0 matches by that regex
  (clock-related cells appear under `CKNM` / `CKBM` / `DCCKNM` / `DCCKBM`
  prefixes instead - this is a naming-only mismatch, not a coverage gap)

## 4. MVP family selection (Phase 2B Tier-1 fixtures)

All cells locked to **PNPN track, SVT, drive MZD0P7** (minimum-drive)
for byte-equal fixture generation. Multi-track and multi-VT are deferred
to Tier-2.

| Slot     | Cell name                                              | Sub-library                                              |
|----------|--------------------------------------------------------|----------------------------------------------------------|
| common   | `AIOI21MDLIMZD0P7BWP130HPNPN3P48CPD`                   | `tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i`      |
| latch    | `LHCNQMZD1BWP130HPNPN3P48CPD`                          | `tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i`      |
| mb       | `MB2SRLSDFQSXGZ1111MZD1BWP130HPNPN3P48CPD`             | `tcbn02p_bwph130pnpnl3p48cpd_mb_svt_c221227_400i`        |
| sync     | `SDFSYNC1QSXGMZD1BWP130HPNPN3P48CPD`                   | `tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i`      |
| mpw      | `DFQSXG0MZD1BWP130HPNPN3P48CPD`                        | `tcbn02p_bwph130pnpnl3p48cpd_base_svt_c221227_400i`      |

Note: tests/test_aioi21_ground_truth.py uses a different AIOI21 variant
(AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD) as its anchor cell. That is
intentional and independent of the Tier-1 byte-equal matrix above.

Notes on slot selection:
- `common` uses `MZD0P7` (sub-unit drive) per Yuxuan's confirmation. This
  matches the minimum drive available for AIOI21 in PNPN. The `LHCNQ`,
  `MB`, `SDFSYNC`, and `DFQ` slots use `MZD1` because `MZD0P7` is not
  consistently available for those families - verify on server during
  baseline generation and fail loud if a slot's path is missing.
- The `sync` slot replaces what the Phase 2A spec called `SLH` (scan
  latch). N2P ships zero `SLH` / `SDLH` / `SCAN*LAT` cells. `SDFSYNC1Q`
  preserves the same architectural axes (scan-init, SE pin constraints,
  Q polarity, recovery/removal arcs). The `latch` slot (`LHCNQ`)
  separately covers transparent-vs-opaque state behavior.

## 5. Corner discovery

### LPE (parasitic-extracted netlist) corners actually present

From `Netlist/LPE_*` subdirectory scan:

```
LPE_cbest_CCbest_T_125c
```

Only one LPE corner is currently materialized in this collateral.
Additional corners (notably `LPE_ssgnp_cworst_CCworst_T_0c` and low-Vdd
slow corners) are expected to land later. The fixture infrastructure
must accept a list of corners and gracefully skip with a loud warning
if an `LPE_<corner>` directory is absent - never silently fall through.

### Characterized corners (from `char.tcl` filenames)

These exist as characterization recipes even if their LPE parasitics are
not yet generated:

```
ccs_ffgnp_1p155v_125c_cbest_CCbest_T
ccs_ffgnp_1p155v_125c_cbest_CCbest_T_ccsp
ccs_ssgnp_0p475v_0c_cworst_CCworst_T
ccs_ssgnp_0p475v_0c_cworst_CCworst_T_ccsp
ccs_ssgnp_0p515v_0c_cworst_CCworst_T
ccs_ssgnp_0p515v_0c_cworst_CCworst_T_ccsp
char_ssgnp_0p450v_m40c_cworst_CCworst_T.cons
char_ssgnp_0p450v_m40c_cworst_CCworst_T.non_cons
char_ssgnp_0p465v_m40c_cworst_CCworst_T.cons
char_ssgnp_0p465v_m40c_cworst_CCworst_T.non_cons
char_ssgnp_0p480v_m40c_cworst_CCworst_T.cons
char_ssgnp_0p480v_m40c_cworst_CCworst_T.non_cons
char_ssgnp_0p495v_m40c_cworst_CCworst_T.cons
char_ssgnp_0p495v_m40c_cworst_CCworst_T.non_cons
ffgnp_cbest_CCbest_T_125c
nldm_ffgnp_1p155v_125c_cbest_CCbest_T
nldm_ssgnp_0p475v_0c_cworst_CCworst_T
nldm_ssgnp_0p515v_0c_cworst_CCworst_T
ssgnp_cworst_CCworst_T_0c
```

### Corner plan

- **Tier-1 (byte-equal, frozen):** `ffgnp_cbest_CCbest_T_125c` only.
- **Tier-2 (planned, relaxed tolerance):** add `ssgnp_cworst_CCworst_T_0c`
  and one low-Vdd corner (e.g. `ssgnp_0p450v_m40c_cworst_CCworst_T`) as
  soon as their `LPE_*` parasitics are generated by Yuxuan.

## 6. Spec deltas that follow from this inspection

These updates land separately in `docs/phase2/spec_draft.md`; this
section is a checklist, not the edits themselves:

1. MVP family list: replace `SLH` slot with `SDFSYNC`; document the
   `sync` slot's coverage of scan-init / SE / Q-polarity / recovery axes.
2. Cell-name regex: install the N2P pattern from section 2 above.
3. Init-strategy map: remove `SLH` key, add `SDFSYNC1Q` key with SI/SE
   vs D handling.
4. Track/VT scope: declare Tier-1 = PNPN+SVT; Tier-2 = other tracks +
   SVT; Tier-3 = ELVT; LVT only via `psw_lvt` sub-lib.
5. Sub-library discovery: add directory-walking logic for `mb_*`,
   `pm_*`, `psw_*` siblings of `base_*`.
6. `KNOWN_V1_BUGS.md` entry: verify v1 path does not crash or silently
   skip when SLH cells are absent (N2P has none).

## 7. Provenance

- Inspection run: TSMC server, May 2026, second-pass script.
- Source images: 9 terminal photographs of Mate Terminal output,
  archived by Yuxuan in the Phase 2B.1 working session.
- This document is the parsed transcript; it is the artifact that
  downstream code and tests should reference, not the photos.
