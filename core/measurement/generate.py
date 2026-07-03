"""generate.py -- G2 of the Phase G spec: parameterized generators for the
grammar families that differ only by a parameter. delay/common_inpin is one
generator x (rel_dir, out_dir); mpw sync{N}.CP and hold CP.sync{N}.D are one
generator each with the phase count, t0x ladder, and cross= indices as
functions of depth N. Parity gate: for every (family, N, dirs) instance in
the mined corpus, the generated recipe byte-matches the mined entry
(tests/test_measurement_generate.py + `python -m core.measurement.generate
check`). Outside the corpus the default stays refusal; generate_entry() is
the explicit extrapolation path -- its output is stamped so a reviewer can
never mistake an extrapolated deck for a corpus-validated one.
CLI: `python -m core.measurement.generate check [grammar.json]`.
stdlib, ASCII."""
from __future__ import annotations

import json
import re
import sys

from core.measurement.regions import classify_line

# ---------------------------------------------------------------------------
# constant blocks shared by the sequential families (transcribed from the
# mined corpus; the parity gate is the oracle that the transcription is exact)
# ---------------------------------------------------------------------------

_SEQ_OPTIONS = (
    ".options runlvl=6 ACCURATE=1 BRIEF=1 MODSRH=1 gmindc=1e-15 "
    "gdcpath=1e-15 method=gear converge=100 pode_check=0 autostop post=0 "
    "NOMOD=1 MEASDGT=7 measform=1 measfile=1 statfl=1 MCBRIEF=5 "
    "sampling_method=lhs")

_NODESET = [
    ".option ptran_nodeset=1",
    ".nodeset v(X1.ml*_a) = 'vdd_value'",
    ".nodeset v(X1.sl*_a) = 'vdd_value'",
    ".nodeset v(X1.bl*_a) = 'vdd_value'",
    ".nodeset v(X1.ml*_b) = 'vdd_value'",
    ".nodeset v(X1.sl*_b) = 'vdd_value'",
    ".nodeset v(X1.bl*_b) = 'vdd_value'",
    ".nodeset v(X1.ml*_ax) = 'vss_value'",
    ".nodeset v(X1.sl*_ax) = 'vss_value'",
    ".nodeset v(X1.bl*_ax) = 'vss_value'",
    ".nodeset v(X1.ml*_bx) = 'vss_value'",
    ".nodeset v(X1.sl*_bx) = 'vss_value'",
    ".nodeset v(X1.bl*_bx) = 'vss_value'",
    ".nodeset v(Q*) = 'vdd_value'",
    ".nodeset v(QN*) = 'vss_value'",
    ".nodeset v(Z*) = 'vdd_value'",
    ".nodeset v(ZN*) = 'vss_value'",
]


def _seq_header(opt_results):
    return [
        "** SPICE Deck created by TSMC ADC Timing Team ***",
        "* DONT_TOUCH_PINS",
        "$HEADER_INFO",
        "* THANOS Headers",
        "* CONSTR_CRITERIA | pushout",
        "* OPT_RESULTS | " + opt_results,
        "* MEAS_DEGRADE_PER cp2q_del1 | $PUSHOUT_PER",
        "* CONSTR_PIN_PARAM | constr_pin_offset",
        "* SPICE options",
        _SEQ_OPTIONS,
        ".save level=none",
        ".param max_slew = '0.1u'",
        ".param search_window = '$MAX_SLEW'",
    ]


def _opt_block(lb):
    return [
        "* Optimization settings",
        ".param opt_init = '5 * search_window'",
        ".param opt_ub = '10 * search_window'",
        ".param opt_lb = " + lb,
        ".param constr_pin_offset = opt_init",
        "*.param constr_pin_offset = OPT1('opt_init', 'opt_lb', 'opt_ub')",
        "* [1ps tolerance] relin = 0.001 / (opt_ub - opt_lb)",
        "*.MODEL optmod opt METHOD=passfail itropt=100 absin='0.1p'",
    ]


