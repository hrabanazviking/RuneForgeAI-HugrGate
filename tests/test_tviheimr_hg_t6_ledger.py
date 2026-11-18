"""HG-T6 gate: judgment provenance ledger.

Gate (roadmap): any verdict in the fixture runs can be traced to its
ledger entry; the ledger survives restart; no verdict exists without
an entry.
"""

import json, urllib.request
import pytest
from hugrgate.decision_server import DecisionServer
from hugrgate.judgment_ledger import JudgmentLedger, LedgerError, canonical_digest
from hugrgate.triage_profile import TriageProfile
from hugrgate.salience_profile import SalienceProfile
from hugrgate.reflex_api import ReflexRegistry

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration

def _load(name):
    return json.loads((ROOT / 'campaign' / name).read_text())

def test_record_and_trace_roundtrip(tmp_path):
    led = JudgmentLedger(tmp_path / 'l.jsonl')
    v = {'route': 'escalate', 'basis': 'rules:critical-signal:fire'}
    e = led.record('triage', {'source': 'a', 'kind': 'fire'}, v, v['basis'], 1.25, slice_id='HG-T3')
    assert e['seq'] == 0 and e['inputs_digest'] == canonical_digest({'source': 'a', 'kind': 'fire'})
    assert led.trace(v)['record_hash'] == e['record_hash']
    assert led.verify()['ok'] is True

def test_no_basis_no_entry(tmp_path):
    led = JudgmentLedger(tmp_path / 'l.jsonl')
    with pytest.raises(ValueError):
        led.record('judge', {}, {'value': 1}, '', 0.1)
    assert len(led) == 0

def test_survives_restart_and_chain_continues(tmp_path):
    path = tmp_path / 'l.jsonl'
    led = JudgmentLedger(path)
    led.record('judge', {'a': 1}, {'value': 'x', 'basis': 'b1'}, 'b1', 0.5)
    led.record('judge', {'a': 2}, {'value': 'y', 'basis': 'b2'}, 'b2', 0.6)
    again = JudgmentLedger(path)  # restart: re-read + verify + continue
    assert len(again) == 2
    e = again.record('judge', {'a': 3}, {'value': 'z', 'basis': 'b3'}, 'b3', 0.7)
    assert e['seq'] == 2 and again.verify() == {'ok': True, 'reason': 'ok', 'entries': 3, 'head_hash': e['record_hash']}

def test_tamper_detected_and_refused(tmp_path):
    path = tmp_path / 'l.jsonl'
    led = JudgmentLedger(path)
    led.record('judge', {'a': 1}, {'value': 'x', 'basis': 'b'}, 'b', 0.5)
    raw = path.read_text().replace('"x"', '"hacked"')
    path.write_text(raw)
    with pytest.raises(LedgerError):
        JudgmentLedger(path)
    assert led.verify()['ok'] is False

def test_fixture_verdicts_all_traced(tmp_path):
    led = JudgmentLedger(tmp_path / 'l.jsonl')
    tri = _load('hg_t3_fixture_stream.json')
    events = tri['events'] if isinstance(tri, dict) else tri
    for ev, v in zip(events, TriageProfile().triage_stream(events)):
        led.record('triage', ev, v, v['basis'], 0.01, slice_id='HG-T3', model_used=v['model_used'])
    sal = _load('hg_t5_fixture_stream.json')
    sevents = sal['events'] if isinstance(sal, dict) else sal
    out = SalienceProfile().judge_stream(sevents)
    for ev, v in zip(sevents, out['verdicts']):
        led.record('salience', ev, v, v['basis'], 0.01, slice_id='HG-T5')
    ref = _load('hg_t4_fixture_reflexes.json')
    reg = ReflexRegistry()
    for r in ref['reflexes']:
        reg.register(r['name'], r['action'], r['pattern'])
    rout = reg.judge_stream(ref['events'])
    n_reflex = 0
    for ev, item in zip(ref['events'], rout['results']):
        for v in item['verdicts']:
            led.record('reflex', ev, v, v['basis'], 0.01, slice_id='HG-T4'); n_reflex += 1
    total = len(events) + len(sevents) + n_reflex
    assert len(led) == total and led.verify()['ok'] is True
    # every single fixture verdict traces to exactly its entry
    for v in TriageProfile().triage_stream(events):
        assert led.trace(v) is not None

def test_server_records_every_verdict(tmp_path):
    path = tmp_path / 'srv.jsonl'
    with DecisionServer(port=0, ledger_path=str(path)) as srv:
        host, port = srv.address
        def post(p, body):
            req = urllib.request.Request(f'http://{host}:{port}{p}', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            return json.loads(urllib.request.urlopen(req, timeout=5).read())
        def get(p):
            return json.loads(urllib.request.urlopen(f'http://{host}:{port}{p}', timeout=5).read())
        tri = _load('hg_t3_fixture_stream.json'); events = tri['events'] if isinstance(tri, dict) else tri
        t = post('/triage', {'events': events})
        sal = _load('hg_t5_fixture_stream.json'); sevents = sal['events'] if isinstance(sal, dict) else sal
        s = post('/salience', {'events': sevents})
        ref = _load('hg_t4_fixture_reflexes.json')
        for r in ref['reflexes']:
            post('/reflexes', r)
        rj = post('/reflex/judge', {'events': ref['events']})
        j = post('/judge', {'state': {'text': 'fire escalate'}, 'spec': {'type': 'categorical', 'options': ['routine', 'escalate']}})
        st = get('/ledger')
    led = JudgmentLedger(path)  # restart view
    expected = len(t['verdicts']) + len(s['verdicts']) + sum(len(i['verdicts']) for i in rj['results']) + 1
    assert st['enabled'] and st['verified'] and st['entries'] == expected
    assert len(led) == expected and led.verify()['ok'] is True
    for v in t['verdicts'] + s['verdicts']:
        assert led.trace(v) is not None, 'verdict without a ledger entry'
    assert led.trace(j) is not None

def test_server_without_ledger_unchanged(tmp_path):
    with DecisionServer(port=0) as srv:
        assert srv.ledger_status() == {'enabled': False, 'entries': 0}
