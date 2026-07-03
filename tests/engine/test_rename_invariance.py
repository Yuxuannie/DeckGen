"""
STEP 0 GATE -- rename-invariance of the foundation (spec 2c, v3 PROMPT 1 STEP 0).

Decisive test: obfuscate EVERY internal node + device-instance name in a netlist
(connectivity preserved exactly), feed both the original and the obfuscated form
to the engine, and require the CCC staging (master/stage/slave roles), the P1
side-pin bias, and the masked-pin determination to be IDENTICAL. If any of these
change under renaming, the engine is leaning on node NAMING (ml*/sl*/...) rather
than the conduction STRUCTURE -- which this gate forbids.

This runs on the single-stage scan-DFF placeholder (master `ml` + slave `sl`), so
it exercises the MECHANISM. The real master/stage1..6/slave staging of the demo
sync cell only appears on the server-side LPE netlist; this gate proves the
derivation is structure-based so that the real staging, when run, is trustworthy.
"""
import os
import re

from engine.config import ENGINE_DIR
from engine.stages import stage0_parse, stage1_ccc, stage2_sensitize
from engine.stages.stage0_parse import RAILS, _is_model_tok
from engine.types import Arc

FIXTURE = os.path.join(ENGINE_DIR, "fixtures", "SDFX_LPE_PLACEHOLDER.subckt")
PORTS = ["SI", "D", "SE", "CP", "Q"]            # interface pins -- never renamed
_SUFFIX = re.compile(r"#.*$")


def _base(tok):
    return _SUFFIX.sub("", tok)


def obfuscate(src, keep):
    """Rename every internal node + device-instance BASE name to a generic id,
    preserving connectivity, ports, rails, models, params and values exactly.

    A token like `ml_a#1` -> `n0007#1` (base renamed, `#k` suffix kept, so nodes
    that shared a base still cluster); `XMSA0` and its pins `XMSA0#d` share base
    `XMSA0` -> renamed consistently. Ports/rails (in `keep`) are never touched.
    Returns (obfuscated_src, base_map).
    """
    keep = set(keep) | RAILS
    lines = src.splitlines()

    # pass 1 -- collect node bases and (separately) device-instance bases. The
    # instance name's first letter sets the SPICE element type (`X` = macro
    # device), so instance bases must keep an `X` prefix or stage0 stops seeing
    # the transistor. Node bases never start a line, so they rename freely.
    bases = set()
    instance_bases = set()
    for line in lines:
        s = line.strip()
        if not s or s.startswith("*") or s.startswith("."):
            continue
        toks = s.split()
        head = toks[0][0].upper()
        if head == "X":
            instance_bases.add(_base(toks[0]))      # device instance name
            for t in toks[1:]:
                if "=" in t or _is_model_tok(t):
                    break                           # reached model/params
                bases.add(_base(t))                 # node terminal
        elif head in ("R", "C"):
            for t in toks[1:3]:                     # the two connected nodes
                bases.add(_base(t))
    bases = {b for b in bases if b and b not in keep} - instance_bases
    instance_bases = {b for b in instance_bases if b and b not in keep}

    base_map = {b: "X%04d" % i for i, b in enumerate(sorted(instance_bases), start=1)}
    base_map.update({b: "n%04d" % i for i, b in enumerate(sorted(bases), start=1)})

    # pass 2 -- rewrite any token whose base was collected
    def rep(tok):
        b = _base(tok)
        return base_map[b] + tok[len(b):] if b in base_map else tok

    out = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("*") or s.startswith("."):
            out.append(line)
        else:
            out.append(" ".join(rep(t) for t in line.split()))
    return "\n".join(out) + "\n", base_map


def _derive(src, cell):
    """Run S0->S1->S2 on a netlist source; return (graph, ccc, sens) for the
    placeholder's hold(CP, D) scan arc (SE select, SI masked)."""
    g = stage0_parse.parse(src, cell)
    ccc = stage1_ccc.decompose(g)
    arc = Arc(cell, "hold", "CP", "rise", "D", "fall", "notSE_SI", "")
    sens = stage2_sensitize.derive(g, arc, ccc)
    return g, ccc, arc, sens


def _staging(ccc):
    """Name-invariant staging signature: the multiset of storage roles and the
    storage-element count (role names are structural; node names are not used)."""
    roles = sorted(sn.role for sn in ccc.state_nodes)
    return roles, len(ccc.components)


def _bias(sens):
    """P1 conclusions keyed by PORT (ports are never renamed)."""
    return {
        "proven": sens.proven,
        "biases": {pin: d.value for pin, d in sens.side_biases.items()},
        "set_pins": sorted(sens.set_pins),
        "masked_pins": sorted(sens.masked_pins),
    }


def _read():
    with open(FIXTURE, "r", encoding="ascii") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def test_obfuscation_actually_renames_internal_nets():
    """Sanity: the obfuscator must genuinely erase the original internal names,
    or the invariance below would be vacuous."""
    src = _read()
    obf, base_map = obfuscate(src, PORTS)
    # telltale logical-net bases of the placeholder are gone from the source
    for tell in ("ml_a", "ml_b", "sl_a", "sl_b", "clkb", "seb", "mi#"):
        assert tell not in obf, f"obfuscation left {tell!r} in the netlist"
    # ports + rails survive untouched
    for p in PORTS + ["VDD", "VSS", "VPP", "VBB"]:
        assert p in obf, f"obfuscation wrongly renamed interface pin {p!r}"
    # the internal logical-net NAMES the parser produces actually differ
    g0, _, _, _ = _derive(src, "SDFX_LPE_PLACEHOLDER")
    g1, _, _, _ = _derive(obf, "SDFX_LPE_PLACEHOLDER")
    internal0 = {n for n in g0.nets if n not in PORTS and n not in RAILS}
    internal1 = {n for n in g1.nets if n not in PORTS and n not in RAILS}
    assert internal0 and internal1
    assert internal0 != internal1, "net names did not change -- obfuscation no-op"


def test_ccc_staging_is_rename_invariant():
    """CCC storage staging (master/slave role multiset + component count) must be
    identical under full internal-node renaming -- i.e. derived from structure."""
    src = _read()
    obf, _ = obfuscate(src, PORTS)
    _, ccc0, _, _ = _derive(src, "SDFX_LPE_PLACEHOLDER")
    _, ccc1, _, _ = _derive(obf, "SDFX_LPE_PLACEHOLDER")
    assert _staging(ccc0) == _staging(ccc1)
    # the placeholder is a single-stage DFF: exactly master + slave storage
    roles0, _ = _staging(ccc0)
    assert "master" in roles0 and "slave" in roles0


def test_p1_bias_and_masking_are_rename_invariant():
    """The P1 side-pin bias and the masked-pin set (keyed by port) must be
    identical under renaming -- derived by Boolean difference, not by name."""
    src = _read()
    obf, _ = obfuscate(src, PORTS)
    _, _, _, s0 = _derive(src, "SDFX_LPE_PLACEHOLDER")
    _, _, _, s1 = _derive(obf, "SDFX_LPE_PLACEHOLDER")
    assert _bias(s0) == _bias(s1)
    # and the conclusion is the expected scan-DFF one: SE select, SI masked
    assert s0.proven
    assert "SE" in s0.set_pins and "SI" in s0.masked_pins
