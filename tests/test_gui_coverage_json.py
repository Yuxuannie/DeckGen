"""Tests for gui._coverage_json forwarding the by_parity Demo-1 scoreboard
tally (core.coverage.build_coverage output) to the browser untouched,
alongside the pre-existing keys. Mirrors test_gui_run_api.py."""


def _fake_report():
    """Mimics the dict shape returned by core.coverage.build_coverage."""
    return {
        'summary': {'expected': 5, 'generated': 4, 'submitted': 0,
                     'generation_error': 1, 'skipped': 0, 'balanced': True},
        'by_category': {'unsupported_arc': 1},
        'by_parity': {'byte': 2, 'engine_extras': 1, 'diff': 1,
                       'no_golden': 1},
        'by_corner': {'ttgnp_0p800v_25c': {'generated': 4, 'submitted': 0,
                                            'error': 1, 'skipped': 0}},
        'matrix': {('CELL1', 'hold', 1, 1): {'ttgnp_0p800v_25c': 'generated'}},
        'triage': [{'arc_id': 'hold_CELL1_Q_rise_CP_rise_NO_CONDITION_1_1',
                    'category': 'unsupported_arc', 'reason': 'no template'}],
        'unaccounted': [],
    }


def test_coverage_json_forwards_by_parity():
    import gui
    out = gui._coverage_json(_fake_report())
    assert out['by_parity'] == {'byte': 2, 'engine_extras': 1, 'diff': 1,
                                 'no_golden': 1}


def test_coverage_json_keeps_existing_keys():
    import gui
    out = gui._coverage_json(_fake_report())
    assert out['summary']['expected'] == 5
    assert out['by_category'] == {'unsupported_arc': 1}
    assert out['by_corner'] == {
        'ttgnp_0p800v_25c': {'generated': 4, 'submitted': 0, 'error': 1,
                              'skipped': 0}}
    assert out['triage'] == [
        {'arc_id': 'hold_CELL1_Q_rise_CP_rise_NO_CONDITION_1_1',
         'category': 'unsupported_arc', 'reason': 'no template'}]
    assert out['matrix'] == [
        {'cell': 'CELL1', 'arc_type': 'hold', 'i1': 1, 'i2': 1,
         'states': {'ttgnp_0p800v_25c': 'generated'}}]
    assert out['unaccounted'] == []


def test_coverage_json_defaults_by_parity_when_absent():
    """Older reports (or callers) without by_parity should not error --
    forward an empty dict instead of KeyError."""
    import gui
    report = _fake_report()
    del report['by_parity']
    out = gui._coverage_json(report)
    assert out['by_parity'] == {}
