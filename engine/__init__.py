"""
engine -- DeckGen v2 core characterization-deck engine (spec:
docs/phase2/DeckGen_v2_Engine_Problem_Description.md).

Derives an arc's sensitization + initialization from transistor-level topology
(name-blind) and emits machine-checkable P1/P2/P3 evidence per deck.

SEGMENT 1: pipeline runs end-to-end on a PLACEHOLDER fixture; Stages 1-5 are
stubs that carry typed data and derivation reasons but do not yet implement the
real algorithms. The novel work is the COMPOSITION; primitives are surveyed in
docs/phase2/v2_technique_survey.md.
"""
from engine.pipeline import run_pipeline

__all__ = ["run_pipeline"]
