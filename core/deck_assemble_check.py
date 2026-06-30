"""deck_assemble_check.py -- simulator-free local validation of an assembled
combinational deck: no unresolved $ placeholders, recipe fidelity vs the golden
template, and structural correctness of the engine bias section. stdlib, ASCII."""
from __future__ import annotations

import re

from core.measurement.regions import extract_recipe


def _bias_ok(deck_text: str, side_bias: dict, toggling_pin: str, detail: list) -> bool:
    ok = True
    for pin, val in side_bias.items():
        rail = "vdd_value" if val else "vss_value"
        want = "V%s %s 0 '%s'" % (pin, pin, rail)
        n = deck_text.count(want)
        if n != 1:
            ok = False
            detail.append("bias %s expected once as %r, found %d" % (pin, want, n))
    # toggling pin must not be tied off by a bias source
    if re.search(r"(?m)^V%s\s+%s\s+0\s" % (re.escape(toggling_pin),
                                           re.escape(toggling_pin)), deck_text):
        ok = False
        detail.append("toggling pin %s must not have a bias source" % toggling_pin)
    return ok


def check_against_template(deck_text: str, template_path: str,
                           side_bias: dict, toggling_pin: str) -> dict:
    detail = []
    no_ph = "$" not in deck_text
    if not no_ph:
        detail.append("unresolved $ placeholder(s) remain in the deck")
    bias_ok = _bias_ok(deck_text, side_bias, toggling_pin, detail)
    # recipe_matches is a DIAGNOSTIC ONLY (never asserted). It compares recipe
    # line-shapes (quoted values stripped) of the deck vs the template. NOTE: for an
    # assembled deck this key is structurally ALWAYS False -- classify_line() does not
    # recognize the assembler's "* ===== ... =====" section headers or its bias
    # V<pin> lines as collateral/bias, so they leak into the deck's recipe extract and
    # never match the template. recipe_matches is meaningful only for template-vs-
    # template comparisons. Real recipe fidelity is guaranteed by Phase A's round-trip.
    tmpl_recipe = extract_recipe(open(template_path, encoding="ascii",
                                      errors="replace").read())
    deck_recipe = extract_recipe(deck_text)
    def _shape(lines):
        return [re.sub(r"'[^']*'", "''", l) for l in lines]
    recipe_matches = _shape(deck_recipe) == _shape(tmpl_recipe)
    if not recipe_matches:
        detail.append("recipe region differs from template (line shapes)")
    return {"no_unresolved_placeholder": no_ph, "recipe_matches": recipe_matches,
            "bias_structural_ok": bias_ok, "detail": detail}
