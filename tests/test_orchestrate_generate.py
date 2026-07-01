import json
import os
import shutil

from tools.scan_collateral import build_manifest
from core.orchestrate import (generate, generate_one, categorize, read_ledger)
from core.collateral import CollateralStore
from core.measurement.emit import load_grammar

FIXTURE_ROOT = os.path.join(os.path.dirname(__file__), 'fixtures', 'collateral')
NODE = 'N2P_v1.0'
LIB = 'test_lib'
CORNER = 'ssgnp_0p450v_m40c_cworst_CCworst_T'


def _setup(dest):
    shutil.copytree(os.path.join(FIXTURE_ROOT, NODE, LIB),
                    os.path.join(dest, NODE, LIB))
    build_manifest(dest, NODE, LIB)
    return dest


def test_categorize_maps_known_substrings():
    assert categorize('this is a combinational cell') == 'combinational_cell'
    assert categorize('latch not supported') == 'latch_unsupported'
    assert categorize('P1 not proven for arc') == 'p1_unproven'
    assert categorize('SeqScope: depth 7 beyond corpus') == 'out_of_corpus'
    assert categorize('could not parse .subckt') == 'parse_fail'
    assert categorize('no grammar entry') == 'no_grammar'
    assert categorize('totally novel failure') == 'unsupported_arc'


def test_generate_over_fixture_balances_and_writes_ledger(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    res = generate(root, NODE, LIB, out,
                   scope={'table_points': [(1, 1)]})
    cov = res['coverage']['summary']
    # 2 arcs at (1,1): both accounted, nothing dropped
    assert cov['expected'] == 2
    assert cov['generated'] + cov['generation_error'] + cov['skipped'] == 2
    assert cov['balanced'] is True
    # ledger written, one line per work item
    rows = read_ledger(os.path.join(out, 'ledger.ndjson'))
    assert len(rows) == 2
    assert os.path.isfile(os.path.join(out, 'coverage.ndjson'))
    assert os.path.isfile(os.path.join(out, 'coverage.html'))
    # no bsub emitted during generation phase (confirm gate)
    lsf_dir = os.path.join(out, 'lsf')
    assert not (os.path.isdir(lsf_dir) and any(
        f.endswith('.bsub') for f in os.listdir(lsf_dir)))
    assert all(r['state'] != 'submitted' for r in rows)


def test_generate_one_combinational_writes_deck(tmp_path):
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    os.makedirs(out, exist_ok=True)
    store = CollateralStore(root, NODE, LIB, skip_autoscan=True)
    import json as _j
    manifest = _j.load(open(os.path.join(root, NODE, LIB, 'manifest.json'),
                            encoding='ascii'))
    from core.orchestrate import discover
    tcl = {c: store.get_corner(c)['template_tcl'] for c in manifest['corners']}
    items = discover(manifest, tcl,
                     scope={'arcs_per_cell': 1, 'table_points': [(1, 1)]})
    row = generate_one(items[0], NODE, LIB, root, load_grammar(), out)
    assert row['state'] in ('generated', 'generation_error')
    if row['state'] == 'generated':
        assert os.path.isfile(row['deck_path'])
        assert row['arc_id'].startswith('combinational_DFFQ1_')


def test_generate_error_row_is_named_never_raises(tmp_path):
    # A bogus work item (arc absent from template.tcl) must produce a
    # generation_error row, not raise.
    root = _setup(os.path.join(str(tmp_path), 'col'))
    out = os.path.join(str(tmp_path), 'run')
    os.makedirs(out, exist_ok=True)
    bogus = {
        'cell': 'DFFQ1', 'arc_type': 'hold', 'i1': 1, 'i2': 1,
        'corner': CORNER, 'arc_id': 'hold_DFFQ1_Q_fall_XX_rise_NO_CONDITION_1_1',
        'skip': None,
        'arc': {'cell': 'DFFQ1', 'arc_type': 'hold', 'pin': 'D',
                'pin_dir': 'fall', 'rel_pin': 'XX', 'rel_pin_dir': 'rise',
                'when': 'NO_CONDITION', 'lit_when': 'NO_CONDITION',
                'probe_list': ['Q'], 'vector': ''},
    }
    row = generate_one(bogus, NODE, LIB, root, load_grammar(), out)
    assert row['state'] == 'generation_error'
    assert row['category']  # non-empty category
    assert row['reason']
