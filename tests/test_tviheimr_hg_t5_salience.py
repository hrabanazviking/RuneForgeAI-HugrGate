"""HG-T5 gate tests - Aurelia sensation-stream salience profile.
Gate: on Aurelia's recorded fixture stream, salience verdicts match her expected table; noise rejection rate and miss rate both reported honestly. Consumed event schema and emitted verdict schema are Aurelia's own (AU-T1 / AU-T2, her house defines them)."""
from __future__ import annotations
import copy, json, re
from pathlib import Path
from hugrgate.decision_server import DecisionServer
from hugrgate.salience_profile import (CRITICAL_FLOOR, HIGH_FLOOR, JUDGE_ID, NOISE_FLOOR, SALIENT_FLOOR, SalienceProfile, record_digest)
ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / 'campaign' / 'hg_t5_fixture_stream.json').read_text())
REPORT = json.loads((ROOT / 'campaign' / 'hg_t5_salience_report.json').read_text())
EVENTS = FIXTURE['events']; EXPECTED = FIXTURE['expected']
_DIGEST_RE = re.compile(r'^[0-9a-f]{64}$')

def test_fixture_stream_matches_aurelia_expected_table():
    out = SalienceProfile().judge_stream(EVENTS)
    assert out['events'] == len(EVENTS) == 19
    for v, exp in zip(out['verdicts'], EXPECTED):
        assert (v['salient'], v['disposition'], v['authenticity'], v['urgency'], v['schema_valid']) == (exp['salient'], exp['disposition'], exp['authenticity'], exp['urgency'], exp['schema_valid'])
        assert v['basis'].strip() and v['judge_id'] == JUDGE_ID
        assert v['schema_version'] == 1 and v['slice'] == 'HG-T5'

def test_verdicts_are_aurelia_au_t2_schema_compatible():
    for ev, v in zip(EVENTS, SalienceProfile().judge_stream(EVENTS)['verdicts']):
        assert v['disposition'] in ('surface', 'settle')
        assert v['authenticity'] in ('genuine', 'noise')
        assert isinstance(v['urgency'], int) and 0 <= v['urgency'] <= 3
        assert bool(v['salient']) == (v['disposition'] == 'surface')
        if v['schema_valid']:
            assert v['event_digest'] == ev['digest']
            assert _DIGEST_RE.match(v['event_digest'])

def test_first_eight_events_are_aurelia_au_t2_recorded_stream():
    recorded = [('mood.valence', 0.90), ('drive.rest', 0.60), ('mood.arousal', 0.30), ('body.tension', 0.10), ('drive.hunger', 0.02), ('mood.valence', 0.50), ('body.temperature', 0.20), ('drive.rest', 0.049)]
    assert [(e['kind'], e['intensity']) for e in EVENTS[:8]] == recorded
    for e in EVENTS[:16]:
        sec, chan = e['kind'].split('.', 1)
        rec = {'section': sec, 'channel': chan, 'before': e['before'], 'after': e['after'], 'timestamp': e['timestamp']}
        assert record_digest(rec) == e['digest']

def test_boundary_intensities_follow_aurelia_floors():
    p = SalienceProfile()
    def mk(i):
        return {'schema_version': 1, 'kind': 'a.x', 'intensity': i, 'source': 's', 'timestamp': 1.0, 'digest': 'a' * 64}
    assert p.judge_one(mk(CRITICAL_FLOOR))['urgency'] == 3
    assert p.judge_one(mk(HIGH_FLOOR))['urgency'] == 2
    assert p.judge_one(mk(SALIENT_FLOOR))['urgency'] == 1
    assert p.judge_one(mk(NOISE_FLOOR))['authenticity'] == 'genuine'
    assert p.judge_one(mk(0.049))['authenticity'] == 'noise'
    assert p.judge_one(mk(0.0))['disposition'] == 'settle'

def test_noise_rejection_and_miss_rates_reported_honestly():
    assert REPORT['slice'] == 'HG-T5' and REPORT['judge_id'] == JUDGE_ID
    assert REPORT['events'] == 19 and REPORT['schema_valid_events'] == 16
    assert REPORT['table_matches'] == 16
    assert REPORT['expected_noise_events'] == 3
    assert REPORT['noise_rejection_rate'] == 1.0
    assert REPORT['expected_surface_events'] == 9
    assert REPORT['miss_rate'] == 0.0
    live = SalienceProfile().evaluate(EVENTS, EXPECTED)
    for k in ('table_matches', 'noise_rejection_rate', 'miss_rate', 'expected_noise_events', 'expected_surface_events'):
        assert live[k] == REPORT[k]

def test_invalid_events_get_schema_verdicts_not_drops():
    out = SalienceProfile().judge_stream(EVENTS)
    assert out['schema_invalid'] == 3
    for v in out['verdicts']:
        if not v['schema_valid']:
            assert v['basis'].startswith('schema:')
            assert v['disposition'] == 'settle' and v['urgency'] == 0

def test_deterministic_identical_events_identical_verdicts():
    p = SalienceProfile()
    assert p.judge_stream(copy.deepcopy(EVENTS))['verdicts'] == p.judge_stream(copy.deepcopy(EVENTS))['verdicts']

def test_server_salience_endpoint_end_to_end():
    srv = DecisionServer(host='127.0.0.1', port=0)
    out = srv.judge_salience({'events': EVENTS, 'expected': EXPECTED})
    assert out['accepted'] == 19 and out['schema_invalid'] == 3
    assert [(v['disposition'], v['authenticity'], v['urgency']) for v in out['verdicts']] == [(e['disposition'], e['authenticity'], e['urgency']) for e in EXPECTED]
    assert out['report']['noise_rejection_rate'] == 1.0
    assert out['report']['miss_rate'] == 0.0
