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
