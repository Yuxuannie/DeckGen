"""Mine a template directory into a measurement-grammar dict, and validate the
captured recipe regions by round-trip. CLI: `python -m core.measurement.mine mine|validate <dir>`.
The grammar captures the set of distinct recipe regions in the pointed-at corpus.
Round-trip validates that those captured regions are reproduced exactly; it does NOT
verify that the captured region is the semantically correct one. Comprehensiveness
on the airgap corpus rests on (i) the classifier's safe default (unknown line ->
recipe, so novel hold lines are kept) and (ii) human inspection of the per-arc-type
entry diff -- not on the 100% round-trip number alone. stdlib, ASCII."""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import sys

from core.measurement.emit import emit
from core.measurement.regions import extract_recipe, parse_template_key, partition


def mine(template_dir: str) -> dict:
    entries = []
    by_recipe = {}                         # recipe-tuple -> entry index
    # Accept both a flat template dir and a corpus root with one level of
    # arc-type subdirs (templates/N2P_v1.0/{delay,mpw}/...).
    paths = sorted(glob.glob(os.path.join(template_dir, "*.sp"))
                   + glob.glob(os.path.join(template_dir, "*", "*.sp")))
    for path in paths:
        text = open(path, encoding="ascii", errors="replace").read()
        recipe = extract_recipe(text)
        fname = os.path.basename(path)
        sig = tuple(recipe)
        if sig in by_recipe:
            entries[by_recipe[sig]]["provenance"].append(fname)
            continue
        by_recipe[sig] = len(entries)
        # frame_text is the ENTIRE template verbatim (collateral lines, blank
        # and trailing-space lines included), from the entry's first
        # provenance file. The assembler fills the frame exactly like the
        # golden flow (deck_builder substitution + injection points), so deck
        # byte-parity is by construction, not by re-composing sections.
        entries.append({"key": parse_template_key(path),
                        "recipe_lines": recipe, "provenance": [fname],
                        "frame_text": text})
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
        text = open(path, encoding="ascii", errors="replace").read()
        original = extract_recipe(text)
        entry = _select_for_template(grammar, path)
        # Route through emit() so the emitter is on the validated path.
        # emit(entry, {}) with empty arc_info and fill_values=False returns
        # recipe_lines verbatim (no placeholder substitution), which is the
        # correct comparison target for the local corpus (already templatized).
        emitted = emit(entry, {}) if entry else []
        if emitted == original:
            reproduced += 1
        else:
            diff = "\n".join(difflib.unified_diff(
                original, emitted, "original", "emitted", lineterm=""))
            mismatches.append({"file": os.path.basename(path), "diff": diff})
        # Conservation check: every source line must land in exactly one bucket.
        # This is a regression guard -- if classify_line ever diverges from
        # extract_recipe or gains an unhandled case, the counts disagree.
        p = partition(text)
        classified_total = sum(len(v) for v in p.values())
        source_total = len(text.splitlines())
        if classified_total != source_total:
            mismatches.append({
                "file": os.path.basename(path),
                "diff": "CONSERVATION FAILURE: %d classified != %d source lines" % (
                    classified_total, source_total)
            })
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
