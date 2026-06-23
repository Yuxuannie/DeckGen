"""
deck_recipe.py -- programmatic combinational FMC deck generator.

The codified alternative to substituting into a per-design template_*.sp file:
it ASSEMBLES the deck section by section from the resolved collateral bundle
(`arc_info`, the dict the resolver already produces) plus a RecipeOpts. The
recipe (MCQC's design method) is expressed here as readable code -- one small
function per deck section, each stating WHAT it emits, WHY, and its SOURCE
(collateral field vs fixed convention) -- so it can be learned, questioned and
tuned by data, not by editing opaque .sp files.

Default RecipeOpts() reproduces the template-substitution deck byte-for-byte
(see tests/test_deck_recipe_parity.py). Knobs that the owner agreed are tunable
default to the MCQC value; tt_out / .meas semantics are FIXED (char flow) and are
NOT exposed. Stdlib only, ASCII.
"""
from __future__ import annotations

from dataclasses import dataclass

# Fixed conventions (MCQC recipe; reproduce exactly).
STD_WV = "/CAD/stdcell/DesignKits/Sponsor/Script/MCQC_automation/Template/std_wv_c651.spi"
MCQC_OPTIONS = (".options RUNLVL=6 ACCURATE=1 BRIEF=1 autostop MODSRH=1 "
                "gmindc=1e-15 gmin=1e-15")
TRAN_NOMINAL = ".tran 1p 5000n sweep monte=1"
RELATED_PIN_T01 = "200ns"


@dataclass
class RecipeOpts:
    """Tunable recipe knobs. Defaults reproduce MCQC byte-for-byte; any change is
    a deliberate divergence to validate by data (Step 6). tt_out/.meas are NOT
    here -- they are fixed by the char flow."""
    options: str = MCQC_OPTIONS
    tran: str = TRAN_NOMINAL
    related_pin_t01: str = RELATED_PIN_T01
    when_source: str = "collateral"     # "collateral" | "engine" (Step 4)


def _g(info, key, default=""):
    v = info.get(key)
    return default if v is None or v == "" else v


# --------------------------------------------------------------------------
# Section emitters -- each returns a list of content lines (no trailing '\n').
# --------------------------------------------------------------------------
def _header(info):
    """Provenance. SOURCE: collateral + arc (HEADER_INFO), made a comment."""
    return ["*** SPICE Deck created by TSMC ADC Timing Team ***",
            "* DONT_TOUCH_PINS",
            "* " + _g(info, "HEADER_INFO")]


def _options(info, opts):
    """HSPICE accuracy/convergence + Monte sampling. SOURCE: convention (KNOB)."""
    return ["* SPICE options", opts.options,
            ".option sampling_method=lhs", ".save level=none"]


def _includes(info, emitted):
    """std waveform + corner model + LPE netlist. SOURCE: collateral. Globally
    de-duplicates .inc (matches the template path: WAVEFORM_FILE often == std_wv)."""
    out = []

    def inc(section_title, *paths):
        out.append(section_title)
        for p in paths:
            p = _g({"p": p}, "p")
            if p and p not in emitted:
                emitted.add(p)
                out.append(".inc '%s'" % p)

    inc("* Waveform", STD_WV, _g(info, "WAVEFORM_FILE"))
    out.append("")
    inc("* Model include file", _g(info, "INCLUDE_FILE"))
    out.append("")
    inc("* Netlist path", _g(info, "NETLIST_PATH"))
    return out


def _lib_params(info):
    """PT. SOURCE: collateral (corner)."""
    return ["* Library information",
            ".param vdd_value = '%s'" % _g(info, "VDD_VALUE"),
            ".param vss_value = 0",
            ".temp %s" % _g(info, "TEMPERATURE")]


def _slew_load(info):
    """One (input slew, output load) point. SOURCE: collateral (template.tcl
    index). cl = INDEX_2, rel_pin_slew = INDEX_1; empty falls back to '0' (matches
    the template path). KNOB: the index point-set / packaging (Step 6)."""
    return ["* Slew and load information",
            ".param cl = '%s'" % _g(info, "INDEX_2_VALUE", "0"),
            ".param rel_pin_slew = '%s'" % _g(info, "INDEX_1_VALUE", "0")]


