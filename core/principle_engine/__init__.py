"""
core/principle_engine -- Principle-driven SPICE deck generation engine (v2).

Public API surface for Phase 2A (classifier + selector + backend abstraction).
param_binder, measurement, and engine orchestrator are Phase 2B/2C scope.

Usage:
    from core.principle_engine import classify_cell, select_template_family
    from core.principle_engine.family_types import CellClass, Backend, TranStyle
"""

from core.principle_engine.classifier import classify_cell
from core.principle_engine.family_types import (
    Backend,
    CellClass,
    InitStyle,
    MeasurementProfile,
    ProbeInfo,
    SelectionError,
    TemplateFamily,
    TranStyle,
)
from core.principle_engine.selector import select_template_family

__all__ = [
    "CellClass",
    "Backend",
    "TranStyle",
    "InitStyle",
    "MeasurementProfile",
    "ProbeInfo",
    "TemplateFamily",
    "SelectionError",
    "classify_cell",
    "select_template_family",
]
