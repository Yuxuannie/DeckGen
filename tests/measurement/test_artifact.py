import os, json
from core.measurement.emit import load_grammar, _DEFAULT

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_committed_grammar_loads_and_is_ascii():
    g = load_grammar(_DEFAULT)
    assert g["version"] == 1 and g["entries"]
    raw = open(_DEFAULT, "rb").read()
    assert all(b < 128 for b in raw), "grammar JSON must be ASCII-only"
