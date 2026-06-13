# Pillar 3 -- Open Questions

What I could not resolve offline. Each needs either your judgment or a SPICE run.
Cross-referenced from `findings.md` and `proposals.md`.

## Needs a SPICE run (physics I cannot validate here)

**Q1 -- Is inter-phase hold "ideal enough"?** (findings D1.2)
The phase recurrence assumes a floating node holds its charge unchanged between
pre-conditioning phases (no sub-threshold / gate leakage over the settle window).
At the fixture corner (`ssgnp_0p450v_m40c`, low VDD) and over a multi-ns settle,
is the decay negligible vs the P3 tolerance? If not, the recurrence needs a leak
term and "last-driven value" becomes time-dependent.
Check: SPICE `.tran` on a precharged isolated node, measure droop over the actual
settle window.

**Q2 -- What tolerance separates model error from numerical noise?** (proposals P3/P6)
I proposed `min(5 mV, 1% VDD)` as a placeholder. UIC settling, integration order,
and `.tran` step all add noise. The real tolerance must be calibrated from a
SPICE run that re-runs the SAME deck with tightened tolerances and measures the
self-noise floor, then sets the model tolerance above it.
Check: V0/V1 re-run with `.option` accuracy sweeps.

**Q3 -- Is the large-|M| worst-case objective supermodular?** (findings D2.3)
For exhaustive (small |M|) it does not matter. If a compound cell ever has many
free masked pins, Dinkelbach needs each subproblem `N - lambda*D` to be
supermodular for an exact poly solve. I could not prove this from the cap-gating
sign structure in the abstract. Likely needs a concrete large cell to settle.
(Low priority -- may never arise for standard cells.)

**Q4 -- Does the t=0 worst-case vector track the measured-edge worst case?** (findings D2.4, proposals P7)
The bump `dV_f` is instantaneous; the perturbation then relaxes on an RC the sim
computes. Maximizing the t=0 bump is not provably maximizing the measured error.
If they do not track across a few cells, P7 downgrades from "auto-select worst"
to "report bump per vector and let the reviewer choose."
Check: enumerate candidate vectors, run SPICE for each, compare argmax(t=0 bump)
vs argmax(measured-edge error).

**Q5 -- Real DSPF/LPE C-line format coverage.** (proposals P1)
The fixture uses `C<name> nA nB farads`. Real kit LPE may use unit suffixes
(`1.2f`), `$`-comments, 3-terminal C, or a separate DSPF file rather than an
embedded subckt. Need a real netlist sample to confirm the parser branch (and
whether `eda-netlist-parser` is warranted vs extending stage0).
Check: one real LPE netlist from the kit.

**Q6 -- A keeper/floating-gate cell to exercise the fixpoint/X path.** (findings D1.3, proposals P4)
My vacuous-fixpoint result says iteration is only needed when a floating node
drives a gate. I have no such cell to test the iterate-or-X behavior or to
confirm that a real charge-race actually produces the X the model emits.
Check: identify a cell with a keeper or dynamic-node-into-gate structure; run SPICE.

## Needs your judgment / decision

**Q7 -- Scope of the first build.** findings argues the series-stack PDN internal
node (vacuous fixpoint, single-pass-correct) is the right FIRST target and the
keeper/bootstrap case is a later, harder tier. Do you want Pillar 3 v1 scoped to
the vacuous class only (with explicit X for floating-gate nodes), or full from
the start?

**Q8 -- Worst-case selection default.** P7 changes which valid sensitizing vector
becomes the golden for cells with free masked pins. Should worst-casing be the
DEFAULT, or opt-in behind a flag until V2-V4 validate it? (I lean opt-in: it
changes existing golden output.)

**Q9 -- numpy dependency.** P3's matrix solve is cleaner with numpy, but the repo
ships pyyaml as the only external dep and numpy is NOT installed in this
environment. Stdlib Gaussian elimination (prototyped) is enough for the small
dense systems standard cells produce. Keep it stdlib, or add numpy?

**Q10 -- Where does the cap network live?** I proposed a new `engine/charge.py`
to keep `stage0` connectivity-only. Alternative: hang it off `DeviceGraph`. The
new-module choice keeps stage boundaries clean (matches the one-dataclass-per-stage
ethos) but adds a module. Your call on placement.

**Q11 -- The branch reality.** The spec's "current-state" is on
`feat/phase-2b-engine`; this research sits on `research/autonomous-explore`
branched from `claude/topology-engine-discussion-7n0x06`, which has NO `engine/`
tree. When this graduates from research to implementation, it must target the
`feat/phase-2b-engine` lineage (or its successor `feat/phase-2c-charge-resolve`,
which the isolation rules named -- implying it already exists or is planned).
Confirm the target branch before any implementation session.
