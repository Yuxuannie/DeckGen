"""stage1b_classify.py -- structural sequential classification + depth (B2).

Classifies a cell's storage cores as latch / ff_chain / multibit /
recognized_unsupported and derives per-bit master/slave depth. Structure is
primary; the cell-name family (family_types regex) is an advisory cross-check
that reports divergence but never overrides. classify() never raises. stdlib +
engine only, ASCII only, simulator-free.

The naive discriminator (forward output-cone connectivity) mis-merges scan
multibit into one deep chain, because the scan daisy-chain links every earlier
bit into every later bit's output cone. peel_bits recovers the true bits from
the NESTED cone sets instead. See the B2 design doc, Section 2.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    nets: frozenset          # the storage core's nets
    role: str                # "latch" | "master" | "slave" | "unpaired"
    dist_to_out: int         # BFS influence-hops to nearest output


@dataclass(frozen=True)
class BitClass:
    outputs: tuple           # Q port(s) this bit drives, e.g. ("Q1",)
    stages: tuple            # ordered Stage list, master ... slave
    latch_stages: int        # == len(stages); latch=1, DFF=2, sync6=12
    ff_depth: int            # master/slave pair count; latch=0; k//2 otherwise
    paired_cleanly: bool     # False = odd core count / could not pair


@dataclass(frozen=True)
class SequentialClass:
    verdict: str             # "latch"|"ff_chain"|"multibit"
                             #   |"recognized_unsupported"|"combinational"
    bits: tuple
    name_hint: str
    divergence: str
    reason: str


def depth_of(seq) -> int:
    """Structural pipeline depth -- single source of truth for the P3 precycle
    oracle and the B3 deck emitter. ff_chain -> the bit's master/slave pair
    count; multibit -> the deepest bit; latch / combinational /
    recognized_unsupported / None -> 0. Duck-typed on .verdict and
    .bits[i].ff_depth so callers need no new import."""
    if seq is None:
        return 0
    if seq.verdict == "ff_chain":
        return seq.bits[0].ff_depth
    if seq.verdict == "multibit":
        return max(b.ff_depth for b in seq.bits)
    return 0


def peel_bits(cores):
    """Partition cores into output bits via nested-cone peeling.

    Returns (bits, dangling): bits is a list of {"cores": set[int],
    "outputs": list[str]}; dangling is the set of core indices whose cone is
    empty (drive no output). Outputs are peeled smallest-cone first so each bit
    claims only its own not-yet-assigned cores; a later output with no new cores
    (e.g. a complementary QN) attaches to the bit already holding those cores.
    """
    reachers = {}                               # q -> set(core index)
    for i, c in enumerate(cores):
        for q in c.cone:
            reachers.setdefault(q, set()).add(i)
    assigned = set()
    bits = []
    for q in sorted(reachers, key=lambda q: (len(reachers[q]), q)):
        new = reachers[q] - assigned
        if not new:
            for b in bits:
                if reachers[q] <= b["cores"]:
                    b["outputs"].append(q)
                    break
            continue
        bits.append({"cores": set(new), "outputs": [q]})
        assigned |= new
    dangling = set(range(len(cores))) - assigned
    return bits, dangling


def _pair(cores, bit):
    """Order a bit's cores by distance-to-output and pair master/slave.

    Nearer-to-output is slave, farther is master. Odd leftover -> 'unpaired'
    and paired_cleanly=False. Stages are emitted master-first (farthest first).
    """
    members = sorted(bit["cores"],
                     key=lambda i: (cores[i].dist_to_out, sorted(cores[i].nets)))
    outputs = tuple(sorted(bit["outputs"]))
    k = len(members)
    if k == 1:
        c = cores[members[0]]
        return BitClass(outputs, (Stage(c.nets, "latch", c.dist_to_out),),
                        1, 0, True)
    paired_cleanly = (k % 2 == 0)
    ff_depth = k // 2
    role = {}
    for p in range(0, k - 1, 2):
        role[members[p]] = "slave"          # nearer to output
        role[members[p + 1]] = "master"     # one stage farther back
    if not paired_cleanly:
        role[members[k - 1]] = "unpaired"
    ordered = sorted(members,
                     key=lambda i: (-cores[i].dist_to_out, sorted(cores[i].nets)))
    stages = tuple(Stage(cores[i].nets, role[i], cores[i].dist_to_out)
                   for i in ordered)
    return BitClass(outputs, stages, k, ff_depth, paired_cleanly)


from engine.types import DeviceGraph
from engine.stages.storage_view import build_storage_view


_NAME_TO_VERDICT = {
    "latch": "latch",
    "flop": "ff_chain",
    "sync": "ff_chain",
    "mb": "multibit",
    "retn": "recognized_unsupported",
    "det": "recognized_unsupported",
    "drdf": "recognized_unsupported",
    "div4": "recognized_unsupported",
    "edf": "recognized_unsupported",
}


def _name_crosscheck(cell_name, verdict):
    """Advisory only: compare structural verdict to the cell-name family.
    Returns (name_hint, divergence). Never raises, never overrides."""
    if not cell_name:
        return ("", "")
    try:
        from core.principle_engine.classifier import classify_cell
        fam = classify_cell(cell_name).cell_class.value
    except Exception:
        return ("", "")
    expected = _NAME_TO_VERDICT.get(fam, "")
    if not expected or expected == verdict:
        return (fam, "")
    return (fam, "name=%s implies %s but structure=%s" % (fam, expected, verdict))


def classify_cores(cores, cell_name=""):
    """Classify a StorageCore list into one SequentialClass. Never raises."""
    try:
        if not cores:
            nh, _ = _name_crosscheck(cell_name, "combinational")
            return SequentialClass("combinational", (), nh, "",
                                   "no storage core -- combinational (not B2's job)")
        raw_bits, dangling = peel_bits(cores)
        bits = tuple(_pair(cores, b) for b in raw_bits)
        if dangling:
            names = sorted(sorted(cores[i].nets)[0] for i in dangling)
            nh, _ = _name_crosscheck(cell_name, "recognized_unsupported")
            return SequentialClass("recognized_unsupported", bits, nh, "",
                                   "storage core(s) drive no output: %s" % names)
        if len(bits) == 1:
            verdict = "latch" if bits[0].latch_stages == 1 else "ff_chain"
        else:
            verdict = "multibit"
        nh, div = _name_crosscheck(cell_name, verdict)
        reason = ""
        if any(not b.paired_cleanly for b in bits):
            odd = [b.latch_stages for b in bits if not b.paired_cleanly]
            reason = "odd core count in bit(s): %s (review, could not pair)" % odd
        return SequentialClass(verdict, bits, nh, div, reason)
    except Exception as e:
        return SequentialClass("recognized_unsupported", (), "", "",
                               "internal: %s" % e)


def classify(graph: DeviceGraph, cell_name="") -> SequentialClass:
    """Graph entry point: extract the storage view, then classify. Never raises."""
    try:
        view = build_storage_view(graph)
    except Exception as e:
        return SequentialClass("recognized_unsupported", (), "", "",
                               "internal: %s" % e)
    return classify_cores(view.cores, cell_name)