def _voltage(info):
    """Rails (VPP=vdd, VBB=vss). SOURCE: convention + netlist rails."""
    return ["* Voltage and Output Load",
            "VVDD VDD 0 'vdd_value'", "VVSS VSS 0 'vss_value'",
            "VVPP VPP 0 'vdd_value'", "VVBB VBB 0 'vss_value'"]


def _output_load(info):
    """Load cap on each output pin: C<pin> <pin> 0 'cl'. SOURCE: netlist output."""
    out = ["* Output Load"]
    pins = (_g(info, "OUTPUT_PINS") or _g(info, "PROBE_PIN_1")).split()
    for pin in pins:
        out.append("C%s %s 0 'cl'" % (pin, pin))
    return out


def _subckt(info):
    """Cell instance. SOURCE: collateral (netlist .subckt pin order)."""
    return ["* Subckt Definition",
            "X1 %s %s" % (_g(info, "NETLIST_PINS"), _g(info, "CELL_NAME"))]


def _timestamps(info, opts):
    """Input-edge timing. SOURCE: convention (max_slew from collateral; t01 fixed
    settling time)."""
    # max_slew falls back to '1n' when the collateral omits it -- matches the
    # template path (build_deck uses `MAX_SLEW or "1n"`).
    return ["* Waveform timestamps",
            ".param max_slew = '%s'" % _g(info, "MAX_SLEW", "1n"),
            ".param related_pin_t01 = %s" % opts.related_pin_t01]


def _side_pins(info, opts, notes=None):
    """Hold the non-measured inputs at their WHEN values (V<pin> 'vdd/vss_value').
    SOURCE: collateral (template.tcl WHEN) by default. With opts.when_source ==
    'engine', VERIFY against the LPE netlist that the collateral WHEN actually
    sensitizes the arc (Boolean difference). If it does, keep it (the deck is
    unchanged) -- two equally valid sensitizing vectors or a held don't-care are
    NOT a contradiction. Only when the collateral WHEN fails to sensitize do we
    flag a DIVERGENCE and substitute the engine-derived holds. Degrade to
    collateral cleanly if the engine cannot run."""
    when = _g(info, "WHEN")
    rel, constr = _g(info, "REL_PIN"), _g(info, "CONSTR_PIN")

    if opts.when_source == "engine":
        engine_holds, reason = _engine_biases(info)          # unconstrained
        coll = _coll_biases(when, rel, constr)
        if engine_holds is None:
            if notes is not None:
                notes.append("engine sensitization unavailable (%s); "
                             "used collateral WHEN" % reason)
        else:
            coll_ok, _ = _engine_biases(info, fixed=coll)    # does WHEN sensitize?
            if coll_ok is not None:
                if notes is not None:
                    notes.append("engine verified collateral WHEN sensitizes "
                                 "%s->%s" % (rel, _g(info, "PROBE_PIN_1")))
                # fall through: emit the collateral holds (deck unchanged)
            else:
                if notes is not None:
                    notes.append("collateral WHEN %r does not sensitize %s->%s; "
                                 "using engine holds"
                                 % (when, rel, _g(info, "PROBE_PIN_1")))
                    for pin in sorted(set(engine_holds) & set(coll)):
                        if engine_holds[pin] != coll[pin]:
                            notes.append("  DIVERGENCE %s: engine=%d collateral=%d"
                                         % (pin, engine_holds[pin], coll[pin]))
                out = ["* Pin definitions"]
                for pin in _side_pin_list(info):
                    if pin in engine_holds:
                        val = ("'vdd_value'" if engine_holds[pin] == 1
                               else "'vss_value'")
                        out.append("V%s %s 0 %s" % (pin, pin, val))
                return out

    out = ["* Pin definitions"]
    if when and when != "NO_CONDITION":
        for cond in when.split("&"):
            cond = cond.strip()
            if not cond:
                continue
            pin = cond.lstrip("!")
            if pin in (rel, constr):
                continue
            val = "'vss_value'" if cond.startswith("!") else "'vdd_value'"
            out.append("V%s %s 0 %s" % (pin, pin, val))
    return out


