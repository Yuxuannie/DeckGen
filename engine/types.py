"""
engine/types.py -- Typed inputs/outputs for the DeckGen v2 pipeline (spec SS5).

One dataclass per stage boundary, so each stage has a typed input and a typed
output and can be tested in isolation. Every *derived* value is wrapped in a
Derivation, so a single screenshot carries the value AND the reason it was
chosen (spec SS7.5: deterministic and inspectable).

SEGMENT 1 status: these are the real type contracts; the stages that fill them
are stubs. Search "PLACEHOLDER" for everything the SEGMENT 2 real-data pass
must replace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Derivation -- the provenance wrapper (spec SS7.5)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Derivation:
    """A derived value plus the reason it was derived and the stage that did it.

    Nothing the engine *computes* should be a bare value; wrap it so the
    screenshot is self-explanatory.
    """
    value: Any
    reason: str
    stage: str

    def __str__(self) -> str:
        return f"{self.value!r} <= {self.reason} [{self.stage}]"


# ---------------------------------------------------------------------------
# Stage 0 output -- structural device graph
# ---------------------------------------------------------------------------
@dataclass
class Device:
    name: str
    kind: str                     # "nmos" | "pmos" | "placeholder"
    terminals: Dict[str, str]     # role -> LOGICAL net (post R-merge), {d,g,s,b}
    model: str = ""               # raw model token, e.g. "nch_svt_mac"


@dataclass
class DeviceGraph:
    cell: str
    ports: List[str]
    devices: List[Device]
    nets: List[str]               # logical net names (after R-merge)
    node_to_net: Dict[str, str] = field(default_factory=dict)  # raw extracted node -> logical net
    checks: List[str] = field(default_factory=list)   # Stage-0 self-check derivations
    source: str = ""              # raw netlist text (provenance only)


# ---------------------------------------------------------------------------
# Engine input -- one arc on one cell (spec SS3 "Arc")
# ---------------------------------------------------------------------------
@dataclass
class Arc:
    cell: str
    arc_type: str
    rel_pin: str
    rel_dir: str
    constr_pin: str
    constr_dir: str
    when: str
    measurement: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, rec: Dict[str, Any]) -> "Arc":
        return cls(
            cell=rec["cell"],
            arc_type=rec["arc_type"],
            rel_pin=rec["rel_pin"],
            rel_dir=rec["rel_dir"],
            constr_pin=rec["constr_pin"],
            constr_dir=rec["constr_dir"],
            when=rec.get("when", "NO_CONDITION"),
            measurement=rec.get("measurement", ""),
            raw=dict(rec),
        )

    def label(self) -> str:
        cond = "" if self.when in ("", "NO_CONDITION") else f" when={self.when}"
        return f"{self.arc_type}({self.rel_pin}, {self.constr_pin}){cond}"


# ---------------------------------------------------------------------------
# Stage 1 output -- CCC decomposition + identified state nodes
# ---------------------------------------------------------------------------
@dataclass
class StateNode:
    net: str
    role: str                     # "master" | "slave" | "unknown"
    derivation: Derivation


@dataclass
class CCCResult:
    components: List[List[str]]    # each = list of logical nets in one channel-connected component
    state_nodes: List[StateNode]   # structurally-found storage nodes (cross-coupled), labeled master/slave
    notes: List[str] = field(default_factory=list)   # derivation trail (Bryant CCC + feedback)


# ---------------------------------------------------------------------------
# Stage 2 output -- sensitization + P1 obligation
# ---------------------------------------------------------------------------
@dataclass
class SensitizationResult:
    side_biases: Dict[str, Derivation]   # side pin -> required static value
    masked_paths: List[str]
    p1_obligation: str                   # textual obligation handed to the P1 check
    proven: bool = False                 # P1 discharged (measured path live, scan masked)
    clock_phase: str = ""                # transparent clock phase used in the proof
    set_pins: List[str] = field(default_factory=list)     # required selects (e.g. SE)
    masked_pins: List[str] = field(default_factory=list)  # masked data inputs (e.g. SI)
    arc_check: str = ""                  # derived-vs-arc.when agreement summary


# ---------------------------------------------------------------------------
# Stage 3 output -- initialization (drive-and-settle) + P2 probes
# ---------------------------------------------------------------------------
@dataclass
class InitializationResult:
    required_state: Dict[str, Derivation]   # state-node net -> required pre-edge value
    stimulus: List[str]                     # drive-and-settle stimulus lines
    precycle_count: Derivation              # number of pre-conditioning cycles
    probes: List[str]                       # nodes probed for P2


# ---------------------------------------------------------------------------
# Stage 4 output -- assembled SPICE deck
# ---------------------------------------------------------------------------
@dataclass
class Deck:
    cell: str
    text: str
    sections: Dict[str, str] = field(default_factory=dict)

    def line_count(self) -> int:
        return len(self.text.splitlines())


# ---------------------------------------------------------------------------
# Stage 5 output -- P1/P2/P3 verdict (spec SS6)
# ---------------------------------------------------------------------------
class PStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    STUB = "STUB"   # skeleton: stage logic not implemented yet (SEGMENT 1)


@dataclass
class Property:
    name: str           # "P1" | "P2" | "P3"
    title: str
    status: PStatus
    detail: List[str] = field(default_factory=list)


@dataclass
class Verdict:
    p1: Property
    p2: Property
    p3: Property

    @property
    def overall(self) -> PStatus:
        statuses = [self.p1.status, self.p2.status, self.p3.status]
        if PStatus.FAIL in statuses:
            return PStatus.FAIL
        if PStatus.STUB in statuses:
            return PStatus.STUB
        return PStatus.PASS


# ---------------------------------------------------------------------------
# Whole-pipeline result
# ---------------------------------------------------------------------------
@dataclass
class PipelineResult:
    arc: Arc
    graph: DeviceGraph
    ccc: CCCResult
    sens: SensitizationResult
    init: InitializationResult
    deck: Deck
    verdict: Verdict
    backend_name: str
    stage_log: List[str] = field(default_factory=list)
