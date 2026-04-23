"""Tests for core.parsers.corner - PVT corner name parser."""
import pytest
from core.parsers.corner import parse_corner_name, parse_corner_list


# ---------------------------------------------------------------------------
# parse_corner_name
# ---------------------------------------------------------------------------

class TestBasicCorners:
    @pytest.mark.parametrize('name,proc,vdd,temp', [
        ('ssgnp_0p450v_m40c',  'ssgnp', '0.450', '-40'),
        ('ttgnp_0p800v_25c',   'ttgnp', '0.800', '25'),
        ('ffgnp_0p900v_125c',  'ffgnp', '0.900', '125'),
        ('tt_0p750v_m10c',     'tt',    '0.750', '-10'),
        ('ss_0p500v_0c',       'ss',    '0.500', '0'),
    ])
    def test_parse(self, name, proc, vdd, temp):
        r = parse_corner_name(name)
        assert r is not None
        assert r['process'] == proc
        assert r['vdd'] == vdd
        assert r['temperature'] == temp

    def test_raw_preserved(self):
        r = parse_corner_name('ssgnp_0p450v_m40c')
        assert r['raw'] == 'ssgnp_0p450v_m40c'


class TestNegativeTemperature:
    def test_m40(self):
        r = parse_corner_name('ssgnp_0p450v_m40c')
        assert r['temperature'] == '-40'

    def test_m10(self):
        r = parse_corner_name('tt_0p750v_m10c')
        assert r['temperature'] == '-10'

    def test_m273(self):
        r = parse_corner_name('ss_0p300v_m273c')
        assert r['temperature'] == '-273'


class TestPositiveTemperature:
    def test_zero(self):
        r = parse_corner_name('tt_0p800v_0c')
        assert r['temperature'] == '0'

    def test_25(self):
        r = parse_corner_name('ttgnp_0p800v_25c')
        assert r['temperature'] == '25'

    def test_125(self):
        r = parse_corner_name('ffgnp_0p900v_125c')
        assert r['temperature'] == '125'


class TestVoltageFormats:
    def test_three_decimal_places(self):
        r = parse_corner_name('ss_0p450v_25c')
        assert r['vdd'] == '0.450'

    def test_single_decimal_place(self):
        r = parse_corner_name('tt_0p8v_25c')
        assert r['vdd'] == '0.8'


class TestInvalidCorners:
    def test_empty(self):
        assert parse_corner_name('') is None

    def test_whitespace(self):
        assert parse_corner_name('   ') is None

    def test_no_voltage_suffix(self):
        assert parse_corner_name('ssgnp_0p450_m40c') is None

    def test_no_temp_suffix(self):
        assert parse_corner_name('ssgnp_0p450v_m40') is None

    def test_plain_text(self):
        assert parse_corner_name('fast') is None

    def test_missing_underscore(self):
        assert parse_corner_name('ssgnp0p450vm40c') is None


# ---------------------------------------------------------------------------
# parse_corner_list
# ---------------------------------------------------------------------------

class TestParseCornerList:
    def test_comma_separated(self):
        corners = parse_corner_list('ssgnp_0p450v_m40c, ffgnp_0p900v_125c')
        assert len(corners) == 2
        assert corners[0]['process'] == 'ssgnp'
        assert corners[1]['process'] == 'ffgnp'

    def test_newline_separated(self):
        corners = parse_corner_list('ssgnp_0p450v_m40c\nttgnp_0p800v_25c')
        assert len(corners) == 2

    def test_three_corners(self):
        text = 'ssgnp_0p450v_m40c, ttgnp_0p800v_25c, ffgnp_0p900v_125c'
        assert len(parse_corner_list(text)) == 3

    def test_skips_invalid(self):
        corners = parse_corner_list('ssgnp_0p450v_m40c, garbage, ffgnp_0p900v_125c')
        assert len(corners) == 2

    def test_empty(self):
        assert parse_corner_list('') == []

    def test_whitespace_trimmed(self):
        corners = parse_corner_list('  ssgnp_0p450v_m40c  ')
        assert len(corners) == 1
