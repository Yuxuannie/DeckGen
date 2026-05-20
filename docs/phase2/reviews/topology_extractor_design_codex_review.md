# Topology Extractor Design Review (Codex, principle engine implementer)

Document reviewed: docs/phase2/topology_extractor_design.md
Branch context reviewed: feat/phase-2b1-topology-extractor-design (base feat/phase-2b1-foundation)
Review date: 2026-05-20 (UTC)

## Executive summary

This design has strong ambition and useful stage decomposition, but it currently mixes three different realities:

1. Claims about current principle engine state,
2. Forward-looking extractor architecture,
3. Historical/project-note examples that are internally inconsistent.

The biggest risk for direction check is not that the extractor idea is wrong; it is that the document overstates current code readiness and under-specifies the handoff contract to the actual principle engine interfaces that exist today.

I would not greenlight implementation from this draft without first fixing the high-severity mismatches below.

## Severity legend

- High: likely to cause wrong implementation direction or immediate integration break.
- Medium: design debt or ambiguity that will likely create churn.
- Low: wording/precision issue that can still mislead but is localized.

## High-severity findings

### H1) Principle-engine data model mismatch: design assumes FamilyEntry, code uses TemplateFamily

The design repeatedly frames outputs as "new family entry" and asks compatibility with "FamilyEntry", but this branch has no FamilyEntry type in core/principle_engine. The actual type is TemplateFamily dataclass in family_types.py, and selector/families are built around its key/path/tran/init/measurement schema.

Impact:
- Any extractor schema field plan that targets a nonexistent FamilyEntry shape will force rework at integration time.
- Handoff should be explicitly defined as either:
  - a deterministic mapping into TemplateFamily plus registry key, or
  - a separate proposal object and a translation step.

Required correction:
- Mark "FamilyEntry" references as "code not present on this branch" and replace with TemplateFamily-based contract.

### H2) Worked example Section 9 is internally contradictory and currently unsuitable as a validation anchor

Section 9 starts with AOI21-style function statement, then later does a SAT reconciliation narrative because arc vector direction appears inconsistent, then proposes alternate interpretation. This is not a stable worked example; it is a debugging transcript embedded as design truth.

Given PROJECT_NOTES section 2.4/2.5, the physically motivated expression and arc-splitting discussion are anchored around specific behavior, but Section 9 introduces unresolved ambiguity about function/vector semantics instead of ending with one canonical, checked truth table.

Impact:
- Teams may implement against the wrong Boolean/arc-direction assumptions.
- Stage B/C "deterministic" claims cannot be evaluated if the exemplar itself is unresolved.

Required correction:
- Replace Section 9 with a single reconciled ground truth trace (inputs, vector mapping, Boolean, expected output direction) and remove contradictory branches.

### H3) Handoff trigger semantics to principle engine are underspecified versus real SelectionError behavior

Design states slow path triggers when principle engine cannot classify or has low confidence. In code, selector raises SelectionError mainly on UNKNOWN classification or missing registry key; there is no confidence score in classifier/selector APIs.

Impact:
- Proposed control flow (especially inline mode) cannot be implemented without inventing a new confidence API.
- "low confidence" fallback is currently non-actionable in real interfaces.

Required correction:
- Define explicit trigger contract tied to current behavior (UNKNOWN or no matching family), then specify the exact new fields/API needed for confidence if desired.

## Medium-severity findings

### M1) Current-state numbers are partly accurate but contextualized incorrectly

Accurate in this branch:
- template_rules.json rule count = 854
- templates/N2P_v1.0 .sp files = 63
- bootstrap families list contains 16 TemplateFamily entries

But design context still talks as if these are directly the same plane as current principle-engine registry evolution toward ~60 families; in code, registry is currently a v2 bootstrap with specific arc/topology keys and backend split metadata, not yet a generic family abstraction layer.

Recommendation:
- Separate "measured corpus facts" from "current engine capability" in the narrative.

### M2) CellClass extension discussion is missing implementer-critical constraint

Design poses enum extension vs free field as open question. My implementer preference:
- Keep CellClass enum closed/stable for selector routing.
- Put extractor novelty into separate free-form topology tags/signatures.

Why:
- Selector key generation depends on finite known CellClass mapping.
- Free-form class labels in routing path will explode fallback behavior and diagnostics.
- Unknown/novel should remain explicit until promoted through reviewed migration.

### M3) "Mechanical/deterministic" characterization is optimistic for Stage B/C boundaries

Stage A graph decomposition can be deterministic. Stage B role naming and Stage C sensitization-to-measurement projection still depend on conventions from parser outputs (define_cell/define_arc normalization, vector semantics, arc defaults). Those are deterministic only if schema contracts are strict and tested.

Today, parser path already includes edge-case handling (for example define_arc default type behavior), so calling B/C "mechanical 80%" without hard interface tests is optimistic.

### M4) Stage effort estimate likely low for first usable integration

The draft implies near-term Stage A implementation in single-engineer-weeks style timelines. Realistically, first useful integration includes:
- parser-contract locking,
- deterministic snapshot fixtures,
- selector-compat translation,
- failure-mode telemetry.

I estimate initial end-to-end "reviewable and non-destructive" extractor slice will take longer than implied unless scope is narrowed to offline proposal generation only (no inline blocking path yet).

## Low-severity findings

### L1) Branch/status metadata in doc header appears stale

Doc says status on feature/topology-intelligence-agent-review, but review request says current branch is feat/phase-2b1-topology-extractor-design.

### L2) Companion doc reference is unresolved in this review context

topology_agent_intelligence.md is referenced but not part of this review request/package, so dependency assumptions should be minimized.

## Claims cross-check snapshot

- Rule count claim (854): matches current branch.
- Template count claim (63): matches current branch (.sp under templates/N2P_v1.0).
- Bootstrap families claim (16): matches current branch count of TemplateFamily entries.
- FamilyEntry references: code not present on this branch.

## Integration guidance I would give Florin directly

1. Keep principle engine as deterministic fast path with current selector contract.
2. Make extractor v1 output a proposal artifact that is explicitly translated into TemplateFamily-compatible candidate entries; do not couple extractor internals directly to selector routing.
3. Treat Section 9 as blocked until a single canonical reconciled example is produced and turned into regression fixtures.
4. Defer any "low confidence" routing claims until confidence is a first-class, tested API in classifier/selector.

## Final verdict

Direction is promising, but the design is not implementation-ready against this branch's ground truth. I recommend "revise then direction-check" rather than "approve and start build".
