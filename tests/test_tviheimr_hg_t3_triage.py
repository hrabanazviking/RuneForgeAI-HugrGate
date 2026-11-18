"""HG-T3 gate tests - event-stream triage profile.
Gate: recorded fixture stream triaged end-to-end; verdicts match the
expected table; every verdict carries its basis; nothing dropped
silently - shedding is a verdict, logged like any other."""
from __future__ import annotations
import copy, json
from pathlib import Path
import pytest
from hugrgate.decision_server import DecisionServer
from hugrgate.triage_profile import TriageProfile, payload_digest, triage_stream
pytestmark = pytest.mark.integration
FIXTURE = json.loads((Path(__file__).resolve().parent.parent / 'campaign' / 'hg_t3_fixture_stream.json').read_text())

def test_fixture_stream_matches_expected_table():
    verdicts = triage_stream(FIXTURE['events'])
    assert len(verdicts) == len(FIXTURE['events']) == len(FIXTURE['expected'])
    for v, exp in zip(verdicts, FIXTURE['expected']):
        assert v['urgency'] == exp['urgency'], v
        assert v['route'] == exp['route'], v
        assert v['escalate'] == exp['escalate'], v

def test_every_verdict_carries_basis_and_digest():
    for v in triage_stream(FIXTURE['events']):
        assert v['basis'] and isinstance(v['basis'], str)
        assert v['payload_digest']
        assert v['deterministic'] is True and v['model_used'] is False
        assert v['slice'] == 'HG-T3'

def test_nothing_dropped_silently_shed_is_a_verdict():
    verdicts = triage_stream(FIXTURE['events'])
    shed = [v for v in verdicts if v['route'] == 'shed']
    assert len(shed) == 3  # duplicate + missing source + bad time
    assert [v['index'] for v in shed] == [9, 10, 11]
    assert 'duplicate' in shed[0]['basis']
    assert 'schema' in shed[1]['basis'] and 'schema' in shed[2]['basis']

def test_deterministic_identical_events_identical_verdicts():
    ev = {'source':'s','kind':'system.failure','time':'2026-11-18T00:00:00Z','payload':{'x':1}}
    a = TriageProfile().triage_one(copy.deepcopy(ev))
    b = TriageProfile().triage_one(copy.deepcopy(ev))
    assert a == b

def test_model_in_loop_is_declared_in_basis():
    prof = TriageProfile(model=lambda e: 'high', model_name='fake-model')
    v = prof.triage_one({'source':'s','kind':'mystery.event','time':'2026-11-18T00:00:00Z','payload':{'detail':'something happened'}})
    assert v['model_used'] is True and v['deterministic'] is False
    assert v['basis'].startswith('model:fake-model')
    # settled cases never consult the model
    v2 = prof.triage_one({'source':'s','kind':'alarm.fire','time':'2026-11-18T00:00:00Z','payload':{}})
    assert v2['model_used'] is False and v2['basis'].startswith('rules:')

def test_payload_digest_is_stable_and_schema_fields():
    assert payload_digest({'b':1,'a':2}) == payload_digest({'a':2,'b':1})
    assert TriageProfile().validate({'source':'s','kind':'k','time':'2026-11-18T00:00:00Z','payload':{}}) == []
    assert TriageProfile().validate({'kind':'k'}) != []

def test_server_triage_endpoint_end_to_end():
    srv = DecisionServer(host='127.0.0.1', port=0)
    out = srv.triage({'events': FIXTURE['events']})
    assert out['accepted'] == 16 and out['shed'] == 3
    assert len(out['verdicts']) == 16
