"""Reflex API for Verdandi - Tviheimr readiness slice HG-T4.

The declared-reflex surface: a consumer (Verdandi) registers reflexes
(trigger pattern -> named action), HugrGate judges incoming events
against them and returns fire/no-fire with basis, at decision-runtime
latency. HugrGate judges; the consumer acts and records.

Design rules, enforced in code:
- Only DECLARED reflexes can fire. An event matching no registered
  pattern fires nothing; there is no implicit or default reflex.
- Patterns are explicit: optional source match, optional kind match
  (exact, or prefix when the pattern value ends in '*'), and optional
  payload conditions (payload key -> expected value, list of
  allowed values, or a numeric comparison object such as
  {'gte': 0.9}). At least one of source/kind/where is required and
  an empty pattern is refused, so a reflex can never be an
  undeclared catch-all. (Where-only patterns serve consumers whose
  reflexes key on a measured field alone - e.g. Verdandi's
  noise-shed at noise >= 0.9; the declared condition still gates
  every fire.)
- Registration is validated: duplicate names, empty actions, empty
  patterns and malformed conditions are refused with ValueError.
- Every judgment returns one verdict per registered reflex, in
  registration order: fire (bool), action, basis naming the matched
  or first failed pattern part, the event payload digest, and the
  measured latency_ms of the judgment. Deterministic: identical
  events against an identical registry give identical fire/no-fire
  and basis (latency excepted).
- Invalid events fire nothing: every verdict is no-fire with a
  schema basis, never a silent drop.
Stdlib only. Plain library code - no service form assumed.
"""
from __future__ import annotations
import hashlib, json, time
from collections.abc import Mapping
__all__ = ['ReflexRegistry', 'ReflexError', 'payload_digest']

def payload_digest(payload):
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()

ReflexError = ValueError  # house rule: raise stdlib validation errors

def _match_pattern_part(label, pattern_value, actual):
    if pattern_value is None:
        return None
    if actual is None:
        return f'{label}: event has no {label}'
    text = str(actual)
    if pattern_value.endswith('*'):
        if text.startswith(pattern_value[:-1]):
            return None
        return f'{label}: {text!r} does not match prefix {pattern_value!r}'
    if text == pattern_value:
        return None
    return f'{label}: {text!r} != {pattern_value!r}'

_COMPARISON_OPS = ('gte', 'lte', 'gt', 'lt')

def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)

def _validate_comparison(k, v):
    if not v:
        raise ValueError(f'pattern where[{k!r}] comparison must be a non-empty object')
    unknown = set(v) - set(_COMPARISON_OPS)
    if unknown:
        raise ValueError(f'pattern where[{k!r}] unknown comparison ops: {sorted(unknown)}')
    for op, operand in v.items():
        if not _is_number(operand):
            raise ValueError(f'pattern where[{k!r}] comparison {op} needs a number, got {operand!r}')
    return dict(v)

def _comparison_failure(key, comparison, actual):
    if not _is_number(actual):
        return f'where: payload {key!r}={actual!r} is not a number'
    for op in _COMPARISON_OPS:
        if op not in comparison:
            continue
        operand = comparison[op]
        ok = {'gte': actual >= operand, 'lte': actual <= operand,
              'gt': actual > operand, 'lt': actual < operand}[op]
        if not ok:
            return f'where: payload {key!r}={actual!r} fails {op} {operand!r}'
    return None

def _validate_pattern(pattern):
    if not isinstance(pattern, Mapping):
        raise ValueError('pattern must be an object')
    unknown = set(pattern) - {'source', 'kind', 'where'}
    if unknown:
        raise ValueError(f'unknown pattern fields: {sorted(unknown)}')
    where = pattern.get('where')
    checked_where = None
    if where is not None:
        if not isinstance(where, Mapping) or not where:
            raise ValueError('pattern where must be a non-empty object')
        checked_where = {}
        for k, v in where.items():
            if isinstance(v, Mapping):
                checked_where[k] = _validate_comparison(k, v)
            elif isinstance(v, list):
                checked_where[k] = list(v)
            else:
                checked_where[k] = v
    if not pattern.get('source') and not pattern.get('kind') and not checked_where:
        raise ValueError('pattern needs at least one of source/kind/where (no catch-all reflexes)')
    for field in ('source', 'kind'):
        v = pattern.get(field)
        if v is not None and (not isinstance(v, str) or not v or v == '*'):
            raise ValueError(f'pattern {field} must be a non-empty string, not a bare wildcard')
    checked = dict(pattern)
    if checked_where is not None:
        checked['where'] = checked_where
    return checked

