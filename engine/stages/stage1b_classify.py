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
