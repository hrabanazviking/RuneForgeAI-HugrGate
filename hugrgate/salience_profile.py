"""Aurelia sensation-stream salience profile - Tviheimr slice HG-T5.

Roadmap: a judgment profile for sensation events: salience, genuine
state change vs noise, urgency. Tuned with Aurelia's own event schema
(her house defines it; this slice consumes it).

Consumed schema: Aurelia AU-T1 sensation event schema v1 (her house:
female_motivation/readiness/sensation_events.py): kind, intensity
(0..1), source, timestamp, digest (sha256 hex of the underlying
record), schema_version=1, optional before/after.
Emitted verdict: Aurelia AU-T2 verdict schema v1, field for field, so
her JudgmentBinding accepts it unchanged: schema_version,
event_digest, salient, disposition (surface/settle), authenticity
(genuine/noise), urgency (0..3), basis, judge_id.
Expected salience table (Aurelia's own, by intensity):
  >= 0.80: salient, genuine, urgency 3, surface
  0.50-0.80: salient, genuine, urgency 2, surface
  0.20-0.50: salient, genuine, urgency 1, surface
  0.05-0.20: not salient, genuine, urgency 0, settle
  < 0.05: not salient, noise, urgency 0, settle
Design rules: deterministic (identical events -> identical verdicts,
no model in the loop); nothing dropped silently - a schema-invalid
event still gets exactly one settle/noise verdict whose basis starts
'schema:' and names every failure; every verdict carries its basis.
Stdlib only. Plain library code - no service form assumed.
"""
from __future__ import annotations
import hashlib, json, math, re
from collections.abc import Mapping
__all__ = ['SalienceProfile', 'salience_stream', 'record_digest', 'JUDGE_ID', 'EVENT_SCHEMA_VERSION', 'VERDICT_SCHEMA_VERSION', 'NOISE_FLOOR', 'SALIENT_FLOOR', 'HIGH_FLOOR', 'CRITICAL_FLOOR']
EVENT_SCHEMA_VERSION = 1
VERDICT_SCHEMA_VERSION = 1
JUDGE_ID = 'hugrgate-salience-v1'
NOISE_FLOOR = 0.05
SALIENT_FLOOR = 0.20
HIGH_FLOOR = 0.50
CRITICAL_FLOOR = 0.80
_DIGEST_RE = re.compile(r'^[0-9a-f]{64}$')

def record_digest(record):
    canonical = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def _schema_errors(event):
    if not isinstance(event, Mapping):
        return ['event is not an object']
    errs = []
    if event.get('schema_version') != EVENT_SCHEMA_VERSION:
        errs.append(f"schema_version must be {EVENT_SCHEMA_VERSION}")
    kind = event.get('kind')
    if not isinstance(kind, str) or not kind.strip():
        errs.append('kind must be a non-empty string')
    source = event.get('source')
    if not isinstance(source, str) or not source.strip():
        errs.append('source must be a non-empty string')
    ts = event.get('timestamp')
    if not isinstance(ts, (int, float)) or isinstance(ts, bool) or not math.isfinite(float(ts)):
        errs.append('timestamp must be a finite number')
    inten = event.get('intensity')
    if (not isinstance(inten, (int, float)) or isinstance(inten, bool) or not math.isfinite(float(inten)) or not (0.0 <= float(inten) <= 1.0)):
        errs.append('intensity must be a number in [0.0, 1.0]')
    digest = event.get('digest')
    if not isinstance(digest, str) or not _DIGEST_RE.match(digest):
        errs.append('digest must be 64 lowercase hex chars (sha256)')
    return errs

class SalienceProfile:
    name = 'aurelia-sensation-salience'
    judge_id = JUDGE_ID
    def validate_event(self, event):
        return _schema_errors(event)
    def judge_one(self, event, index=None):
        errs = _schema_errors(event)
        supplied = event.get('digest') if isinstance(event, Mapping) else None
        digest = supplied if isinstance(supplied, str) and supplied else record_digest({'invalid': repr(event)[:200]})
        base = {'schema_version': VERDICT_SCHEMA_VERSION, 'event_digest': digest, 'judge_id': self.judge_id, 'slice': 'HG-T5', 'index': index}
        if errs:
            return {**base, 'salient': False, 'disposition': 'settle', 'authenticity': 'noise', 'urgency': 0, 'schema_valid': False, 'basis': 'schema: invalid AU-T1 event - ' + '; '.join(errs)}
        i = float(event['intensity'])
        if i >= CRITICAL_FLOOR:
            salient, disp, auth, urg, basis = True, 'surface', 'genuine', 3, f'intensity {i:.3f} >= critical floor {CRITICAL_FLOOR}: major genuine change'
        elif i >= HIGH_FLOOR:
            salient, disp, auth, urg, basis = True, 'surface', 'genuine', 2, f'intensity {i:.3f} >= high floor {HIGH_FLOOR}: genuine salient change'
        elif i >= SALIENT_FLOOR:
            salient, disp, auth, urg, basis = True, 'surface', 'genuine', 1, f'intensity {i:.3f} >= salient floor {SALIENT_FLOOR}: genuine change worth surfacing'
        elif i >= NOISE_FLOOR:
            salient, disp, auth, urg, basis = False, 'settle', 'genuine', 0, f'intensity {i:.3f} in [{NOISE_FLOOR}, {SALIENT_FLOOR}): genuine but minor, settles quietly'
        else:
            salient, disp, auth, urg, basis = False, 'settle', 'noise', 0, f'intensity {i:.3f} < noise floor {NOISE_FLOOR}: judged noise'
        return {**base, 'salient': salient, 'disposition': disp, 'authenticity': auth, 'urgency': urg, 'schema_valid': True, 'basis': basis}
    def judge_stream(self, events):
        verdicts = [self.judge_one(ev, index=n) for n, ev in enumerate(events)]
        return {'verdicts': verdicts, 'events': len(verdicts), 'surfaced': sum(1 for v in verdicts if v['disposition'] == 'surface'), 'settled': sum(1 for v in verdicts if v['disposition'] == 'settle'), 'noise': sum(1 for v in verdicts if v['authenticity'] == 'noise'), 'schema_invalid': sum(1 for v in verdicts if not v['schema_valid'])}
    def evaluate(self, events, expected):
        verdicts = self.judge_stream(events)['verdicts']
        exp_noise = exp_surface = noise_rejected = missed = matched = 0
        for v, exp in zip(verdicts, expected):
            if not v['schema_valid']:
                continue
            if (v['disposition'], v['authenticity'], v['urgency']) == (exp['disposition'], exp['authenticity'], exp['urgency']):
                matched += 1
            if exp['authenticity'] == 'noise':
                exp_noise += 1
                if v['disposition'] == 'settle':
                    noise_rejected += 1
            if exp['disposition'] == 'surface':
                exp_surface += 1
                if v['disposition'] == 'settle':
                    missed += 1
        valid = sum(1 for v in verdicts if v['schema_valid'])
        return {'events': len(verdicts), 'schema_valid_events': valid, 'schema_invalid_events': len(verdicts) - valid, 'table_matches': matched, 'expected_noise_events': exp_noise, 'noise_rejected': noise_rejected, 'noise_rejection_rate': (noise_rejected / exp_noise) if exp_noise else None, 'expected_surface_events': exp_surface, 'missed_genuine': missed, 'miss_rate': (missed / exp_surface) if exp_surface else None}

def salience_stream(events, profile=None):
    return (profile or SalienceProfile()).judge_stream(list(events))