def _related_params(total, offset_at):
    """The t0x ladder: anchor k sits at (10(k-1)+1)*max_slew; the search
    anchor at *offset_at* repeats the previous anchor's timestamp plus the
    swept constr_pin_offset (the pulse edge the search moves)."""
    out = []
    for k in range(1, total + 1):
        if k == offset_at:
            out.append(".param related_pin_t%02d = '%d * max_slew + "
                       "constr_pin_offset'" % (k, 10 * (k - 2) + 1))
        else:
            out.append(".param related_pin_t%02d = '%d * max_slew'"
                       % (k, 10 * (k - 1) + 1))
    return out


def _stimulus(first_dir, total):
    toks = [first_dir if k % 2 == 1 else
            {"rise": "fall", "fall": "rise"}[first_dir]
            for k in range(1, total + 1)]
    anchors = "".join(" t%02d='related_pin_t%02d'" % (k, k)
                      for k in range(1, total + 1))
    return ("XV$REL_PIN $REL_PIN 0 stdvs_mpw_%s VDD='vdd_value' "
            "slew='rel_pin_slew'%s" % ("_".join(toks), anchors))


# ---------------------------------------------------------------------------
# family generators
# ---------------------------------------------------------------------------

def mpw_sync_recipe(n, rel_dir):
    """mpw sync{N}.CP: N flop stages between CP and the probed output. The
    rel_dir=rise variant ends at the searched pulse edge (2N+2 anchors); the
    fall variant appends recovery pulses after it (4N-1 anchors total)."""
    if n < 2:
        raise GenerateError("mpw sync generator needs depth >= 2 (depth 1 is "
                            "the CPN cluster, a different topology)")
    if rel_dir not in ("rise", "fall"):
        raise GenerateError("mpw sync generator needs rel_dir rise|fall, "
                            "got %r" % rel_dir)
    total = 2 * n + 2 if rel_dir == "rise" else 4 * n - 1
    offset_at = 2 * n + 2
    lines = _seq_header("cp2q_del1")
    lines += [
        ".param constrained_pin_t01 = '0 * max_slew'",
        ".param constrained_pin_t02 = '16 * max_slew'",
    ]
    lines += _related_params(total, offset_at)
    lines += _opt_block("'0 * search_window'")
    lines += _NODESET
    lines += ["* Toggling pins", _stimulus(rel_dir, total)]
    cp2q_cross = 2 * n + 1 if rel_dir == "rise" else 2 * n + 2
    lines += [
        "* Measurements",
        ".meas cp2q_del1 trig v($REL_PIN) val='vdd_value/2' cross=%d "
        "targ v(Q)  td='related_pin_t%02d' val='vdd_value/2' cross=1"
        % (cp2q_cross, cp2q_cross - 1),
        ".meas cp2cp trig v($REL_PIN) val='vdd_value/2' cross=%d "
        "targ v($CONSTR_PIN) val='vdd_value/2' cross=%d"
        % (2 * n + 1, 2 * n + 2),
        "* Transient Sim Command",
        ".tran 1p 50u sweep monte=1",
        ".end",
    ]
    return lines


def hold_sync_recipe(n):
    """hold CP.sync{N}.D (mined fall/rise only): the constrained pin's window
    widens with depth (t02 = 20N-4) and the launch edge under search is the
    (2N+2)th clock anchor."""
    if n < 2:
        raise GenerateError("hold sync generator needs depth >= 2 (depth 1 "
                            "is the CP.syncx.D cluster, a different topology)")
    total = 2 * n + 2
    lines = _seq_header("cp2q_del1 cp2q_del2")
    lines += [
        ".param constrained_pin_t01 = '16 * max_slew'",
        ".param constrained_pin_t02 = '%d * max_slew'" % (20 * n - 4),
    ]
    lines += _opt_block("'0'")
    lines += _related_params(total, total)
    lines += _NODESET
    lines += ["* Toggling pins", _stimulus("fall", total)]
    lines += [
        "* Measurements",
        ".meas cp2q_del1 trig v($REL_PIN) val='vdd_value/2' cross=%d "
        "targ v($PROBE_PIN_1) val='vdd_value/2' cross=1 "
        "td='related_pin_t%02d'" % (total, total - 1),
        ".meas cp2q_del2 trig v($REL_PIN) val='vdd_value/2' cross=%d "
        "targ v(Q) val='vdd_value/2' cross=1 td='related_pin_t%02d'"
        % (total, total - 1),
        ".meas cp2cp trig v($REL_PIN) val='vdd_value/2' cross=%d "
        "targ v($CONSTR_PIN) val='vdd_value/2' cross=%d"
        % (total - 1, total),
        "* Transient Sim Command",
        ".tran 1p 50u sweep monte=1",
        ".end",
    ]
    return lines


