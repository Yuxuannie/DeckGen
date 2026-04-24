"""Tests for MPW skip_this_arc logic (MCQC 0-mpw/qaTemplateMaker port)."""
import pytest
from core.mpw_skip import skip_this_arc


class TestSync2Removal:
    def test_sync2_q_removal_skipped(self):
        assert skip_this_arc(
            cell_name='SYNC2DFF',
            arc_type='removal',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])

    def test_sync2_q_hold_not_skipped(self):
        assert not skip_this_arc(
            cell_name='SYNC2DFF',
            arc_type='hold',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])


class TestSync3Removal:
    def test_sync3_q_removal_skipped(self):
        assert skip_this_arc(
            cell_name='SYNC3DFF',
            arc_type='removal',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])


class TestSync4Removal:
    def test_sync4_q_removal_skipped(self):
        assert skip_this_arc(
            cell_name='SYNC4DFF',
            arc_type='removal',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])


class TestNormalCells:
    def test_regular_dff_not_skipped(self):
        assert not skip_this_arc(
            cell_name='DFFQ1',
            arc_type='hold',
            rel_pin='CP', rel_pin_dir='rise',
            pin='D', pin_dir='fall',
            when='NO_CONDITION',
            probe_list=['Q'])

    def test_regular_combinational_not_skipped(self):
        assert not skip_this_arc(
            cell_name='AND2X1',
            arc_type='combinational',
            rel_pin='A', rel_pin_dir='rise',
            pin='Y', pin_dir='rise',
            when='NO_CONDITION',
            probe_list=['Y'])
