"""Tviheimr-side fixture consumer - 'Ready for Tviheimr' gate harness.

Simulates the Connector Fabric admission harness: starts the
decision server as a plain process (subprocess, --ledger on),
registers the HG-T4 reflexes, then calls /triage, /reflex/judge,
/salience and /judge with the recorded fixture streams and checks
every verdict against the fixtures' expected tables, each call
against its latency budget (single calls per call; batch calls per
ledgered verdict, since HG-T6 fsyncs one ledger entry per verdict), and the HG-T6 ledger afterwards
(every verdict traced, chain verified). Writes the report JSON.
Budgets (localhost HTTP, batch calls): 500 ms per call - the
in-process judgment medians recorded by HG-T3/T4/T5 are sub-ms to
~1 ms; the budget covers HTTP + ledger fsync on a shared laptop.
"""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUDGET_MS = 500.0
PER_VERDICT_BUDGET_MS = 25.0  # per ledgered verdict in a batch call (fsync included)
def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p
def call(port, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data, method=method, headers={'Content-Type': 'application/json'})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as r:
        out = json.loads(r.read())
    return out, round((time.perf_counter() - t0) * 1000, 3)
def main():
    load = lambda n: json.loads(open(os.path.join(ROOT, 'campaign', n)).read())
    tri, ref, sal = load('hg_t3_fixture_stream.json'), load('hg_t4_fixture_reflexes.json'), load('hg_t5_fixture_stream.json')
    port = free_port()
    tmp = tempfile.mkdtemp(prefix='hg-ready-')
    ledger = os.path.join(tmp, 'ledger.jsonl')
    env = dict(os.environ, TMPDIR=os.path.expanduser('~/forge-tmp'))
    proc = subprocess.Popen([sys.executable, '-m', 'hugrgate.decision_server', '--port', str(port), '--ledger', ledger], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    checks, lat = {}, {}
    try:
        for _ in range(100):
            try:
                h, _l = call(port, 'GET', '/health'); break
            except Exception:
                if proc.poll() is not None: raise RuntimeError('server exited early')
                time.sleep(0.1)
        checks['health_ok'] = h['status'] == 'ok'
        for r in ref['reflexes']:
            call(port, 'POST', '/reflexes', r)
        t, lat['triage_ms'] = call(port, 'POST', '/triage', {'events': tri['events']})
        checks['triage_table'] = all((v['urgency'], v['route'], v['escalate']) == (e['urgency'], e['route'], e['escalate']) for v, e in zip(t['verdicts'], tri['expected'])) and len(t['verdicts']) == len(tri['events'])
        rj, lat['reflex_ms'] = call(port, 'POST', '/reflex/judge', {'events': ref['events']})
        checks['reflex_table'] = [i['fires'] for i in rj['results']] == ref['expected_fires']
        s, lat['salience_ms'] = call(port, 'POST', '/salience', {'events': sal['events']})
        checks['salience_table'] = all((not v['schema_valid']) or (v['disposition'], v['authenticity'], v['urgency']) == (e['disposition'], e['authenticity'], e['urgency']) for v, e in zip(s['verdicts'], sal['expected']))
        j, lat['judge_ms'] = call(port, 'POST', '/judge', {'state': {'text': 'fire escalate now'}, 'spec': {'type': 'categorical', 'options': ['routine', 'escalate']}, 'backend': 'keyword'})
        checks['judge_ok'] = j.get('value') == 'escalate'
        st, lat['ledger_ms'] = call(port, 'GET', '/ledger')
        expected_entries = len(tri['events']) + len(sal['events']) + sum(len(i['verdicts']) for i in rj['results']) + 1
        checks['ledger_complete'] = st['entries'] == expected_entries and st['verified'] is True
        per_verdict = {'triage': lat['triage_ms'] / len(t['verdicts']), 'reflex': lat['reflex_ms'] / sum(len(i['verdicts']) for i in rj['results']), 'salience': lat['salience_ms'] / len(s['verdicts'])}
        checks['within_budgets'] = lat['judge_ms'] < BUDGET_MS and all(v < PER_VERDICT_BUDGET_MS for v in per_verdict.values())
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
    sys.path.insert(0, ROOT)
    from hugrgate.judgment_ledger import JudgmentLedger
    led = JudgmentLedger(ledger)
    checks['ledger_survives_restart'] = led.verify()['ok'] and len(led) == st['entries']
    report = {'consumer': 'tviheimr-fixture-admission-harness', 'checks': checks, 'latency_ms': lat, 'budget_ms_per_call': BUDGET_MS, 'budget_ms_per_verdict': PER_VERDICT_BUDGET_MS, 'per_verdict_ms': per_verdict, 'ledger_entries': len(led), 'all_passed': all(checks.values())}
    out_path = os.path.join(ROOT, 'campaign', 'hg_ready_consumer_report.json')
    open(out_path, 'w').write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['all_passed'] else 1
if __name__ == '__main__':
    raise SystemExit(main())
