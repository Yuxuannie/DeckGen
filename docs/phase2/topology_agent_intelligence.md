# Topology Intelligence Agent Concept

## Goal

The topology intelligence agent is a learning layer above the principle engine.
Its purpose is to analyze previously unseen cells and simulation requests, then
produce structured topology knowledge that can be consumed by DeckGen and by
other projects that need cell-level characterization intelligence.

The agent does not replace deterministic deck generation. Instead, it proposes
or validates the abstract family information that the principle engine needs in
order to select templates, bind parameters, and warn about measurement risks.

## Motivation

The principle engine is strongest when a cell can be mapped to a known topology
family. New collateral drops may contain cells whose naming, internal structure,
or measurement behavior was not present in the bootstrap family registry. For
these cells, the current deterministic path should fail loudly or fall back to
v1 behavior, but that is not sufficient for long-term learning.

A separate topology agent can inspect the same collateral inputs used by DeckGen
and produce a normalized, reviewable schema for each cell/arc/table-point case.
This schema becomes the durable learning artifact.

## Inputs

For each target, the agent should receive a complete evidence bundle:

- `cell_arc_pt` identifier, including arc type, cell, probe pin, related pin,
  transition directions, when condition, and LUT indices.
- Parsed `define_cell` entry from `template.tcl`, including pinlist, output pins,
  delay/constraint/mpw template names, and any available attributes.
- Parsed `define_arc` entry from `template.tcl`, including vector, related pin,
  arc type, probe list, metric, metric threshold, and literal when condition.
- Netlist summary, including subckt pin order, transistor-level connectivity
  summary, clock/data/reset/scan candidate pins, and output candidates.
- Char.tcl-derived overrides, including glitch threshold, pushout percentage,
  output-load index, and model include selection.
- Template evidence, including matched v1 template path, closest principle
  family candidates, init style, transient style, and measurement blocks.
- Simulation context, including requested backend, corner, VDD, temperature,
  RC corner, nominal/MC mode, and requested table-point sweep.
- Historical results, if available: generated deck path, simulation pass/fail,
  convergence issues, waveform anomalies, and byte-diff status versus MCQC.

## Output Schema

The agent should emit a versioned topology schema. The schema must be structured
enough to feed DeckGen and conservative enough to require human review before it
extends the production family registry.

```yaml
schema_version: 1
cell: DFFQ1
arc_id: hold_DFFQ1_Q_rise_CP_rise_NO_CONDITION_1_1
source:
  node: N2P_v1.0
  lib_type: example_lib
  corner: ssgnp_0p450v_m40c_cworst_CCworst_T
classification:
  proposed_cell_class: flop
  confidence: 0.92
  evidence:
    - define_cell constraint_template present
    - Q listed as output pin
    - CP appears as clock-like related pin
family_proposal:
  family_key: hold/common/rise_fall
  backend_support:
    hspice: true
    spectre: false
  init_style: none
  tran_style: monte
parameter_binding:
  required_vars:
    - REL_PIN
    - CONSTR_PIN
    - PROBE_PIN_1
    - VDD_VALUE
    - INDEX_1_VALUE
    - OUTPUT_LOAD
  derived_values:
    REL_PIN: CP
    CONSTR_PIN: D
    PROBE_PIN_1: Q
measurement_guidance:
  measurement_type: standard
  risks:
    - verify constrained pin direction is opposite related pin direction
    - check when-condition side pins are not double-driven
  recommended_checks:
    - inspect waveform crossing at vdd/2
    - confirm output load matches delay template index policy
learning:
  novelty_type: known_family_new_cell
  reusable_features:
    topology_tokens: [DFF, Q, CP]
    structural_roles:
      clock: CP
      data: D
      output: Q
  human_review_required: true
```

## Intelligence Responsibilities

### 1. Topology abstraction

The agent should convert raw collateral and netlist evidence into a topology
hypothesis. The hypothesis should name the cell class, important subtypes, pin
roles, state elements, scan/retention/reset behavior, and measurement-relevant
internal structure.

### 2. Family recommendation

The agent should propose a principle-engine family key, but it should not edit
the production registry automatically. It should return candidate families,
confidence, missing evidence, and fallback advice.

### 3. Parameter-binding advice

The agent should explain how pins, directions, LUT indices, VDD/temp, output
load, glitch threshold, pushout percentage, and dont-touch pins should bind into
template variables. If a value is ambiguous, it must mark the ambiguity instead
of guessing silently.

### 4. Measurement guidance

The agent should produce simulation-specific warnings, such as likely glitch
measurement sensitivity, pushout-vs-standard measurement choice, initialization
risk, multi-output polarity risk, scan pin biasing risk, and backend-specific
syntax or convergence concerns.

### 5. Learning memory

The agent should persist reviewed schemas into a knowledge base. Future unknown
cells should be compared against this knowledge base using structural features,
not only cell-name tokens.

## Knowledge Base Layout

A practical repository layout could be:

```text
docs/topology_knowledge/
  schemas/
    N2P_v1.0/
      <lib_type>/
        <cell>/<arc_id>.yaml
  reviews/
    accepted/
    rejected/
    needs_more_evidence/
  indexes/
    family_examples.yaml
    pin_role_patterns.yaml
    measurement_risks.yaml
```

Production code should only consume accepted schemas or schemas explicitly
provided in an experimental mode.

## Interaction With DeckGen

The recommended integration is a three-layer flow:

1. Batch planner expands the target matrix into jobs.
2. Deterministic principle engine attempts classification, family selection,
   backend validation, and parameter binding.
3. If the deterministic path is unknown or low-confidence, the topology agent
   produces a topology schema and recommendation. The job can then either fail
   with actionable advice, run through v1 fallback, or run in experimental mode
   using the proposed schema.

The topology agent should therefore be advisory by default and executable only
under an explicit experimental gate.

## Safety Rules

- Never silently add a new production family from an unreviewed schema.
- Never override measured collateral values without marking the override source.
- Prefer failing with a diagnostic over generating a plausible but untrusted deck.
- Keep all recommendations reproducible by storing the evidence bundle hash.
- Separate structural evidence from language-model inference.

## Open Design Questions

1. What is the minimum netlist abstraction needed to distinguish genuinely new
   topology from a naming variation of a known family?
2. Should the knowledge base be repo-local YAML, an external database, or both?
3. How should confidence be calibrated against byte-equal MCQC regression data?
4. Which projects besides DeckGen should consume the topology schema, and what
   fields must be stable for those users?
5. What review workflow promotes a proposed schema into an accepted family or an
   accepted example of an existing family?
