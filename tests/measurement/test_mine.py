import os
from core.measurement.mine import mine

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_mine_delay_corpus():
    g = mine(os.path.join(_REPO, "templates/N2P_v1.0/delay"))
    assert g["version"] == 1
    assert len(g["entries"]) >= 1
    # every entry has a key, recipe_lines, provenance
    for e in g["entries"]:
        assert set(e["key"]) >= {"arc_type", "rel_dir", "other_dir", "cluster_tag"}
        assert e["recipe_lines"] and e["provenance"]
    # all 4 delay templates are accounted for in provenance
    provs = [p for e in g["entries"] for p in e["provenance"]]
    assert len(provs) == 4
    assert len(set(provs)) == 4


def test_mine_dedups_identical_recipes():
    g = mine(os.path.join(_REPO, "templates/N2P_v1.0/mpw"))
    provs = [p for e in g["entries"] for p in e["provenance"]]
    assert len(provs) == 63                # every mpw template accounted for
    # entries <= templates (dedup may collapse some)
    assert len(g["entries"]) <= 63
