"""Ground truth test for AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD.

Verifies that the ALAPI parser produces exactly 10 combinational delay arcs
matching the known template.tcl structure for this cell. See PROJECT_NOTES.md
section 2.4 for the full arc table.

Cell function: ZN = B * !(A1*A2)
Pinlist: A1 A2 B ZN
"""

import os
import tempfile
import pytest

from core.parsers.template_tcl import parse_template_tcl_full


# Exact template.tcl fragment for AIOI21.
# 24 define_arc total: 14 hidden + 10 combinational (no -type).
AIOI21_TEMPLATE = r"""
define_template -type delay \
    -index_1 {0.0019 0.5336 1.5971 3.7240 7.9962} \
    -index_2 {0.000001 0.001 0.003 0.005 0.006270} \
    delay_template_5x5

define_template -type constraint \
    -index_1 {0.0019 0.5336 1.5971 3.7240 7.9962} \
    -index_2 {0.0019 0.5336 1.5971 3.7240 7.9962} \
    constraint_template_5x5

if {[ALAPI_active_cell "AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD"]} {
define_cell \
    -input { A1 A2 B } \
    -output { ZN } \
    -pinlist { A1 A2 B ZN } \
    -delay delay_template_5x5 \
    -user_arcs_only \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_leakage -when "!A1 !A2 !B !ZN" AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
define_leakage -when "!A1 !A2 B ZN"   AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
define_leakage -when "!A1 A2 !B !ZN"  AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
define_leakage -when "!A1 A2 B ZN"    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
define_leakage -when "A1 !A2 !B !ZN"  AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
define_leakage -when "A1 !A2 B ZN"    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
define_leakage -when "A1 A2 !B ZN"    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
define_leakage -when "A1 A2 B ZN"     AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A2&B" \
    -vector {Rxxх} \
    -pin A1 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A2&!B" \
    -vector {Rxxx} \
    -pin A1 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "A2&B" \
    -vector {Rxxx} \
    -pin A1 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A2&B" \
    -vector {Fxxx} \
    -pin A1 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A2&!B" \
    -vector {Fxxx} \
    -pin A1 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "A2&B" \
    -vector {Fxxx} \
    -pin A1 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A1&B" \
    -vector {xRxx} \
    -pin A2 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A1&!B" \
    -vector {xRxx} \
    -pin A2 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "A1&B" \
    -vector {xRxx} \
    -pin A2 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A1&B" \
    -vector {xFxx} \
    -pin A2 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "!A1&!B" \
    -vector {xFxx} \
    -pin A2 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "A1&B" \
    -vector {xFxx} \
    -pin A2 \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "A1&A2" \
    -vector {xxRx} \
    -pin B \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -type hidden \
    -when "A1&A2" \
    -vector {xxFx} \
    -pin B \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -related_pin A1 \
    -vector {FxxR} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -related_pin A1 \
    -vector {RxxF} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -related_pin A2 \
    -vector {xFxR} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -related_pin A2 \
    -vector {xRxF} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -when "A1&!A2" \
    -related_pin B \
    -vector {xxRR} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -when "A1&!A2" \
    -related_pin B \
    -vector {xxFF} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -when "!A1&A2" \
    -related_pin B \
    -vector {xxRR} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -when "!A1&A2" \
    -related_pin B \
    -vector {xxFF} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -when "!A1&!A2" \
    -related_pin B \
    -vector {xxRR} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD

define_arc \
    -when "!A1&!A2" \
    -related_pin B \
    -vector {xxFF} \
    AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD
}
"""

CELL = 'AIOI21M1LIDHMZD4BWP130HPNPN3P48CPD'

# Ground truth: 10 combinational delay arcs (related_pin, when, vector)
# Note: parser strips {} braces from vector values via Tcl tokenizer
EXPECTED_ARCS = [
    ('A1', 'NO_CONDITION', 'FxxR'),
    ('A1', 'NO_CONDITION', 'RxxF'),
    ('A2', 'NO_CONDITION', 'xFxR'),
    ('A2', 'NO_CONDITION', 'xRxF'),
    ('B',  'A1&!A2',      'xxRR'),
    ('B',  'A1&!A2',      'xxFF'),
    ('B',  '!A1&A2',      'xxRR'),
    ('B',  '!A1&A2',      'xxFF'),
    ('B',  '!A1&!A2',     'xxRR'),
    ('B',  '!A1&!A2',     'xxFF'),
]

