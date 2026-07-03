"""Select a grammar entry and emit its recipe lines. Value substitution of the
$PLACEHOLDERS is delegated to the existing deck_builder, not re-implemented here.
stdlib, ASCII."""
from __future__ import annotations

import json
import os

_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "config", "measurement_grammar.json")


class SelectionError(Exception):
    pass


def load_grammar(path: str = _DEFAULT) -> dict:
    with open(path, encoding="ascii") as fh:
        return json.load(fh)


def select_entry(grammar, *, arc_type, rel_dir, other_dir, cluster_tag=None):
    want = {"arc_type": arc_type, "rel_dir": rel_dir, "other_dir": other_dir}
    if cluster_tag is not None:
        want["cluster_tag"] = cluster_tag
    matches = [e for e in grammar["entries"]
               if all(e["key"].get(k) == v for k, v in want.items())]
    if matches:
        return matches[0]
    closest = [e["key"] for e in grammar["entries"]
               if e["key"].get("arc_type") == arc_type][:5]
    raise SelectionError(
        "no grammar entry for tried=%r; closest %d entr(ies): %r"
        % (want, len(closest), closest))


_IDENTITY = ("REL_PIN", "CONSTR_PIN", "PROBE_PIN_1")
_VALUE = ("VDD_VALUE", "INDEX_1_VALUE", "INDEX_2_VALUE", "MAX_SLEW",
          "OUTPUT_LOAD", "TEMPERATURE")


def emit(entry, arc_info, *, fill_values=False):
    keys = list(_IDENTITY)
    if fill_values:
        keys += list(_VALUE)
    out = []
    for line in entry["recipe_lines"]:
        for k in keys:
            if k in arc_info:
                line = line.replace("$" + k, str(arc_info[k]))
        if fill_values:
            line = line.replace("$PUSHOUT_PER", str(arc_info.get("PUSHOUT_PER", "0.4")))
        out.append(line)
    return out
