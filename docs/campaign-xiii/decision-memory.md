# Campaign XIII — Decision Memory

**Mission:** give the runtime useful historical context without turning
it into an opaque agent.

## Architecture decisions (Yrsa Execution Law, rule 8)

1. **Memory snapshots provenance, never indexes it.** An `Episode`
   holds a deep copy of the `DecisionRecord`; the provenance store's
   `purge()` re-chains survivors, which would invalidate positional or
   hash references. The provenance `record_hash` rides along inside the
   snapshot for audit linkage.
2. **`ProvenanceStore` stays the tamper-evident legal record.**
   Memory is the *working* episodic layer: outcomes, ground truth,
   similarity, retrieval, features. No duplication of the chain logic.
3. **Episodes are immutable from the caller's perspective** —
   deep-copied on the way in and out, `RLock`-guarded, like
   `ProvenanceStore`.
4. **Privacy classes reuse the existing ladder** (`public` … `forbidden`
   from `hugrgate.privacy`); retention defaults reuse
   `hugrgate.privacy_retention.RETENTION_DEFAULTS`.
5. **Bounded by construction:** `max_episodes` oldest-first eviction,
   byte estimates, quotas (slice 316), compaction summaries (slice
   317). This campaign directly answers the Campaign XII finding of
   +1.3 GB RSS over 1M decisions.

## Slice log

### Slice 301 — Decision history API
- New package `hugrgate/memory/` with `__init__.py` (public facade).
- `hugrgate/memory/history.py`: `Episode` dataclass (snapshot +
  privacy class + tags + outcome/ground-truth slots + annotations),
  `DecisionHistory` (record/get/recent/count/by_request_hash/
  episodes_between/clear/import_from_provenance/estimate_bytes,
  `max_episodes` oldest-first eviction, thread-safe).
- `hugrgate/errors.py`: `MemoryError` (`memory_error`, recoverable),
  `MemoryQuotaExceeded` (`memory_quota_exceeded`, recoverable),
  `MemoryAccessDenied` (`memory_access_denied`, not recoverable);
  registered in `tests/test_errors.py`.
- Tests: `tests/test_memory_history.py` (20 tests: round-trip,
  deep-copy isolation, failure paths, boundaries, eviction, import,
  thread-safety smoke).

### Slice 302 — Queryable provenance store
- `ProvenanceStore.scan(predicate)` hardened into `hugrgate/provenance.py`:
  thread-safe snapshot, deep copies, the new query primitive.
- `hugrgate/memory/query.py`: `MemoryQuery` — typed composable filters
  (backend, model, accepted, fallback, time range, privacy class, tags
  any/all, outcome kind, has_outcome, has_ground_truth, probability
  range, request hashes), sorting (`recorded_at`/`probability`/
  `latency_ms`), limit/offset pagination, `matches()`/`explain()`.
- `DecisionHistory.find(query)`; `find_in_provenance(store, query)`
  runs the same language on a raw provenance store (memory-only
  filters raise `MemoryError` instead of being silently ignored).
- Fixed a real bug found by tests: `getattr(x, name, x.timestamp)`
  evaluates the default eagerly — replaced with explicit `hasattr`.
- Tests: `tests/test_memory_query.py` (15 tests).
