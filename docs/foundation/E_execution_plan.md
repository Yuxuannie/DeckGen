# E: Execution Plan for Task E Template Sampling

## Purpose

This document gives Yuxuan exact commands to run on the TSMC server,
the expected output format, and the analysis Claude Code will perform
once data arrives. Self-contained: no re-derivation needed.

---

## 1. Server-Side Commands

The 10 template paths are relative to the MCQC SPICE template root.
Based on Phase 1 archaeology, this is the `TEMPLATE_DECK_PATH` from
globals.cfg, typically:

```
/CAD/stdcell/DesignKits/Sponsor/Script/MCQC_automation/Template/v1.6.10/SPICE_Templates/
```

If the path differs on your server, substitute accordingly.

### 1.1 Extraction script

Run this from the template root directory. It extracts the 6 key
structural features from each template:

```bash
#!/bin/bash
# Run from TEMPLATE_DECK_PATH
# Usage: bash extract_task_e.sh > task_e_output.txt

TEMPLATES=(
  "hold/template__common__rise__fall__1.sp"
  "hold/template__latch__rise__fall__glitch__minq__1.sp"
  "nochange/template__ckg__hold__fall__en__fall__pushout__negative__0.sp"
  "non_seq_hold/template__latch__fall__rise__pushout__1.sp"
  "setup/template__common__rise__fall__1.sp"
  "delay/template__invdX__fall.sp"
  "hold/template__retn__removal__fall__rise__glitch__minq__2.sp"
  "hold/template__MB__common__rise__fall__2.sp"
  "hold/template__SLH__rise__SE__rise__pushout__1.sp"
  "non_seq_hold/template__retn__nonseqhold__RETN__fall__CD__rise__glitch__minq__minbl_b__2.sp"
)

for tmpl in "${TEMPLATES[@]}"; do
  echo "========== $tmpl =========="
  if [ ! -f "$tmpl" ]; then
    echo "FILE NOT FOUND"
    echo ""
    continue
  fi

  echo "--- TOTAL LINES ---"
  wc -l < "$tmpl"

  echo "--- HEADER (first 12 lines) ---"
  head -12 "$tmpl"

  echo "--- .meas STATEMENTS ---"
  grep -n '\.meas' "$tmpl"

  echo "--- .ic STATEMENTS ---"
  grep -n '\.ic' "$tmpl" || echo "(none)"

  echo "--- .nodeset STATEMENTS ---"
  grep -n '\.nodeset' "$tmpl" || echo "(none)"

  echo "--- .tran LINE ---"
  grep -n '\.tran' "$tmpl"

  echo "--- WAVEFORM .inc ---"
  grep -n 'stdvs\|std_wv\|Waveform' "$tmpl"

  echo "--- TIMING VARS (tNN) ---"
  grep -oE '\bt[0-9]{2}\b' "$tmpl" | sort -u

  echo "--- PROBE_PIN refs ---"
  grep -n 'PROBE_PIN' "$tmpl" || echo "(none)"

  echo "--- VOLTAGE SOURCES (V*) ---"
  grep -n '^V[A-Z]' "$tmpl"

  echo ""
done
```

### 1.2 Alternative: manual extraction

If the script cannot be run, for each of the 10 templates provide:
1. First 12 lines (header + DONT_TOUCH_PINS + metadata)
2. All lines containing `.meas`
3. All lines containing `.ic` or `.nodeset`
4. The `.tran` line
5. Lines containing `stdvs` or `std_wv` (waveform model reference)
6. Total line count

### 1.3 If a template path does not exist

Report which paths are missing. This indicates the rule extraction has
stale paths from a different template version. For missing paths, check
if a similar file exists in the same directory (e.g., different variant
index) and provide that instead, noting the substitution.

---

## 2. Expected Output Format

One text file (`task_e_output.txt`), concatenated with `==========`
separators between templates. Example structure:

```
========== hold/template__common__rise__fall__1.sp ==========
--- TOTAL LINES ---
127
--- HEADER (first 12 lines) ---
** SPICE Deck created by TSMC ADC Timing Team ***
* DONT_TOUCH_PINS
$HEADER_INFO
...
--- .meas STATEMENTS ---
45: .meas tran cp2q_del1 ...
47: .meas tran glitch_check ...
--- .ic STATEMENTS ---
(none)
--- .nodeset STATEMENTS ---
78: .nodeset V(X1.Q) 0
79: .nodeset V(X1.QN) 'vdd_value'
...
```

Paste this output into the conversation or save as a file. Both work.

---

## 3. Local Analysis Steps (Claude Code)

Once data arrives, Claude Code will:

### 3.1 Extract fingerprint per template

For each of the 10 templates, extract:

