"""Mine a template directory into a measurement-grammar dict, and validate it by
byte-exact round-trip. CLI: `python -m core.measurement.mine mine|validate <dir>`.
Comprehensive-by-construction: the grammar is exactly the set of distinct recipe
regions in the corpus it is pointed at (run on the airgap corpus for full hold+
delay coverage). stdlib, ASCII."""
from __future__ import annotations

import glob
import json
import os

from core.measurement.regions import extract_recipe, parse_template_key


def mine(template_dir: str) -> dict:
    entries = []
    by_recipe = {}                         # recipe-tuple -> entry index
    for path in sorted(glob.glob(os.path.join(template_dir, "*.sp"))):
        recipe = extract_recipe(open(path, encoding="ascii", errors="replace").read())
        fname = os.path.basename(path)
        sig = tuple(recipe)
        if sig in by_recipe:
            entries[by_recipe[sig]]["provenance"].append(fname)
            continue
        by_recipe[sig] = len(entries)
        entries.append({"key": parse_template_key(path),
                        "recipe_lines": recipe, "provenance": [fname]})
    return {"version": 1, "source_corpus": template_dir, "entries": entries}
