"""HG-T4 gate tests - reflex API for Verdandi.
Gate: fixture reflex set fires exactly on its patterns and no others;
latency measured and recorded; undeclared patterns cannot fire."""
from __future__ import annotations
import copy, json
from pathlib import Path
import pytest
from hugrgate.decision_server import DecisionServer
from hugrgate.reflex_api import ReflexError, ReflexRegistry
pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / 'campaign' / 'hg_t4_fixture_reflexes.json').read_text())
REPORT = json.loads((ROOT / 'campaign' / 'hg_t4_latency_report.json').read_text())

def _registry():
    reg = ReflexRegistry(consumer=FIXTURE['consumer'])
    for r in FIXTURE['reflexes']:
        reg.register(r['name'], r['action'], r['pattern'])
    return reg

def test_fixture_fires_exactly_on_declared_patterns():
    out = _registry().judge_stream(FIXTURE['events'])
    assert [r['fires'] for r in out['results']] == FIXTURE['expected_fires']
    assert out['total_fires'] == 5  # events 0,2,4,6,7 fire one each

def test_undeclared_patterns_cannot_fire():
    reg = _registry()
    for kind in ('security.login', 'unknown.thing', 'alarm.fire.extra'):
        res = reg.judge_one({'source': 'auth.service', 'kind': kind, 'payload': {}})
        assert res['fires'] == []
    empty = ReflexRegistry()
    res = empty.judge_one({'source': 'sensor.hall', 'kind': 'alarm.fire', 'payload': {}})
    assert res['fires'] == [] and res['verdicts'] == []

def test_every_verdict_carries_basis_digest_and_latency():
    for res in _registry().judge_stream(FIXTURE['events'])['results']:
        assert res['latency_ms'] >= 0
        for v in res['verdicts']:
            assert v['basis'] and v['payload_digest'] and v['slice'] == 'HG-T4'
            assert v['deterministic'] is True and v['latency_ms'] == res['latency_ms']
            assert (v['basis'].startswith('declared:') or v['basis'].startswith('schema:'))

def test_invalid_event_fires_nothing_with_schema_basis():
    res = _registry().judge_one({'source': 'sensor.hall', 'payload': {}})
    assert res['fires'] == []
    assert all(v['basis'].startswith('schema:') for v in res['verdicts'])

def test_registration_validation_refuses_undeclared_catchalls():
    reg = ReflexRegistry()
    with pytest.raises(ReflexError):
        reg.register('bad', 'act', {})
    with pytest.raises(ReflexError):
        reg.register('bad', 'act', {'kind': '*'})
    with pytest.raises(ReflexError):
        reg.register('bad', '', {'kind': 'x.y'})
    reg.register('ok', 'act', {'kind': 'x.y'})
    with pytest.raises(ReflexError):
        reg.register('ok', 'act2', {'kind': 'x.z'})

def test_deterministic_and_unregister():
    reg = _registry()
    ev = copy.deepcopy(FIXTURE['events'][0])
    a, b = reg.judge_one(ev), reg.judge_one(copy.deepcopy(ev))
    strip = lambda r: [{k: v for k, v in x.items() if k != 'latency_ms'} for x in r['verdicts']]
    assert strip(a) == strip(b) and a['fires'] == b['fires'] == ['evacuate-hall']
    reg.unregister('hall-fire')
    assert reg.judge_one(ev)['fires'] == []

def test_latency_report_recorded_and_fast():
    assert REPORT['slice'] == 'HG-T4' and REPORT['expected_table_match'] is True
    assert REPORT['judgments'] >= 1000
    assert REPORT['latency_ms']['median'] < 5.0  # decision-runtime: sub-5ms median

def test_server_reflex_endpoints_end_to_end():
    srv = DecisionServer(host='127.0.0.1', port=0)
    for r in FIXTURE['reflexes']:
        out = srv.register_reflex(r)
        assert out['registered']['name'] == r['name']
    assert len(srv.list_reflexes()['reflexes']) == 4
    out = srv.judge_reflexes({'events': FIXTURE['events']})
    assert [r['fires'] for r in out['results']] == FIXTURE['expected_fires']


def test_where_comparison_conditions_judge_numeric_fields():
    reg = ReflexRegistry(consumer='verdandi')
    reg.register('spike-notify', 'notify', {'source': 'wyrd', 'where': {'salience': {'gte': 0.8}}})
    assert reg.judge_one({'source': 'wyrd', 'kind': 'nerve.note', 'payload': {'salience': 0.95}})['fires'] == ['notify']
    res = reg.judge_one({'source': 'wyrd', 'kind': 'nerve.note', 'payload': {'salience': 0.3}})
    assert res['fires'] == [] and 'fails gte' in res['verdicts'][0]['basis']
    res = reg.judge_one({'source': 'wyrd', 'kind': 'nerve.note', 'payload': {'salience': 'high'}})
    assert res['fires'] == [] and 'not a number' in res['verdicts'][0]['basis']
    res = reg.judge_one({'source': 'wyrd', 'kind': 'nerve.note', 'payload': {}})
    assert res['fires'] == [] and 'has no' in res['verdicts'][0]['basis']

def test_where_only_pattern_is_declared_not_catchall():
    reg = ReflexRegistry(consumer='verdandi')
    reg.register('noisy-shed', 'shed', {'where': {'noise': {'gte': 0.9}}})
    assert reg.judge_one({'source': 'chatter', 'kind': 'nerve.note', 'payload': {'noise': 0.97}})['fires'] == ['shed']
    assert reg.judge_one({'source': 'chatter', 'kind': 'nerve.note', 'payload': {'noise': 0.4}})['fires'] == []
    with pytest.raises(ReflexError):
        reg.register('bad', 'act', {'where': {}})

def test_comparison_objects_are_validated():
    reg = ReflexRegistry()
    for bad in ({'gte': 'high'}, {'approx': 1.0}, {}, {'gte': True}):
        with pytest.raises(ReflexError):
            reg.register('bad', 'act', {'kind': 'x.y', 'where': {'level': bad}})