class ReflexRegistry:
    """Declared reflexes for one consumer. HugrGate judges only."""
    def __init__(self, consumer='verdandi'):
        self.consumer = str(consumer)
        self._reflexes = []
        self._by_name = {}
    def register(self, name, action, pattern, consumer=None):
        if not isinstance(name, str) or not name:
            raise ValueError('reflex name must be a non-empty string')
        if name in self._by_name:
            raise ValueError(f'reflex {name!r} already registered')
        if not isinstance(action, str) or not action:
            raise ValueError('reflex action must be a non-empty string (a named action)')
        checked = _validate_pattern(pattern)
        entry = {'name': name, 'action': action, 'pattern': checked,
                 'consumer': str(consumer) if consumer else self.consumer}
        self._reflexes.append(entry)
        self._by_name[name] = entry
        return dict(entry)
    def unregister(self, name):
        entry = self._by_name.pop(name, None)
        if entry is None:
            raise ValueError(f'no reflex named {name!r}')
        self._reflexes.remove(entry)
        return dict(entry)
    def list_reflexes(self):
        return [dict(r) for r in self._reflexes]
    def __len__(self):
        return len(self._reflexes)
    def _first_failure(self, entry, event):
        pattern = entry['pattern']
        for field in ('source', 'kind'):
            fail = _match_pattern_part(field, pattern.get(field), event.get(field))
            if fail:
                return fail
        where = pattern.get('where') or {}
        payload = event.get('payload') if isinstance(event.get('payload'), Mapping) else {}
        for key in sorted(where):
            expected = where[key]
            if key not in payload:
                return f'where: payload has no {key!r}'
            if isinstance(expected, Mapping):
                fail = _comparison_failure(key, expected, payload[key])
                if fail:
                    return fail
                continue
            allowed = expected if isinstance(expected, list) else [expected]
            if payload[key] not in allowed:
                return f'where: payload {key!r}={payload[key]!r} not in {allowed!r}'
        return None
    def judge_one(self, event, index=None):
        started = time.perf_counter()
        if isinstance(event, Mapping) and 'payload' in event:
            digest = payload_digest(event['payload'])
        elif isinstance(event, Mapping) and event.get('payload_digest'):
            digest = str(event['payload_digest'])
        else:
            digest = payload_digest(None)
        valid = isinstance(event, Mapping) and bool(event.get('source')) and bool(event.get('kind'))
        verdicts = []
        for entry in self._reflexes:
            if not valid:
                fire, basis = False, 'schema: invalid event (needs source and kind) - no reflex fires'
            else:
                fail = self._first_failure(entry, event)
                if fail is None:
                    fire, basis = True, f"declared:{entry['name']} pattern matched (source/kind/where all satisfied)"
                else:
                    fire, basis = False, f"declared:{entry['name']} no-match: {fail}"
            verdicts.append({'reflex': entry['name'], 'action': entry['action'],
                             'consumer': entry['consumer'], 'fire': fire, 'basis': basis,
                             'payload_digest': digest, 'deterministic': True, 'slice': 'HG-T4'})
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        for v in verdicts:
            v['latency_ms'] = latency_ms
        return {'index': index, 'fires': [v['action'] for v in verdicts if v['fire']],
                'verdicts': verdicts, 'latency_ms': latency_ms}
    def judge_stream(self, events):
        results = [self.judge_one(ev, index=i) for i, ev in enumerate(events)]
        lat = [r['latency_ms'] for r in results]
        return {'results': results, 'events': len(results),
                'total_fires': sum(len(r['fires']) for r in results),
                'latency_ms': {'median': round(sorted(lat)[len(lat) // 2], 3) if lat else 0.0,
                               'max': max(lat) if lat else 0.0}}
