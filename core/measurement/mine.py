"""Mine a template directory into a measurement-grammar dict, and validate it by
byte-exact round-trip. CLI: `python -m core.measurement.mine mine|validate <dir>`.
Comprehensive-by-construction: the grammar is exactly the set of distinct recipe
regions in the corpus it is pointed at (run on the airgap corpus for full hold+
delay coverage). stdlib, ASCII."""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import sys

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


def _select_for_template(grammar, path):
    """The entry whose provenance lists this template (round-trip selection)."""
    fname = os.path.basename(path)
    for e in grammar["entries"]:
        if fname in e["provenance"]:
            return e
    return None


def validate(template_dir: str, grammar: dict) -> dict:
    total = reproduced = 0
    mismatches = []
    for path in sorted(glob.glob(os.path.join(template_dir, "*.sp"))):
        total += 1
        original = extract_recipe(open(path, encoding="ascii", errors="replace").read())
        entry = _select_for_template(grammar, path)
        emitted = entry["recipe_lines"] if entry else []
        if emitted == original:
            reproduced += 1
        else:
            diff = "\n".join(difflib.unified_diff(
                original, emitted, "original", "emitted", lineterm=""))
            mismatches.append({"file": os.path.basename(path), "diff": diff})
    cov = round(100.0 * reproduced / total, 1) if total else 0.0
    return {"total": total, "reproduced": reproduced,
            "mismatches": mismatches, "coverage": cov}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="core.measurement.mine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine"); m.add_argument("dir")
    m.add_argument("-o", "--out", default="config/measurement_grammar.json")
    v = sub.add_parser("validate"); v.add_argument("dir")
    v.add_argument("-g", "--grammar", default=None)
    args = ap.parse_args(argv)

    if args.cmd == "mine":
        g = mine(args.dir)
        with open(args.out, "w", encoding="ascii") as fh:
            json.dump(g, fh, indent=2, ensure_ascii=True)
            fh.write("\n")
        print("mined %d entries from %d templates -> %s"
              % (len(g["entries"]),
                 sum(len(e["provenance"]) for e in g["entries"]), args.out))
        return 0

    g = json.load(open(args.grammar, encoding="ascii")) if args.grammar else mine(args.dir)
    rep = validate(args.dir, g)
    print("round-trip: %d/%d reproduced (%.1f%%)"
          % (rep["reproduced"], rep["total"], rep["coverage"]))
    for mm in rep["mismatches"]:
        print("MISMATCH %s\n%s" % (mm["file"], mm["diff"]))
    return 0 if not rep["mismatches"] else 1


if __name__ == "__main__":
    sys.exit(main())