def delay_recipe(rel_dir, out_dir):
    """delay common_inpin: one generator x (rel_dir, out_dir). rel_dir picks
    the input waveform; out_dir orders the half_tt_out thresholds (a falling
    output crosses 0.7*vdd before 0.3*vdd)."""
    if rel_dir not in ("rise", "fall") or out_dir not in ("rise", "fall"):
        raise GenerateError("delay generator needs rise|fall dirs, got "
                            "(%r, %r)" % (rel_dir, out_dir))
    hi, lo = "'vdd_value*0.7'", "'vdd_value*0.3'"
    trig_v, targ_v = (hi, lo) if out_dir == "fall" else (lo, hi)
    return [
        "*** SPICE Deck created by TSMC ADC Timing Team ***",
        "* DONT_TOUCH_PINS",
        "* $HEADER_INFO",
        "* SPICE options",
        ".options RUNLVL=6 ACCURATE=1 BRIEF=1 autostop MODSRH=1 "
        "gmindc=1e-15 gmin=1e-15",
        ".option sampling_method=lhs",
        ".save level=none",
        ".param max_slew = '$MAX_SLEW'",
        ".param related_pin_t01 = 200ns",
        "* Toggling pins",
        "XV$REL_PIN $REL_PIN 0 stdvs_%s VDD='vdd_value' "
        "slew='rel_pin_slew' t01='related_pin_t01'" % rel_dir,
        "* Measurements",
        ".meas tran meas_delay trig v($REL_PIN) val='vdd_value/2' cross=1 "
        "targ v($PROBE_PIN_1) val='vdd_value/2' cross=1",
        ".meas tran half_tt_out trig v($PROBE_PIN_1) val=%s cross=1 "
        "targ v($PROBE_PIN_1) val=%s cross=1" % (trig_v, targ_v),
        ".meas tran meas_tt_out param='half_tt_out*2'",
        "* Transient Sim Command",
        ".tran 1p 5000n sweep monte=1",
        ".end",
    ]


_SYNC_MPW = re.compile(r"^sync(\d+)\.CP$")
_SYNC_HOLD = re.compile(r"^CP\.sync(\d+)\.D$")


def generated_recipe(key):
    """Recipe lines the generator produces for a grammar entry key, or None
    when no generator owns that family (one-off clusters stay mined-only)."""
    tag = key.get("cluster_tag", "")
    if key.get("arc_type") == "delay" and tag == "common_inpin":
        return delay_recipe(key["rel_dir"], key["other_dir"])
    m = _SYNC_MPW.match(tag)
    if m:
        return mpw_sync_recipe(int(m.group(1)), key["rel_dir"])
    m = _SYNC_HOLD.match(tag)
    if m and key.get("rel_dir") == "fall":
        return hold_sync_recipe(int(m.group(1)))
    return None


# ---------------------------------------------------------------------------
# frame splice + extrapolated entries
# ---------------------------------------------------------------------------

class GenerateError(Exception):
    """A generator cannot produce the requested (family, depth, dirs) --
    named reason, never a silent fallback."""


def splice_frame(frame_text, new_recipe):
    """Replace the recipe-classified line runs of *frame_text* with
    *new_recipe*, keeping every collateral/bias/blank line of the donor frame
    verbatim. Runs after the first are located by their first line (a
    constant section anchor); the same anchor splits new_recipe. Identity is
    gated per mined entry: splice(frame(N), recipe(N)) == frame(N)."""
    lines = frame_text.split("\n")
    runs = []                       # [start, end) index pairs into lines
    start = None
    for i, l in enumerate(lines):
        if classify_line(l) == "recipe":
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(lines)))
    if not runs:
        raise GenerateError("donor frame has no recipe lines")

    # split new_recipe at each later run's first-line anchor
    bounds = [0]
    pos = 0
    for (s, _e) in runs[1:]:
        anchor = lines[s]
        try:
            pos = new_recipe.index(anchor, pos + 1 if pos else 1)
        except ValueError:
            raise GenerateError(
                "cannot splice: donor frame section anchor %r not found in "
                "the generated recipe" % anchor)
        bounds.append(pos)
    bounds.append(len(new_recipe))

    out = []
    prev_end = 0
    for k, (s, e) in enumerate(runs):
        out.extend(lines[prev_end:s])
        out.extend(new_recipe[bounds[k]:bounds[k + 1]])
        prev_end = e
    out.extend(lines[prev_end:])
    return "\n".join(out)


