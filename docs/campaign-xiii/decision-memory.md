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

### Slice 306 — Decision retrieval
- `hugrgate/memory/retrieval.py`: `retrieve()` scores precedents as
  `alpha*similarity + beta*recency + gamma*outcome_bonus` (weights
  validated, `min_score` filter, `exclude_ids`, injectable `now`);
  `RetrievalResult` carries the full score breakdown plus
  `explain()`; `recall()` builds features from raw attributes.
  Outcome bonus: known-positive 1.0, known-negative 0.0, unknown 0.5.
- Exported similarity + retrieval surfaces from `hugrgate.memory`
  (missed in the slice 305 commit).
- Tests: `tests/test_memory_retrieval.py` (9 tests).

### Slice 307 — Contextual memory policies
- `hugrgate/memory/policies.py`: `MemoryPolicy` (ordered `MemoryRule`s,
  first match wins, default record) with `MemoryDecision` verdicts and
  `explain()`; factories `drop_forbidden` (mirrors
  `privacy_retention`: forbidden never persists), `redact_above`
  (privacy-ladder-aware via `at_least`), `drop_backend`,
  `record_only_backend`, `drop_unaccepted`; custom predicate rules.
- `DecisionHistory.record(..., policy=...)`: drop returns `None`,
  redact strips record metadata and marks annotations.
- `hugrgate/memory/types.py`: `EpisodeLike`/`HistoryLike` Protocols —
  spokes stay typed without importing the `history` hub (the
  import-cycle gate counts `TYPE_CHECKING` edges; `consistency_report`
  moved onto `DecisionHistory` as a method; `MemoryQuery.apply`
  made generic to preserve concrete episode types).
- Tests: `tests/test_memory_policies.py` (14 tests).

### Slice 308 — Time-decay weighting
- `hugrgate/memory/decay.py`: shared exponential-decay math —
  `decay_weight` (0.5 at one half-life, negative ages clamped,
  underflow documented as exactly 0.0), `half_life_for_horizon`,
  `effective_count`, `decayed_mean` (explicit error when all weights
  underflow instead of a silent NaN).
- `retrieval.py` refactored onto the shared module (as its docstring
  promised); regression test keeps half-life behavior pinned.
- Tests: `tests/test_memory_decay.py` (7 tests).

### Slice 309 — Recency features
- `hugrgate/memory/recency.py`: `recency_features(history, features)`
  distills time-since-last-similar, last outcome kind, current
  success/failure streaks (head-of-history runs, broken by unknown
  outcomes), raw + decay-weighted similar counts, mean similarity.
  Cosine threshold gate, newest-first scan capped at `max_candidates`
  for large histories.
- Tests: `tests/test_memory_recency.py` (9 tests).

### Slice 310 — Frequency features
- `hugrgate/memory/frequency.py`: `count_by(history, key_fn)` groups
  episodes (key fns: `by_backend`, `by_model`, `by_backend_value`,
  `by_outcome_kind`, or custom) into `FrequencyEntry` records — raw
  count, decay-weighted count, first/last seen, per-outcome breakdown;
  `FrequencyTable.top(n)` ranks by decayed count; optional
  `MemoryQuery` pre-filter and scan `limit`.
- Tests: `tests/test_memory_frequency.py` (10 tests).

### Slice 311 — Outcome-conditioned retrieval
- `hugrgate/memory/conditioned.py`: `retrieve_conditioned()` filters
  precedents by outcome kind (default: successes only), with
  `include_unknown` (default strict-off, anti-survivorship-bias) and
  `require_truth_agreement` (ground truth must agree with the outcome).
- `retrieve()` gained an additive `episodes=` subset parameter so
  conditioned (or otherwise pre-filtered) sets score without a second
  history scan; prior tests still green.
- Tests: `tests/test_memory_conditioned.py` (9 tests).

### Slice 312 — Backend history features
- `hugrgate/memory/backend_history.py`: `backend_histories()` builds
  per-backend `BackendHistory` records — decision/accepted counts and
  rates, outcome distribution, success rate (`None`, not 0, when
  unlabeled), raw + decay-weighted mean probability, mean latency,
  first/last seen, observed models; query pre-filter and scan limit.
- Tests: `tests/test_memory_backend_history.py` (7 tests).

### Slice 313 — Contract history features
- Attack (Anti-Checkbox Rule): `privacy_preserving_record` silently
  dropped `contract_id` (it rides in `result.metadata`), making
  contract history impossible. Now propagated as an identifier across
  all privacy modes — never state payload, never PII. Existing
  privacy tests still green.
