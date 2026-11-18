"""HG-T5 salience report runner: judges the recorded Aurelia fixture stream with the live SalienceProfile and banks the honest gate numbers (table matches, noise rejection rate, miss rate)."""
import json
from pathlib import Path
from hugrgate.salience_profile import JUDGE_ID, SalienceProfile
ROOT = Path(__file__).resolve().parent.parent
FIX = json.loads((ROOT / 'campaign' / 'hg_t5_fixture_stream.json').read_text())
rep = SalienceProfile().evaluate(FIX['events'], FIX['expected'])
rep = {'slice': 'HG-T5', 'judge_id': JUDGE_ID, 'fixture': 'campaign/hg_t5_fixture_stream.json', **rep}
out = ROOT / 'campaign' / 'hg_t5_salience_report.json'
out.write_text(json.dumps(rep, indent=1) + '\n')
print(json.dumps(rep))
