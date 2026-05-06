# B Tables -- Full Arc Signature Group-By Data

Machine-readable companion to `docs/foundation/B_rule_groupby.md`.

## Files

### B1_trivial.csv

All arc signatures where exactly one template path is used regardless of
cell pattern (signature alone determines template).

| Column | Type | Description |
|--------|------|-------------|
| arc_type | string | Arc type (hold, setup, min_pulse_width, removal, nochange_*, etc.) |
| rel_pin | string | Related pin name(s), pipe-delimited if multiple; `[]` = empty/wildcard; `null` = not set |
| rel_pin_dir | string | Related pin direction: rise, fall, or null |
| constr_pin_dir | string | Constrained pin direction: rise, fall, or null |
| probe_pattern | string | Abstracted probe: `none`, `contains_X`, `len_N`, or compound `contains_X\|len_N` |
| num_rules | int | Number of rules in this signature group |
| num_cell_patterns | int | Number of distinct cell_pattern values across rules |
| template | string | The single template path used by all rules in this group |

### B2_discriminating.csv

All arc signatures where 2+ distinct templates are used -- cell pattern is
the discriminating factor within the signature.

| Column | Type | Description |
|--------|------|-------------|
| arc_type | string | Arc type |
| rel_pin | string | Related pin name(s), same encoding as B1 |
| rel_pin_dir | string | Related pin direction |
| constr_pin_dir | string | Constrained pin direction |
| probe_pattern | string | Abstracted probe pattern |
| num_rules | int | Number of rules in this signature group |
| num_templates | int | Number of distinct template paths |
| num_cell_patterns | int | Number of distinct cell_pattern values |
| pairs_json | JSON string | Array of `{"cell_pattern": [...], "template": "..."}` objects, one per rule |

### How to join

The arc signature is the natural key: `(arc_type, rel_pin, rel_pin_dir,
constr_pin_dir, probe_pattern)`. A signature appears in exactly one of
B1 or B2, never both.

To find all rules for a signature, filter `template_rules.json` by matching
arc_type + rel_pin + rel_pin_dir + constr_pin_dir + abstracted probe.

## Source

Generated from `my-work-scripts/deckgen/config/template_rules.json`,
filtering to `function="getHspiceTemplateName"` (688 rules).

## Statistics

| Metric | Value |
|--------|-------|
| Total signatures | 343 |
| Trivial signatures (B1) | 228 (236 rules, 34.3%) |
| Discriminating signatures (B2) | 115 (452 rules, 65.7%) |
