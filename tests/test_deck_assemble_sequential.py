import os

import pytest

from core.deck_assemble import _seq_cluster_tag, SeqScope


def test_hold_family_depth_mapping():
    assert _seq_cluster_tag("hold", 1, "fall") == ("CP.syncx.D", "fall", "rise")
    assert _seq_cluster_tag("hold", 2, "fall") == ("CP.sync2.D", "fall", "rise")
    assert _seq_cluster_tag("hold", 6, "fall") == ("CP.sync6.D", "fall", "rise")


def test_mpw_family_depth_mapping():
    assert _seq_cluster_tag("mpw", 1, "rise") == ("CPN", "rise", "fall")
    assert _seq_cluster_tag("mpw", 3, "fall") == ("sync3.CP", "fall", "rise")
    assert _seq_cluster_tag("mpw", 3, "rise") == ("sync3.CP", "rise", "fall")


def test_depth_beyond_corpus_raises_named_scope():
    with pytest.raises(SeqScope) as e:
        _seq_cluster_tag("hold", 7, "fall")
    assert "7" in str(e.value) and "6" in str(e.value)
    with pytest.raises(SeqScope):
        _seq_cluster_tag("mpw", 0, "rise")


def test_unknown_family_raises():
    with pytest.raises(SeqScope):
        _seq_cluster_tag("removal", 2, "rise")