# Ground truth: 5 .lib timing arc groups (related_pin, when)
EXPECTED_GROUPS = [
    ('A1', 'NO_CONDITION'),   # 2 arcs: rise + fall
    ('A2', 'NO_CONDITION'),   # 2 arcs: rise + fall
    ('B',  'A1&!A2'),         # 2 arcs: rise + fall
    ('B',  '!A1&A2'),         # 2 arcs: rise + fall
    ('B',  '!A1&!A2'),        # 2 arcs: rise + fall
]


@pytest.fixture
def parsed():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tcl', delete=False) as f:
        f.write(AIOI21_TEMPLATE)
        tmp = f.name
    try:
        yield parse_template_tcl_full(tmp)
    finally:
        os.unlink(tmp)


class TestAIOI21CellParsing:
    def test_cell_found(self, parsed):
        assert CELL in parsed['cells']

    def test_cell_output_pins(self, parsed):
        assert parsed['cells'][CELL]['output_pins'] == ['ZN']

    def test_cell_delay_template(self, parsed):
        assert parsed['cells'][CELL]['delay_template'] == 'delay_template_5x5'


class TestAIOI21ArcCount:
    def test_exactly_10_arcs(self, parsed):
        arcs = [a for a in parsed['arcs'] if a['cell'] == CELL]
        assert len(arcs) == 10, (
            f"Expected 10 combinational delay arcs, got {len(arcs)}: "
            f"{[(a['arc_type'], a['rel_pin'], a['when']) for a in arcs]}")

    def test_all_combinational(self, parsed):
        arcs = [a for a in parsed['arcs'] if a['cell'] == CELL]
        for a in arcs:
            assert a['arc_type'] == 'combinational', (
                f"Expected combinational, got {a['arc_type']} for "
                f"rel_pin={a['rel_pin']} vector={a['vector']}")

    def test_no_hidden_arcs(self, parsed):
        arcs = [a for a in parsed['arcs'] if a['cell'] == CELL]
        hidden = [a for a in arcs if a['arc_type'] == 'hidden']
        assert len(hidden) == 0, "hidden arcs should be filtered out"


class TestAIOI21ArcDetails:
    def test_exact_arc_tuples(self, parsed):
        """Each (related_pin, when, vector) must match ground truth."""
        arcs = [a for a in parsed['arcs'] if a['cell'] == CELL]
        actual = sorted(
            (a['rel_pin'], a['when'], a['vector']) for a in arcs)
        expected = sorted(EXPECTED_ARCS)
        assert actual == expected, (
            f"Arc tuples mismatch.\n"
            f"Missing: {set(expected) - set(actual)}\n"
            f"Extra:   {set(actual) - set(expected)}")

    def test_a1_arcs_unconditional(self, parsed):
        arcs = [a for a in parsed['arcs']
                if a['cell'] == CELL and a['rel_pin'] == 'A1']
        assert len(arcs) == 2
        for a in arcs:
            assert a['when'] == 'NO_CONDITION'

    def test_a2_arcs_unconditional(self, parsed):
        arcs = [a for a in parsed['arcs']
                if a['cell'] == CELL and a['rel_pin'] == 'A2']
        assert len(arcs) == 2
        for a in arcs:
            assert a['when'] == 'NO_CONDITION'

    def test_b_arcs_conditional(self, parsed):
        arcs = [a for a in parsed['arcs']
                if a['cell'] == CELL and a['rel_pin'] == 'B']
        assert len(arcs) == 6
        whens = sorted(a['when'] for a in arcs)
        assert whens == sorted([
            'A1&!A2', 'A1&!A2',
            '!A1&A2', '!A1&A2',
            '!A1&!A2', '!A1&!A2',
        ])


class TestAIOI21Grouping:
    def test_5_groups(self, parsed):
        """Arcs should form 5 .lib timing arc groups by (related_pin, when)."""
        arcs = [a for a in parsed['arcs'] if a['cell'] == CELL]
        groups = set((a['rel_pin'], a['when']) for a in arcs)
        assert groups == set(EXPECTED_GROUPS), (
            f"Expected 5 groups, got {len(groups)}: {sorted(groups)}")

    def test_each_group_has_2_arcs(self, parsed):
        """Each group (= .lib timing arc) has exactly 2 arcs (rise + fall)."""
        arcs = [a for a in parsed['arcs'] if a['cell'] == CELL]
        from collections import Counter
        counts = Counter((a['rel_pin'], a['when']) for a in arcs)
        for group, count in counts.items():
            assert count == 2, (
                f"Group {group} has {count} arcs, expected 2 (rise+fall)")