def generate_entry(grammar, *, family, depth, rel_dir):
    """Synthesize a grammar entry for a sync depth OUTSIDE the mined corpus
    (or a missing direction variant). Returns (entry, tag, sel_rel,
    sel_other); the entry carries generated=True and a generated:...
    provenance so the caller can stamp the audit sidecar. The frame is the
    deepest mined family member's frame with the generated recipe spliced in.
    Raises GenerateError when no generator/donor covers the request."""
    if family == "hold":
        tag = "CP.sync%d.D" % depth
        sel_rel, sel_other = "fall", "rise"
        recipe = hold_sync_recipe(depth)
        pat = _SYNC_HOLD
    elif family == "mpw":
        if rel_dir not in ("rise", "fall"):
            raise GenerateError("mpw needs rel_dir rise|fall, got %r"
                                % rel_dir)
        tag = "sync%d.CP" % depth
        sel_rel = rel_dir
        sel_other = {"rise": "fall", "fall": "rise"}[rel_dir]
        recipe = mpw_sync_recipe(depth, rel_dir)
        pat = _SYNC_MPW
    else:
        raise GenerateError("no generator for family %r (generators cover "
                            "hold CP.sync{N}.D and mpw sync{N}.CP)" % family)

    donor = None
    donor_n = -1
    for e in grammar["entries"]:
        k = e["key"]
        m = pat.match(k.get("cluster_tag", ""))
        if m and k.get("rel_dir") == sel_rel and "frame_text" in e:
            n = int(m.group(1))
            if n > donor_n:
                donor, donor_n = e, n
    if donor is None:
        raise GenerateError("no mined %s sync entry with a frame to donate "
                            "the collateral skeleton (re-mine the corpus)"
                            % family)

    entry = {
        "key": {"arc_type": "mpw", "rel_dir": sel_rel,
                "other_dir": sel_other, "cluster_tag": tag},
        "recipe_lines": recipe,
        "frame_text": splice_frame(donor["frame_text"], recipe),
        "provenance": ["generated:%s depth=%d donor=%s" %
                       (family, depth, donor["provenance"][0])],
        "generated": True,
    }
    return entry, tag, sel_rel, sel_other


# ---------------------------------------------------------------------------
# parity check CLI
# ---------------------------------------------------------------------------

def check(grammar):
    """Parity report: every mined instance of a generated family must
    byte-match the generator, and self-splicing its own recipe into its own
    frame must reproduce the frame exactly."""
    covered = []
    mismatches = []
    for e in grammar["entries"]:
        gen = generated_recipe(e["key"])
        if gen is None:
            continue
        name = "%s/%s" % (e["key"]["cluster_tag"], e["key"]["rel_dir"])
        covered.append(name)
        if gen != e["recipe_lines"]:
            mismatches.append((name, "recipe"))
            continue
        if "frame_text" in e and \
                splice_frame(e["frame_text"], gen) != e["frame_text"]:
            mismatches.append((name, "frame self-splice"))
    return {"covered": covered, "mismatches": mismatches}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "check":
        print("usage: python -m core.measurement.generate check "
              "[grammar.json]")
        return 2
    path = argv[1] if len(argv) > 1 else "config/measurement_grammar.json"
    rep = check(json.load(open(path, encoding="ascii")))
    print("generator parity: %d/%d mined family instances byte-match"
          % (len(rep["covered"]) - len(rep["mismatches"]),
             len(rep["covered"])))
    for name, what in rep["mismatches"]:
        print("MISMATCH %s (%s)" % (name, what))
    return 0 if not rep["mismatches"] else 1


if __name__ == "__main__":
    sys.exit(main())
