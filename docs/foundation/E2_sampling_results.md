# E.2: Sampling Results -- .ic / .nodeset / Spectre Distribution

Source: targeted sampling script run on
`/SIM/DFDS_20211231/Personal/ynie/4-Projects/2026/5-deckGen/templates/N2P_v1.0/`
Date: 2026-05-08

## Summary

Phase E (initial 10 samples) suggested all `.sp` files use neither `.ic`
nor `.nodeset`. Phase E.2 targeted sampling reveals this was a sampling
artifact. The actual init strategy distribution is:

- **TEMPLATE_EMBEDDED_NONE**: 604 templates (67%) -- no SPICE-level init,
  relies on V-source biasing + DONT_TOUCH_PINS metadata
- **TEMPLATE_EMBEDDED_IC**: 169 templates (19%) -- embedded `.ic`
  statements, concentrated in `delay/` (91 of 169 = 54%)
- **TEMPLATE_EMBEDDED_NODESET**: 126 templates (14%) -- embedded
  `.nodeset` statements, 100% in `mpw/` and `min_pulse_width/`
- BOTH: 0 (mutually exclusive -- confirmed)

All three are template-level properties. No runtime init dispatch is
needed. The `InitStrategy` is metadata that travels with the template,
not a strategy selected at deck generation time.

## Section A: .ic-using templates (169 total)

### Distribution by arc_type directory

| Arc type | Count | % of .ic |
|---|---:|---:|
| delay | 91 | 54% |
| hold | 56 | 33% |
| nochange | 14 | 8% |
| non_seq_hold | 4 | 2% |
| non_seq_setup | 3 | 2% |
| nochange_low_high | 1 | <1% |

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
| 4 | seq_inpin |
| 3 | SDFQNSXGD / SDFNQSXGD |

### ic_count is a function of cell topology

| Cell topology | Typical ic_count |
|---|---:|
| simple gates (latch_S, RCB, CKG, gclk_clken) | 2 |
| EDF / standard FF with state | 4 |
| MB (multi-bank) | 8 |
| synx retention (sync stage chain) | 14 |
| syn2 retention (asymmetric 2-stage) | 16 |
| seq_inpin (SDF input variants) | 1 |

### .tran style binding

| .tran style | Used by | Count |
|---|---|---:|
| `.tran 1p 5000n sweep monte=1` | hold, nochange, non_seq_hold, non_seq_setup | 78 |
| `.tran 1p 5000n sweep OPTIMIZE=OPT1 ...` | delay | ~85 |
| `.tran 1p 400ns` (bare) | delay (simple) | ~6 |

## Section B: .nodeset-using templates (126 total)

100% in mpw/ (63) and min_pulse_width/ (63). These two directories may
be symlinks/copies of identical content. The `.nodeset` block is 12-17
lines covering ml/sl/bl/Q/QN/Z/ZN node state with `*` glob matching.

## Section C: retn sibling comparison

Key finding: only `syn2` (16 .ic) and `synx` (14 .ic) have .ic statements
among retention non_seq_hold templates. syn3/4/5/6 and unprefixed retn all
have zero .ic. The asymmetric syn2 topology requires explicit state
initialization; deeper symmetric pipelines converge from V-source biasing
alone.

## Section D: Spectre .thanos.sp files (94 total)

| Arc type | Count |
|---|---:|
| delay | 91 |
| hold | 3 |

97% of Spectre files are in delay/. Spectre decks are complete standalone
templates with their own simulator config, not patches on HSPICE templates.

## Architectural implications

1. **InitStrategy is metadata, not dispatcher**: all three init styles are
   template-embedded. No runtime init dispatch needed.
2. **delay/ is its own ecosystem**: 91 .ic files, 91 Spectre files, all
   OPTIMIZE-style .tran. Cannot be omitted from MVP validation.
3. **ic_count is deterministic by topology**: computable from cell class.
4. **Spectre is not an edge case**: 94 files, dominant for delay arcs.
5. **Revised principle count**: 50-65 (was 45-55), trending higher due to
   delay ecosystem + Spectre parallel families.
