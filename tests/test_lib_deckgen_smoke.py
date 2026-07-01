import os, subprocess, sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args):
    return subprocess.run([sys.executable, "tools/lib_deckgen.py"] + args,
                          cwd=_REPO, capture_output=True, text=True)


def test_lib_deckgen_hold_writes_real_recipe_deck(tmp_path):
    out = str(tmp_path / "decks")
    p = _run(["--netlist", "engine/fixtures/SDFX_LPE_PLACEHOLDER.subckt",
              "--arc-type", "hold", "--out", out])
    assert p.returncode == 0, p.stderr
    deck = os.path.join(out, "SDFX_LPE_PLACEHOLDER.sp")
    assert os.path.exists(deck)
    text = open(deck, encoding="ascii").read()
    assert "cp2q_del1" in text and "$" not in text        # real recipe, resolved


def test_lib_deckgen_reports_combinational_without_deck(tmp_path):
    p = _run(["--dir", "engine/fixtures", "--arc-type", "hold",
              "--out", str(tmp_path / "d"), "--dry-run"])
    assert p.returncode == 0
    assert "combinational" in p.stdout                     # reported, never dropped
