# tests/test_orchestrate_sidecar_parity.py
#
# generate_one's post-assembly duties (G0 sidecar + Demo-1 parity verdict),
# isolated with monkeypatches so they are covered even where the shared
# fixture lib produces refusals only. generate_one imports resolver/assembler/
# build_deck inside the function body, so patching the source modules works.
import json
import os

import core.deck_assemble
import core.deck_builder
import core.resolver
from core.orchestrate import generate_one
from core.measurement.emit import load_grammar

_DECK = "*** title ***\n* Pin definitions\nVSE SE 0 'vss_value'\n.end\n"


def _work_item():
    return {'cell': 'CELLX', 'arc_type': 'combinational', 'i1': 1, 'i2': 1,
            'corner': 'ssgnp_0p450v_m40c_cworst_CCworst_T',
            'arc_id': 'combinational_CELLX_ZN_rise_A1_rise_NO_CONDITION_1_1',
            'skip': None,
            'arc': {'cell': 'CELLX', 'arc_type': 'combinational',
                    'pin': 'ZN', 'pin_dir': 'rise', 'rel_pin': 'A1',
                    'rel_pin_dir': 'rise', 'when': '',
                    'probe_list': ['ZN']}}


def _patch(monkeypatch, tmp_path, template_path='', golden=None):
    netlist = tmp_path / 'CELLX.spi'
    netlist.write_text('.subckt CELLX A1 ZN VDD VSS\n.ends\n',
                       encoding='ascii')

    def fake_resolve(**kw):
        info = {'NETLIST_PATH': str(netlist), 'VDD_VALUE': '0.45',
                'TEMPERATURE': '-40', 'INDEX_1_VALUE': '1n',
                'INDEX_2_VALUE': '1f', 'NETLIST_PINS': 'A1 ZN VDD VSS'}
        if template_path:
            info['TEMPLATE_DECK_PATH'] = template_path
        return info
    monkeypatch.setattr(core.resolver, 'resolve_all_from_collateral',
                        fake_resolve)

    def fake_assemble(arc_info, netlist_src, grammar, engine_cache=None):
        return {'status': 'OK', 'deck_text': _DECK, 'kit_match': True,
                'bias': {'SE': 0}, 'error': None,
                'explain': {'selection': {'arc_class': 'combinational'},
                            'engine': {'bias': {'SE': 0}},
                            'collateral': {},
                            'audit': {'lines': []}}}
    monkeypatch.setattr(core.deck_assemble, 'assemble_combinational',
                        fake_assemble)

    if golden is not None:
        monkeypatch.setattr(core.deck_builder, 'build_deck',
                            lambda *a, **k: golden)


def _run(tmp_path):
    out = str(tmp_path / 'run')
    row = generate_one(_work_item(), 'N2P_v1.0', 'test_lib',
                       str(tmp_path), load_grammar(), out)
    return row, out


def test_sidecar_written_next_to_deck_with_identity(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    row, out = _run(tmp_path)
    assert row['state'] == 'generated'
    side = row['deck_path'][:-3] + '.explain.json'
    assert os.path.isfile(side)
    ex = json.load(open(side, encoding='ascii'))
    assert ex['arc_id'] == row['arc_id']
    assert ex['corner'] == row['corner']
    assert (ex['i1'], ex['i2']) == (1, 1)
    assert ex['parity_vs_golden'] == row['parity']
    assert ex['selection']['arc_class'] == 'combinational'


def test_parity_no_golden_when_kit_has_no_template(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)             # no TEMPLATE_DECK_PATH
    row, _ = _run(tmp_path)
    assert row['parity'] == 'no_golden'
    assert row['kit_match'] is True


def test_parity_byte_when_golden_matches(monkeypatch, tmp_path):
    tpl = tmp_path / 'golden.sp'
    tpl.write_text('placeholder', encoding='ascii')
    _patch(monkeypatch, tmp_path, template_path=str(tpl),
           golden=[_DECK])                    # ''.join equals deck bytes
    row, _ = _run(tmp_path)
    assert row['parity'] == 'byte'


def test_parity_engine_extras_when_only_vlines_added(monkeypatch, tmp_path):
    tpl = tmp_path / 'golden.sp'
    tpl.write_text('placeholder', encoding='ascii')
    golden = ["*** title ***\n* Pin definitions\n.end\n"]   # no VSE line
    _patch(monkeypatch, tmp_path, template_path=str(tpl), golden=golden)
    row, _ = _run(tmp_path)
    assert row['parity'] == 'engine_extras'


def test_parity_diff_when_golden_disagrees(monkeypatch, tmp_path):
    tpl = tmp_path / 'golden.sp'
    tpl.write_text('placeholder', encoding='ascii')
    _patch(monkeypatch, tmp_path, template_path=str(tpl),
           golden=["*** other title ***\n.end\n"])
    row, _ = _run(tmp_path)
    assert row['parity'] == 'diff'


def test_parity_golden_error_never_fails_the_row(monkeypatch, tmp_path):
    tpl = tmp_path / 'golden.sp'
    tpl.write_text('placeholder', encoding='ascii')
    _patch(monkeypatch, tmp_path, template_path=str(tpl))
    def boom(*a, **k):
        raise RuntimeError('golden flow exploded')
    monkeypatch.setattr(core.deck_builder, 'build_deck', boom)
    row, _ = _run(tmp_path)
    assert row['state'] == 'generated'
    assert row['parity'].startswith('golden_error:')
    assert 'exploded' in row['parity']
