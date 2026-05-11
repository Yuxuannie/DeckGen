"""
classifier.py -- Cell topology classifier for the principle engine.

Classifies a cell into one of 15 CellClass values using a hybrid strategy:
  1. define_cell attributes from parsed template.tcl Cell object (preferred)
  2. Cell name token matching (fallback when Cell object unavailable)

The 15 classes replace the cell-name pattern matching scattered across the
688 rules in template_rules.json and the 18K-line if-chain.

Classification order matters: more specific patterns before more general ones.
For example, ESLH before SLH, synX before RETN, MB before FLOP.

Source: B_rule_groupby.md SS2 (internal topology category, 250+ rules, 15
sub-types), F_feasibility_verdict.md SS2.
"""

import re
from typing import Optional

from core.principle_engine.family_types import CellClass

# ---------------------------------------------------------------------------
# Token tables -- ordered most-specific to least-specific within each class.
# Each tuple: (regex_pattern, CellClass)
# ---------------------------------------------------------------------------

# Cell name token patterns.  Checked in the order listed; first match wins.
_NAME_PATTERNS: list = [
    # --- AO22 / OA22 compound gates (Spectre-only delay arcs) ---
    (re.compile(r'AO22|OA22', re.IGNORECASE), CellClass.AO22),

    # --- DIV4: clock divider ---
    (re.compile(r'DIV4', re.IGNORECASE), CellClass.DIV4),

    # --- DRDF: dual-rail dual-flop ---
    (re.compile(r'DRDF', re.IGNORECASE), CellClass.DRDF),

    # --- CKG: clock gater family (ckg, ckgn, ckgian, ckgmux2, ckgmux3)
    #     Match before SYNC to avoid ckg tokens inside synX names.
    (re.compile(r'CKG|CLKGT|CLKGATE', re.IGNORECASE), CellClass.CKG),

    # --- BASEMEG: memory (WWL-based) ---
    (re.compile(r'BASEMEG|MEGA|MEGABASE', re.IGNORECASE), CellClass.BASEMEG),

    # --- RETN retention family ---
    # synX (syn2..syn6) before plain RETN/RTNQ so depth is captured.
    # synx (no digit) is a specific deep-pipeline variant (14 .ic).
    # \bRET matches RETN, RETNQ, RETD, RET variants at a word boundary.
    (re.compile(r'SYN[2-6]|synx', re.IGNORECASE), CellClass.RETN),
    (re.compile(r'RETN|RTNQ|\bRET', re.IGNORECASE), CellClass.RETN),

    # --- SYNC: synchronizer ---
    (re.compile(r'SYNC[2-6]|\bSYNC', re.IGNORECASE), CellClass.SYNC),

    # --- ESLH: extended scan latch (before SLH) ---
    (re.compile(r'ESLH', re.IGNORECASE), CellClass.ESLH),

    # --- SLH: scan latch ---
    # No trailing \b: "SLH1BWP" must match even when SLH is followed by digits.
    (re.compile(r'\bSLH', re.IGNORECASE), CellClass.SLH),

    # --- RCB: register-controlled buffer ---
    (re.compile(r'\bRCB', re.IGNORECASE), CellClass.RCB),

    # --- MB: multi-bank (before EDF/FLOP to catch MBFF, MBD etc.) ---
    # No trailing \b: "MBD4BWP" must match.
    (re.compile(r'\bMB', re.IGNORECASE), CellClass.MB),

    # --- EDF: edge-detect flip-flop ---
    # No trailing \b: "EDFQ1BWP" must match.
    (re.compile(r'\bEDF|SDFQNSXGD|SDFNQSXGD', re.IGNORECASE), CellClass.EDF),

    # --- DET: detector ---
    # No trailing \b: "DETD1BWP" must match.
    (re.compile(r'\bDET', re.IGNORECASE), CellClass.DET),

    # --- LATCH: level-sensitive transparent latch ---
    (re.compile(r'LATCH|LTHD|LTCH|\bLA\b', re.IGNORECASE), CellClass.LATCH),

    # --- FLOP: standard D flip-flop (scan variants included) ---
    (re.compile(r'\bDFF|SDFF|SDFQ|DFFQ|DFFS|DFQD|\bFF\b', re.IGNORECASE), CellClass.FLOP),
]


