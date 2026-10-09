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

### Slice 303 — Outcome attachment
- `hugrgate/memory/outcomes.py`: frozen `Outcome` (kind in
  success/failure/partial, optional score in [0,1], `observed_at`,
  note, latency) with `to_dict`/`from_dict`, `is_positive()`.
- `DecisionHistory.attach_outcome(episode_id, outcome, overwrite=False)`:
  one outcome per episode; double-attach raises `MemoryError` unless
  `overwrite=True`; unknown ids raise `MemoryError`.
- Outcomes are queryable (`has_outcome`, `outcome_kinds` filters from
  slice 302) and feed slices 305-322.
- Tests: `tests/test_memory_outcomes.py` (13 tests).

### Slice 304 — Ground-truth attachment
- `hugrgate/memory/groundtruth.py`: frozen `GroundTruth`
  (label/confidence/source/verified_at/note) with round-trip;
  `outcome_agrees()` (bool or outcome-kind labels comparable,
  partial outcomes never verdicts); `consistency_report(history)`
  listing episodes where verified truth contradicts observed outcome.
- `DecisionHistory.attach_ground_truth(episode_id, truth, supersede=False)`:
  immutable once set; supersede preserves the displaced truth in
  `annotations["ground_truth_revisions"]`.
- Tests: `tests/test_memory_groundtruth.py` (12 tests).

### Slice 305 — Historical similarity search
- `hugrgate/memory/similarity.py`: auditable sparse feature vectors
  (`featurize_episode`/`featurize_query`: spec shape, backend, model,
  probability bucket, acceptance, fallback, latency band, state keys
  capped at 32, domain), exact `cosine`, `most_similar` top-k with
  `SimilarityHit` (score + shared features explaining the match),
  recency tie-break, `exclude_ids`.
- Tests: `tests/test_memory_similarity.py` (10 tests).
