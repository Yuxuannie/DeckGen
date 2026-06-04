# DeckGen v2 -- Technique Survey (spec SS5.1: reuse before build)

Survey of existing open-source implementations before writing any algorithm.
The novel contribution is the **composition** (derive sensitization +
initialization from topology and prove them per deck), not re-implementing
solved primitives.

| Stage / technique | Candidate (link) | Decision | One-line reason |
|---|---|---|---|
| **S0 netlist / .subckt parse** | spicelib (PyLTSpice successor) [github.com/nunobrum/spicelib](https://github.com/nunobrum/spicelib) | **ADOPT** | Pure-Python, pip-only, handles line continuation / params / subckts; wrap behind `stage0_parse.parse()`. |
| S0 alt parser | PySpice `SpiceParser` [github.com/PySpice-org/PySpice](https://github.com/PySpice-org/PySpice/blob/master/PySpice/Spice/Parser.py) | reference | Mature but pulls ngspice/heavier deps; keep as fallback, not first choice on the air-gapped box. |
| S0 alt parser | eda-netlist-parser [piwheels.org/project/eda-netlist-parser](https://www.piwheels.org/project/eda-netlist-parser/) | reference | Pure-Python, extracts subckt/port/device for characterization; evaluate vs spicelib once real `.subckt` syntax is known (SEGMENT 2). |
| **S0-S1 device graph** | NetworkX [networkx.org](https://networkx.org/) | **ADOPT** | Standard graph primitive for the channel graph + traversal/feedback-loop detection. |
| S0-S1 circuit model | Hdl21 / VLSIR [github.com/dan-fritchman/Hdl21](https://github.com/dan-fritchman/Hdl21), [github.com/Vlsir/Vlsir](https://github.com/Vlsir/Vlsir) | reference | Rich generator/IR ecosystem but protobuf-heavy; overkill for a name-blind read-only structural model. Lightweight dataclasses (`engine/types.py`) instead. |
| **S1 CCC decomposition** | (no standalone lib; networkx connected-components) | **BUILD** | CCC = connected components over source/drain channel edges (gate edges excluded). Small, well-defined; build on networkx. State-node id (feedback loops) is the novel part. |
| **S2 sensitization / P1 SAT** | Z3 `z3-solver` [github.com/Z3Prover/z3](https://github.com/Z3Prover/z3) | **ADOPT** | Single-wheel SMT solver; clean Python API for the Boolean-difference obligation (path-live AND competitors-masked). |
| S2 SAT alt | PySAT [github.com/pysathq/pysat](https://github.com/pysathq/pysat) | reference | Faster pure-CNF if z3 proves heavy; same `stage2` seam, swap solver only. |
| S2 method | Boolean-difference arc recognition (literature) | **BUILD** (encode) | Adopt the *method* as reference; the CNF/SMT encoding from device graph + arc is engine-specific and small. |
| S3 initialization | (none -- domain-specific) | **BUILD** | Drive-and-settle stimulus synthesis from required pre-edge state is the core novel work; no library does it. |
| S4 deck assembly | (template/string assembly) | **BUILD** | Thin; positions the passed-through Liberate measurement block. |
| S5 verify harness | sim runner + Z3 (reuse S2) + probe compare | **BUILD** (compose) | Composition of adopted primitives; the per-deck P1/P2/P3 contract is the engine's contribution. |

## Summary of decisions
- **ADOPT:** spicelib (parse), NetworkX (graph), Z3 (SAT/P1).
- **BUILD (the novel composition):** CCC state-node identification (S1), sensitization encoding (S2), initialization / drive-and-settle (S3), deck assembly (S4), P1/P2/P3 verification harness (S5).
- **Reference only:** PySpice, eda-netlist-parser, Hdl21/VLSIR, PySAT, Boolean-difference literature.

## Dependency note (air-gapped, spec SS7)
The SEGMENT 1 skeleton runs on **stdlib only** (no pip) so it executes on the
air-gapped server immediately. Adopted libraries (spicelib, networkx, z3-solver)
enter behind the existing stage seams as each stage's real logic lands; each is a
single importable wheel that can cross the file-share boundary.

## SEGMENT 2 addendum -- deriving topology from an LPE-only netlist

The real input is a **parasitic-extracted (LPE) netlist only** -- no schematic/CDL
exists (MCQC also simulates on LPE). Confirmed on the real cell
`SDFQSXG0MZD1BWP130HPNPN3P48CPD`: flat single subckt, transistors are macro
subckts `X<name> d g s b nch_svt_mac|pch_svt_mac`, device terminals are private
extracted nodes (`XMSA2#d`), connectivity is only through ~226 parasitic `R`
(all interconnect; no real resistor devices). This splits Stage 0/1 into two
well-established layers:

### Layer A -- logical-net recovery (de-parasitic)
Extraction "cuts each net into pieces for extraction and stitches them back with
R" ([insighteda](https://insighteda.com/help-desk/app-notes/122-usage-tips-a-tricks/274-parasitics-fanout-and-extracted-netlists.html)).
Parasitic **R is always intra-net**; **C** is to-ground/coupling and carries no DC
connectivity. Timing-accurate reductions (serial-merge threshold, TICER) exist
([EDN](https://www.edn.com/parasitic-extraction-must-solve-advanced-node-issues/))
but are irrelevant for connectivity.

- **Decision: BUILD** -- drop all C, **short every R and union-find contract** its
  two nodes; node-clusters = logical nets. No thresholding. Name each cluster by
  its port or the common `netbase` of `netbase#k` nodes (`X<Dev>#pin` nodes are
  device pins, they do not name the net).
- **Self-check (becomes deck evidence):** each cluster must hold exactly one
  port/net anchor; an R bridging two distinct ports is a topology error -> FAIL
  with reason. Validated safe here: 226 R, zero are real resistor devices.

### Layer B -- CCC + storage-node identification
Canonical method is Randal **Bryant's switch-level / channel-connected-component**
analysis -- and its CCC definition is word-for-word the spec's:
[*Extraction of Gate-Level Models from Transistor Circuits*, ICCAD'91](https://www.cs.cmu.edu/~bryant/pubdir/iccad91.pdf);
COSMOS/ANAMOS; [TRANALYZE / symbolic FSM extraction](https://www.cs.cmu.edu/~bryant/pubdir/unc85.pdf).

- **CCC:** components over source/drain channels (gates excluded); rails + input
  ports are boundaries. **BUILD** on networkx union-find.
- **Storage nodes:** structural feedback -- a gate->drain "control" graph; an SCC
  of size >= 2 (e.g. `ml_a<->ml_b`) is a cross-coupled storage bit. Label
  master/slave by control-graph distance to D vs Q. **BUILD** (name-blind, per
  spec). This is the input to P2.

The sim deck still `.inc`s the original LPE netlist for HSPICE (as the golden
deck does); the R-merged graph is internal-only for derivation.

### Dependency reversal on S2 (z3 -> stdlib)
The survey's ADOPT-z3 decision is **overridden by a binding environment
constraint**: the air-gapped server forbids pip-from-internet (confirmed
2026-06-04). The whole engine therefore stays stdlib-only / pip-free. Stage 2
sensitization uses a **stdlib switch-level Boolean evaluator + Boolean-difference
enumeration** over the cell's few primary inputs (e.g. D/SI/SE/CP). At this size
exhaustive enumeration is exact, deterministic, and more inspectable than a SAT
call -- not a quality compromise. z3 remains a documented future option (via an
offline-staged wheel, if policy permits) should a cell's side-pin space ever
exceed enumeration.