- `hugrgate/memory/contract_history.py`: `contract_key_for()`
  (`contract:<id>` or synthetic `spec:<value-space-signature>`);
  `contract_histories()` aggregates per-contract `ContractHistory`
  (counts, acceptance rate, outcome distribution, success rate `None`
  when unlabeled, serving backends, mean probability, first/last seen).
- Tests: `tests/test_memory_contract_history.py` (8 tests, incl.
  propagation across all five privacy classes).

### Slice 314 — Domain history profiles
- `hugrgate/memory/domain_profiles.py`: `domain_for()` resolves
  spec-metadata > record-metadata > `"default"`; `domain_profiles()`
  aggregates per-domain `DomainProfile` (volume, acceptance rate,
  outcome distribution, success rate, top-3 backends, spec-type mix,
  mean probability, decay-weighted activity, first/last seen).
- Tests: `tests/test_memory_domain_profiles.py` (9 tests).

### Slice 315 — Memory privacy controls
- `hugrgate/memory/access.py`: `MemoryAccessPolicy` maps
  owner/analyst/auditor roles over the privacy ladder (max readable
  class, redact-at threshold, write flag); `GuardedHistory` wraps a
  history — reads filtered + redacted per role, writes
  (`record`/`attach_*`/`clear`) owner-only via `MemoryAccessDenied`.
  Denied reads raise, never return partial episodes; views are deep
  copies. Fixed during testing: `recent(n)` returns the n most recent
  *readable* episodes, not the readable subset of the n newest.
- Negative/adversarial tests: cross-class reads denied, non-owner
  writes denied (store untouched), unknown roles rejected, view
  mutation cannot leak into the store, role-escalation attempts
  contained.
- Tests: `tests/test_memory_access.py` (13 tests).

### Slice 316 — Memory retention controls
- `hugrgate/memory/retention.py`: `MemoryQuota` (max episodes, max
  bytes, warn threshold, TTL overrides reusing
  `privacy_retention.RETENTION_DEFAULTS`); `enforce_quotas()` applies
  TTL purges then oldest-first count/byte eviction and returns a
  `RetentionReport`; `check_quota()` is the non-mutating ok/warn/over
  probe; `MemoryQuotaExceeded` raised when no single episode can fit
  `max_bytes` (total amnesia would be the dishonest alternative).
- `DecisionHistory.purge(predicate)` retention primitive;
  `ProvenanceStore.estimate_bytes()` — direct answer to the Campaign
  XII +1.3 GB unbounded-growth flag: measure before controlling.
- Tests: `tests/test_memory_retention.py` (12 tests).

### Slice 317 — Memory compaction
- `hugrgate/memory/compaction.py`: `compact(history, older_than_seconds)`
  rolls old episodes into a `CompactionSummary` (window, per-backend
  and outcome counts, success rate, mean probability, privacy-class
  mix, compacted ids), purges the raw episodes, and stores the summary
  on the history (`add_compaction_summary` /
  `compaction_summaries()`). Ground-truth-bearing episodes are spared
  by default — verified labels are irreplaceable by aggregates.
- Tests: `tests/test_memory_compaction.py` (9 tests).

### Slice 318 — Memory export/import
- `hugrgate/memory/io.py`: `export_jsonl()` writes versioned JSONL
  envelopes (episodes chronological + compaction summaries);
  `import_jsonl()` restores with id preservation, duplicate skipping,
  corrupt-line reports, strict mode raising `MemoryError`, unknown
  schema/version rejection, missing-file errors. Export is
  documented as owner-grade (all privacy classes verbatim).
- `Episode.from_dict()` + `DecisionHistory.import_episode()` (new-id
  preservation, duplicate-id `MemoryError`); `to_dict` added to the
  `EpisodeLike` protocol.
- Tests: `tests/test_memory_io.py` (9 tests).

### Slice 319 — Memory replay
- `hugrgate/memory/replay.py`: `replay(history, decide)` re-runs
  episodes through a caller-supplied `decide(spec) -> (value,
  probability)` and reports value-match rate, mean absolute
  probability drift, per-episode mismatches, and counted (never fatal)
  errors. Specs are deep-copied so a misbehaving policy cannot mutate
  history. Query pre-filter and limit supported.
- Tests: `tests/test_memory_replay.py` (9 tests).
