"""Judgment provenance ledger - Tviheimr readiness slice HG-T6.

Roadmap: every judgment - rules, classifier, or model - is recorded
with its basis, inputs digest, and latency, in an append-only local
ledger a caller can audit.

Design rules, enforced in code:
- Append-only JSONL file. Entries are never rewritten or deleted by
  this module; each entry carries seq, timestamp, kind, slice, basis,
  inputs_digest (sha256 of the canonical input), the full verdict,
  verdict_digest, latency_ms, and a hash chain (prev_hash ->
  record_hash, same integrity model as hugrgate.provenance) so any
  tampering with a stored line breaks verify().
- No verdict without an entry: record() writes, flushes and fsyncs
  BEFORE returning the entry, and the decision server records every
  verdict synchronously before the response is built.
- Survives restart: opening an existing ledger re-reads and verifies
  it, and new entries continue seq and the hash chain from the last
  stored entry. A corrupt or tampered file is refused at open
  (LedgerError) rather than silently extended.
- Audit: entries(), by_verdict_digest(), by_inputs_digest(),
  trace(verdict) -> the entry that recorded exactly that verdict,
  verify() re-reads the file from disk and re-checks the chain.
Stdlib only. Plain local file - no service form assumed.
"""
from __future__ import annotations
import hashlib, json, os, threading, time
from collections.abc import Mapping
__all__ = ['JudgmentLedger', 'LedgerError', 'canonical_digest', 'verdict_digest_of']

LedgerError = RuntimeError  # house rule: raise stdlib errors

def _canonical(obj):
    return json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False, separators=(',', ':'))

def canonical_digest(obj):
    return hashlib.sha256(_canonical(obj).encode('utf-8')).hexdigest()

def verdict_digest_of(verdict):
    return canonical_digest(verdict)

def _entry_hash(entry):
    body = {k: v for k, v in entry.items() if k != 'record_hash'}
    return hashlib.sha256((entry.get('prev_hash', '') + _canonical(body)).encode('utf-8')).hexdigest()

class JudgmentLedger:
    def __init__(self, path):
        self.path = os.fspath(path)
        self._lock = threading.RLock()
        self._entries = []
        if os.path.exists(self.path):
            self._entries = self._read_all()
            ok, why = self._verify_entries(self._entries)
            if not ok:
                raise RuntimeError(f'refusing to extend corrupt ledger {self.path}: {why}')
    # -- file layer ----------------------------------------------------
    def _read_all(self):
        out = []
        with open(self.path, 'r', encoding='utf-8') as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError as e:
                    raise RuntimeError(f'ledger line {n} is not valid JSON: {e}') from e
        return out
    @staticmethod
    def _verify_entries(entries):
        prev = ''
        for i, e in enumerate(entries):
            if e.get('seq') != i:
                return False, f"entry {i}: seq is {e.get('seq')}, expected {i}"
            if e.get('prev_hash') != prev:
                return False, f'entry {i}: prev_hash does not match previous record_hash'
            if e.get('record_hash') != _entry_hash(e):
                return False, f'entry {i}: record_hash mismatch (tampered or corrupt)'
            for f in ('kind', 'basis', 'inputs_digest', 'verdict', 'verdict_digest', 'latency_ms'):
                if f not in e:
                    return False, f'entry {i}: missing field {f}'
            if e['verdict_digest'] != verdict_digest_of(e['verdict']):
                return False, f'entry {i}: verdict_digest does not match verdict'
            prev = e['record_hash']
        return True, 'ok'
    # -- writing ---------------------------------------------------------
    def record(self, kind, inputs, verdict, basis, latency_ms, slice_id=None, model_used=False):
        if not isinstance(verdict, Mapping):
            raise ValueError('verdict must be an object')
        if not basis:
            raise ValueError('every judgment must record its basis')
        with self._lock:
            prev = self._entries[-1]['record_hash'] if self._entries else ''
            entry = {'seq': len(self._entries), 'timestamp': time.time(), 'kind': str(kind), 'slice': slice_id, 'basis': str(basis), 'inputs_digest': canonical_digest(inputs), 'verdict': json.loads(_canonical(verdict)), 'verdict_digest': verdict_digest_of(verdict), 'latency_ms': round(float(latency_ms), 3), 'model_used': bool(model_used), 'prev_hash': prev}
            entry['record_hash'] = _entry_hash(entry)
            parent = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(parent, exist_ok=True)
            with open(self.path, 'a', encoding='utf-8') as fh:
                fh.write(_canonical(entry) + '\n')
                fh.flush()
                os.fsync(fh.fileno())
            self._entries.append(entry)
            return json.loads(_canonical(entry))
    # -- audit -----------------------------------------------------------
    def __len__(self):
        with self._lock:
            return len(self._entries)
    def entries(self):
        with self._lock:
            return json.loads(_canonical(self._entries))
    def by_verdict_digest(self, digest):
        with self._lock:
            for e in reversed(self._entries):
                if e['verdict_digest'] == digest:
                    return json.loads(_canonical(e))
        return None
    def by_inputs_digest(self, digest):
        with self._lock:
            return [json.loads(_canonical(e)) for e in self._entries if e['inputs_digest'] == digest]
    def trace(self, verdict):
        return self.by_verdict_digest(verdict_digest_of(verdict))
    def verify(self):
        on_disk = self._read_all()
        ok, why = self._verify_entries(on_disk)
        return {'ok': ok, 'reason': why, 'entries': len(on_disk), 'head_hash': on_disk[-1]['record_hash'] if on_disk else ''}