def _side_pin_list(info):
    from core.sensitize_bridge import side_inputs
    return side_inputs(_g(info, "NETLIST_PINS"), _g(info, "REL_PIN"),
                       _g(info, "OUTPUT_PINS") or _g(info, "PROBE_PIN_1"))


def _coll_biases(when, rel, constr):
    from core.sensitize_bridge import collateral_biases
    return collateral_biases(when, rel, constr)


def _engine_biases(info, fixed=None):
    """({pin:0/1}, reason) from the netlist, or (None, reason). Lazy + safe.
    `fixed` constrains side pins (used to verify a collateral WHEN)."""
    import os
    from core.sensitize_bridge import derive_combinational_biases
    path = _g(info, "NETLIST_PATH")
    if not path or not os.path.isfile(path):
        return None, "no readable NETLIST_PATH"
    try:
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            text = fh.read()
    except OSError as e:
        return None, "cannot read netlist: %s" % e
    return derive_combinational_biases(
        text, _g(info, "CELL_NAME"), _g(info, "REL_PIN"),
        _g(info, "PROBE_PIN_1"), _side_pin_list(info), fixed=fixed)


def _toggling(info):
    """Single input edge stdvs_<rel_dir>. SOURCE: arc + convention (stdvs)."""
    return ["* Unspecified pins", "",
            "* Toggling pins",
            "XV%s %s 0 stdvs_%s VDD='vdd_value' slew='rel_pin_slew' "
            "t01='related_pin_t01'"
            % (_g(info, "REL_PIN"), _g(info, "REL_PIN"), _g(info, "REL_PIN_DIR"))]


def _measurements(info):
    """FIXED by the char flow (do NOT change): input->output 50% delay, and output
    slew via the 30/70 (70/30 for a falling output) half-transition x2."""
    probe = _g(info, "PROBE_PIN_1")
    rel = _g(info, "REL_PIN")
    # The slew window follows the OUTPUT (probe) transition, not the related
    # pin: a rising output is measured 30%->70%, a falling output 70%->30%. Use
    # PROBE_PIN_DIR (the true output edge); fall back to CONSTR_PIN_DIR only when
    # the output direction was not resolved (it mirrors the related pin and is
    # therefore wrong for an inverting cell, e.g. an inverter).
    out_dir = _g(info, "PROBE_PIN_DIR") or _g(info, "CONSTR_PIN_DIR")
    lo, hi = ("0.3", "0.7") if out_dir != "fall" else ("0.7", "0.3")
    return ["* Measurements",
            ".meas tran meas_delay trig v(%s) val='vdd_value/2' cross=1 "
            "targ v(%s) val='vdd_value/2' cross=1" % (rel, probe),
            ".meas tran half_tt_out trig v(%s) val='vdd_value*%s' cross=1 "
            "targ v(%s) val='vdd_value*%s' cross=1" % (probe, lo, probe, hi),
            ".meas tran meas_tt_out param='half_tt_out*2'"]


def _tran(info, opts):
    """Transient + Monte. SOURCE: convention. KNOB: num_samples/packaging (Step 6)."""
    return ["* Transient Sim Command", opts.tran]


def build_combinational_deck(info, opts=None, notes=None):
    """Assemble a combinational FMC deck from arc_info + opts. Returns a list of
    lines (no trailing newline). Default opts reproduce the template deck.

    `notes` (optional list): when opts.when_source == 'engine', divergence and
    derivation notes are appended to it (the deck content itself is unaffected
    beyond the derived side pins)."""
    if opts is None:
        opts = RecipeOpts()
    emitted_inc = set()
    blocks = [
        _header(info),
        _options(info, opts),
        _includes(info, emitted_inc),
        _lib_params(info),
        _slew_load(info),
        _voltage(info),
        _output_load(info),
        _subckt(info),
        _timestamps(info, opts),
        _side_pins(info, opts, notes),
        _toggling(info),
        _measurements(info),
        _tran(info, opts),
    ]
    out = []
    for i, b in enumerate(blocks):
        out.extend(b)
        out.append("")          # blank line between sections (matches template)
    out.append(".end")
    return out


def render_text(lines):
    """Join generator lines into deck text (trailing newline)."""
    return "\n".join(lines) + "\n"
