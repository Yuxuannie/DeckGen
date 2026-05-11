"""
selector.py -- Template family selector for the principle engine.

Given a classified cell (CellClass) plus arc electrical characteristics,
selects the correct TemplateFamily from the registry.

Selection is BACKEND-AGNOSTIC.  The returned TemplateFamily carries both
hspice_template_path and spectre_template_path (either or both may be set).
The caller requests a specific backend after selection via
TemplateFamily.assert_backend_available(backend).

Selection chain:
  (cell_class, arc_type, rel_pin_dir, constr_pin_dir, measurement, probe_info)
      -> family key
      -> registry lookup
      -> TemplateFamily  (caller then asserts backend availability)

On failure, raises SelectionError with what was tried and closest matches.

Replaces: core/template_rules.py (688-rule JSON lookup).

Source: spec_draft.md SS2 (selector.py section), SS3 (v1/v2 coexistence),
        Yuxuan clarification 2026-05-11 (Spectre as parallel output format).
"""

from typing import Optional

from core.principle_engine.classifier import ClassifierResult
from core.principle_engine.families import get_registry
from core.principle_engine.family_types import (
    Backend,
    CellClass,
    MeasurementProfile,
    ProbeInfo,
    SelectionError,
    TemplateFamily,
    TranStyle,
)


def _dir_pair(rel_pin_dir: str, constr_pin_dir: str) -> str:
    """Normalize direction pair to string fragment used in family keys."""
    r = (rel_pin_dir or "rise").lower()
    c = (constr_pin_dir or "fall").lower()
    return f"{r}_{c}"


def _infer_tran_style(arc_type: str, backend: Backend) -> TranStyle:
    """Infer HSPICE TranStyle from arc_type and backend.

    Utility for engine.py (Phase 2B) to know what .tran command to emit.
    Not used by select_template_family itself (selection is backend-agnostic).

    Source: E2_sampling_results.md SS A (.tran style binding table).
    """
    if backend == Backend.SPECTRE:
        return TranStyle.SPECTRE_TRAN_ITER
    arc = (arc_type or "").lower()
    if arc in ("delay", "slew"):
        return TranStyle.OPTIMIZE
    return TranStyle.MONTE_CARLO


def _topology_key(
    classification: ClassifierResult,
    arc_type: str,
    measurement: Optional[MeasurementProfile],
    probe_info: Optional[ProbeInfo],
) -> str:
    """Build the topology segment of the family key.

    Maps CellClass to the key fragment used in the registry.
    For CKG: uses ckg_subtype.
    For RETN/SYNC: uses sync_depth if available.
    """
    cc = classification.cell_class

    if cc == CellClass.CKG:
        subtype = classification.ckg_subtype or "ckg"
        return subtype

    if cc == CellClass.RETN:
        depth = classification.sync_depth
        if depth is not None:
            return f"syn{depth}"
        return "retn"

    if cc == CellClass.SYNC:
        depth = classification.sync_depth
        if depth is not None:
            return f"sync{depth}"
        return "sync"

    _MAP = {
        CellClass.COMMON:   "common",
        CellClass.LATCH:    "latch",
        CellClass.FLOP:     "flop",
        CellClass.MB:       "mb",
        CellClass.EDF:      "edf",
        CellClass.SLH:      "slh",
        CellClass.ESLH:     "eslh",
        CellClass.RCB:      "rcb",
        CellClass.DET:      "det",
        CellClass.DIV4:     "div4",
        CellClass.DRDF:     "drdf",
        CellClass.BASEMEG:  "basemeg",
        CellClass.AO22:     "ao22",
    }
    return _MAP.get(cc, cc.value)


def _closest_matches(
    arc_type: str,
    topology: str,
    registry: dict,
    limit: int = 3,
) -> list:
    """Find closest partial matches in registry for diagnostic output."""
    arc = (arc_type or "").lower()
    candidates = []

    for key in registry:
        parts = key.split("/")
        score = 0
        if parts[0] == arc:
            score += 2
        if len(parts) > 1 and topology in parts[1]:
            score += 1
        if score > 0:
            candidates.append((score, key))

    candidates.sort(key=lambda x: -x[0])
    return [k for _, k in candidates[:limit]]


def select_template_family(
    classification: ClassifierResult,
    arc_type: str,
    rel_pin_dir: str,
    constr_pin_dir: str,
    measurement: MeasurementProfile = None,
    probe_info: ProbeInfo = None,
) -> TemplateFamily:
    """Select template family from registry.

    Selection is backend-agnostic.  The returned TemplateFamily may have
    one or both of hspice_template_path / spectre_template_path set.
    After selection, call family.assert_backend_available(backend) before
    assembling the deck.

    Args:
        classification:  Result from classify_cell().
        arc_type:        Arc type string ("hold", "delay", "min_pulse_width", etc.)
        rel_pin_dir:     Related pin direction ("rise" or "fall").
        constr_pin_dir:  Constraint pin direction ("rise" or "fall").
        measurement:     MeasurementProfile (optional; glitch/pushout variant).
        probe_info:      ProbeInfo (optional; polarity selection).

    Returns:
        TemplateFamily for the matching family.

    Raises:
        SelectionError: If no family matches, with diagnostic info.
    """
    arc = (arc_type or "").lower()

    # UNKNOWN cells must not silently fall through to common -- v1 fallback
    # is the correct path for unclassified cells (spec_draft.md SS3).
    if classification.cell_class == CellClass.UNKNOWN:
        raise SelectionError(
            "Cell not classified (CellClass.UNKNOWN); route to v1 engine",
            tried={"arc_type": arc, "cell_class": "unknown"},
            closest=[],
        )

    topology = _topology_key(classification, arc, measurement, probe_info)

    # Build candidate keys in preference order.
    # Delay/slew arcs use single-direction keys (output transition direction).
    # All other arcs use direction-pair keys.
    if arc in ("delay", "slew"):
        rel_dir = (rel_pin_dir or "rise").lower()
        candidate_keys = [
            f"{arc}/{topology}/{rel_dir}",   # exact topology match
            f"{arc}/common/{rel_dir}",       # topology fallback
        ]
        direction_desc = rel_dir
    else:
        dir_pair = _dir_pair(rel_pin_dir, constr_pin_dir)
        candidate_keys = [
            f"{arc}/{topology}/{dir_pair}",  # exact topology + direction
            f"{arc}/common/{dir_pair}",      # topology fallback, same direction
        ]
        direction_desc = dir_pair

    # Deduplicate while preserving order
    seen: set = set()
    ordered_keys = []
    for k in candidate_keys:
        if k not in seen:
            seen.add(k)
            ordered_keys.append(k)

    registry = get_registry()
    for key in ordered_keys:
        fam = registry.get(key)
        if fam is not None:
            return fam

    # No match -- build diagnostic
    tried = {
        "arc_type": arc,
        "cell_class": classification.cell_class.value,
        "topology": topology,
        "keys_tried": ordered_keys,
    }
    closest = _closest_matches(arc, topology, registry)
    raise SelectionError(
        f"No template family found for {arc}/{topology}/{direction_desc}",
        tried=tried,
        closest=closest,
    )