def _extract_sync_depth(cell_name: str) -> Optional[int]:
    """Extract synchronizer pipeline depth from cell name.

    Returns integer depth (2-6) if found, else None.
    Examples: 'SYNC2' -> 2, 'SYNC4D2BWP...' -> 4
    """
    m = re.search(r'SYN(?:C)?([2-6])', cell_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _extract_ckg_subtype(cell_name: str) -> str:
    """Extract CKG gate logic sub-type from cell name.

    Returns one of: "ckgmux3", "ckgmux2", "ckgian", "ckgn", "ckg".
    More specific checks first.
    """
    name_upper = cell_name.upper()
    if 'CKGMUX3' in name_upper or 'CLKGMUX3' in name_upper:
        return "ckgmux3"
    if 'CKGMUX2' in name_upper or 'CLKGMUX2' in name_upper:
        return "ckgmux2"
    if 'CKGIAN' in name_upper:
        return "ckgian"
    if 'CKGN' in name_upper or 'CLKGN' in name_upper:
        return "ckgn"
    return "ckg"


class ClassifierResult:
    """Result of cell classification.

    Carries the primary CellClass plus any auxiliary data needed by the
    selector (e.g., sync_depth for RETN/SYNC, ckg_subtype for CKG).
    """
    __slots__ = ("cell_class", "sync_depth", "ckg_subtype", "source")

    def __init__(
        self,
        cell_class: CellClass,
        sync_depth: Optional[int] = None,
        ckg_subtype: Optional[str] = None,
        source: str = "name",
    ):
        self.cell_class = cell_class
        self.sync_depth = sync_depth        # int or None; only for SYNC/RETN
        self.ckg_subtype = ckg_subtype      # str or None; only for CKG
        self.source = source                # "define_cell" | "name" | "fallback"

    def __repr__(self) -> str:
        parts = [f"CellClass.{self.cell_class.name}"]
        if self.sync_depth is not None:
            parts.append(f"depth={self.sync_depth}")
        if self.ckg_subtype is not None:
            parts.append(f"ckg_subtype={self.ckg_subtype!r}")
        parts.append(f"source={self.source!r}")
        return f"ClassifierResult({', '.join(parts)})"


def _classify_by_name(cell_name: str) -> ClassifierResult:
    """Classify cell using name-token matching only."""
    for pattern, cell_class in _NAME_PATTERNS:
        if pattern.search(cell_name):
            sync_depth = None
            ckg_subtype = None
            if cell_class == CellClass.SYNC:
                sync_depth = _extract_sync_depth(cell_name)
            elif cell_class == CellClass.RETN:
                sync_depth = _extract_sync_depth(cell_name)  # syn2..syn6 depth
            elif cell_class == CellClass.CKG:
                ckg_subtype = _extract_ckg_subtype(cell_name)
            return ClassifierResult(
                cell_class=cell_class,
                sync_depth=sync_depth,
                ckg_subtype=ckg_subtype,
                source="name",
            )
    return ClassifierResult(cell_class=CellClass.UNKNOWN, source="fallback")


def _classify_by_define_cell(cell_obj) -> Optional[ClassifierResult]:
    """Attempt classification from parsed define_cell attributes.

    cell_obj is a parsed Cell object from core/parsers/template_tcl.py.
    Returns ClassifierResult if a definitive match is found, else None
    (caller falls back to name-based classification).

    Attribute keys vary by template.tcl version; we check common ones:
      - cell_type / celltype / CELL_TYPE
      - scan_style / flip_flop_type
      - retention / ret_type

    Source: Phase 1 archaeology (template.tcl define_cell blocks).
    """
    if cell_obj is None:
        return None

    # Normalize: try common attribute name variants
    attrs = {}
    if hasattr(cell_obj, 'attrs'):
        attrs = {k.lower(): v for k, v in (cell_obj.attrs or {}).items()}
    elif hasattr(cell_obj, '__dict__'):
        attrs = {k.lower(): v for k, v in cell_obj.__dict__.items()}

    cell_type = attrs.get('cell_type', attrs.get('celltype', '')).lower()
    scan_style = attrs.get('scan_style', '').lower()
    retention = attrs.get('retention', attrs.get('ret_type', '')).lower()

    # Explicit type flags take precedence over name matching
    if 'latch' in cell_type:
        return ClassifierResult(cell_class=CellClass.LATCH, source="define_cell")
    if 'multi_bank' in cell_type or 'mb' in cell_type:
        return ClassifierResult(cell_class=CellClass.MB, source="define_cell")
    if 'edf' in cell_type or 'edge_detect' in cell_type:
        return ClassifierResult(cell_class=CellClass.EDF, source="define_cell")
    if 'clock_gate' in cell_type or 'ckg' in cell_type:
        return ClassifierResult(cell_class=CellClass.CKG, source="define_cell")
    if 'retention' in cell_type or retention:
        return ClassifierResult(cell_class=CellClass.RETN, source="define_cell")
    if 'sync' in cell_type:
        return ClassifierResult(cell_class=CellClass.SYNC, source="define_cell")

    # Not enough info from define_cell to classify definitively
    return None


def classify_cell(cell_name: str, cell_obj=None) -> ClassifierResult:
    """Classify cell by topology.

    Strategy:
      1. If cell_obj (parsed template.tcl Cell) is provided, attempt
         classification from define_cell attributes.
      2. If step 1 is inconclusive or cell_obj is None, use cell name
         token matching.
      3. If neither matches, return CellClass.UNKNOWN (triggers v1 fallback).

    Args:
        cell_name: Cell name string (e.g., "DFFQ1BWP130H").
        cell_obj:  Optional parsed Cell object from template_tcl parser.
                   Pass None if template.tcl is not available.

    Returns:
        ClassifierResult with .cell_class, .sync_depth, .ckg_subtype, .source.
    """
    # Step 1: define_cell attributes (most reliable)
    if cell_obj is not None:
        result = _classify_by_define_cell(cell_obj)
        if result is not None:
            # Augment with name-derived sub-type info that define_cell may lack
            if result.cell_class == CellClass.SYNC and result.sync_depth is None:
                result.sync_depth = _extract_sync_depth(cell_name)
            if result.cell_class == CellClass.RETN and result.sync_depth is None:
                result.sync_depth = _extract_sync_depth(cell_name)
            if result.cell_class == CellClass.CKG and result.ckg_subtype is None:
                result.ckg_subtype = _extract_ckg_subtype(cell_name)
            return result

    # Step 2: name-token matching
    return _classify_by_name(cell_name)
