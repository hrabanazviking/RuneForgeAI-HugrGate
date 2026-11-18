"""HG-T4 reflex latency benchmark: judges the recorded fixture stream
repeatedly against the declared fixture reflex set and writes the
latency report banked in campaign/hg_t4_latency_report.json."""
from __future__ import annotations
import json, statistics, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hugrgate.reflex_api import ReflexRegistry

def main(rounds=200):
    fixture = json.loads((ROOT / 'campaign' / 'hg_t4_fixture_reflexes.json').read_text())
    reg = ReflexRegistry(consumer=fixture.get('consumer', 'verdandi'))
    for r in fixture['reflexes']:
        reg.register(r['name'], r['action'], r['pattern'])
    # correctness first: one pass must match the expected table exactly
    out = reg.judge_stream(fixture['events'])
    got = [r['fires'] for r in out['results']]
    assert got == fixture['expected_fires'], (got, fixture['expected_fires'])
    lat = []
    for _ in range(rounds):
        for ev in fixture['events']:
            t0 = time.perf_counter()
            reg.judge_one(ev)
            lat.append((time.perf_counter() - t0) * 1000)
    report = {'slice': 'HG-T4', 'fixture_events': len(fixture['events']),
              'reflexes': len(fixture['reflexes']), 'rounds': rounds,
              'judgments': len(lat), 'expected_table_match': True,
              'latency_ms': {'median': round(statistics.median(lat), 3),
                             'p95': round(sorted(lat)[int(len(lat) * 0.95)], 3),
                             'max': round(max(lat), 3)}}
    (ROOT / 'campaign' / 'hg_t4_latency_report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
