"""SCLD realism guard: parse a template.tcl-style `-when` conjunction into
{pin: 0|1}, and REFUSE (return None -> UNSUPPORTED-WHEN) anything that is not a
pure conjunction (contains OR). A tool that says "I can't read this one" keeps
trust; one that silently mis-parses an OR'd condition as a conjunction computes
the wrong covered region and false-flags a correct cell (the exact failure mode
/florin and /scld warned about).

This is decision-independent infrastructure for the region-equivalence verdict;
it does not depend on any cell's ground-truth function.
"""
from engine.whencond import parse_when_conjunction


class TestPureConjunction:
    def test_ampersand_form(self):
        # template.tcl delay-arc form, e.g. AIOI21 B arc
        assert parse_when_conjunction("A1&!A2") == {"A1": 1, "A2": 0}

    def test_space_form(self):
        # define_leakage form is space-separated
        assert parse_when_conjunction("!A1 !A2 B") == {"A1": 0, "A2": 0, "B": 1}

    def test_not_prefix_form(self):
        # arc-identifier-style notX negation must also be accepted
        assert parse_when_conjunction("notSE&SI") == {"SE": 0, "SI": 1}

    def test_empty_is_unconstrained(self):
        assert parse_when_conjunction("") == {}
        assert parse_when_conjunction("NO_CONDITION") == {}


class TestUnsupportedReturnsNone:
    def test_or_pipe_is_unsupported(self):
        # real kits write OR; must NOT be coerced into a conjunction
        assert parse_when_conjunction("A1|A2") is None

    def test_or_mixed_is_unsupported(self):
        assert parse_when_conjunction("A1&!A2 | B") is None

    def test_contradiction_is_unsupported(self):
        # same pin pinned to both values -> not a coherent conjunction
        assert parse_when_conjunction("A1&!A1") is None