| Dimension | How extracted |
|-----------|-------------|
| `line_count` | From "TOTAL LINES" |
| `meas_count` | Count of `.meas` lines |
| `ic_count` | Count of `.ic` lines |
| `nodeset_count` | Count of `.nodeset` lines |
| `timing_vars` | Unique `tNN` values, count |
| `probe_count` | Count of distinct `PROBE_PIN_N` |
| `vsource_count` | Count of `V[A-Z]` lines |
| `waveform_model` | Extracted from `stdvs_*` / `std_wv_*` reference |
| `has_glitch` | Whether any `.meas` line contains "glitch" |
| `has_pushout` | Whether any `.meas` line or header contains "pushout" |
| `dont_touch_pins` | From line 2 header |
| `init_style` | Classified: IC (if .ic > 0), NODESET (if .nodeset > 0, .ic == 0), NO_INIT (both zero) |

### 3.2 Compare against predictions from E_sampling_request.md

For each template, the prediction from E_sampling_request.md specified
expected structural properties. Compare:

| Template | Predicted init | Actual init | Match? |
|----------|---------------|-------------|--------|
| hold/common | nodeset for Q/QN | (from data) | Y/N |
| hold/latch | nodeset + internal latch state | (from data) | Y/N |
| ... | ... | ... | ... |

### 3.3 Compute topology compressibility

Group the 10 templates by directory:
- `hold/`: templates 1, 2, 7, 8, 9 (common, latch, retn_removal, MB, SLH)
- `nochange/`: template 3
- `non_seq_hold/`: templates 4, 10
- `setup/`: template 5
- `delay/`: template 6

Within `hold/` (5 templates), compute whether they share structural
fingerprint or differ:
- Same `meas_count`? Same `timing_vars` count? Same `init_style`?
- If they share fingerprint: topology sub-types are compressible
  within hold -> fewer principles needed
- If they differ: topology sub-types genuinely need separate templates

---

## 4. Decision Criteria

### 4.1 "35 principles" outcome (aggressive compression)

Triggers if ALL of:
- hold/common, hold/latch, hold/MB, hold/SLH share the same structural
  fingerprint (same meas_count, same timing_var_count, same init_style)
- Differences are limited to parameterizable values ($VAR names, pin
  names, direction tokens)
- nochange and non_seq_hold templates share structure with hold
  templates (differing only in waveform model and pin stimulus)

**Interpretation**: Topology sub-types within the same arc category are
structurally identical. The 15 internal-topology sub-principles collapse
to ~5 (one per directory/waveform-model). Total: ~20 trivial + ~15
discriminating = ~35.

### 4.2 "55 principles" outcome (each sub-type distinct)

Triggers if ANY of:
- hold/latch has different init_style from hold/common (e.g., extra
  .nodeset or .ic lines for latch transparency)
- hold/MB has different meas_count or structural block from hold/common
- hold/retn has .ic statements while others have only .nodeset
- non_seq_hold/latch differs structurally from hold/latch beyond
  waveform model

**Interpretation**: Topology sub-types genuinely require separate
template families. The 15 sub-principles cannot be compressed. Total:
~20 trivial + ~30 discriminating = ~50-55.

### 4.3 "Ambiguous, need more samples" outcome

Triggers if:
- Some topology pairs share structure, others don't (partial
  compression)
- Template paths are missing and substitutes don't provide clear signal
- Init style is "NODESET" for all but the counts differ significantly
  (e.g., 16 vs 32 .nodeset lines)

**Action**: Identify which specific topology pairs are ambiguous and
request 3-5 additional targeted templates to resolve.

---

## 5. SS1.X Update Template

Once the verdict is determined, Claude Code will update
`docs/phase2/spec_draft.md` section 1.X with:

```markdown
### 1.X Open Architectural Question: Topology Sub-Principle Compressibility

> **RESOLVED** (date). Task E sampling completed. Verdict: [35/55/PARTIAL].

**Evidence**: [N] of 10 sampled templates analyzed. Structural fingerprints:

| Template | Init | Meas | Timing | Waveform | Fingerprint group |
|----------|------|------|--------|----------|-------------------|
| hold/common | ... | ... | ... | ... | A |
| hold/latch | ... | ... | ... | ... | A or B |
| ... | | | | | |

**Verdict**: [One of:]
- Topology sub-types are compressible within arc categories. The 15
  internal-topology sub-principles collapse to ~N families. Revised
  principle count: [new number]. Phase 2A classifier can merge [list
  of mergeable classes].
- Topology sub-types are structurally distinct. The 15 sub-principles
  stand as-is. Principle count remains 45-55. Phase 2A classifier
  must distinguish all 15 classes.
- Partial compression: [list which pairs merge, which don't].
  Principle count: [revised range].

**Impact on Phase 2A**: [Specific changes to classifier.py CellClass
enum if any classes are merged or split.]
```

---

## 6. Timeline

- **Yuxuan runs extraction**: as soon as server access is available
- **Claude Code analysis**: same session as data paste (< 30 minutes)
- **SS1.X update + Phase 2A unblock**: immediately after analysis

Phase 2A can begin as soon as the SS1.X verdict is recorded.
