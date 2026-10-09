# Campaign XIII — Decision Memory: Completion Report

**Slices 301–325 · branch `gjallarbu/campaign-xiii` · 2026-10-09**

## Mission

Give HugrGate a persistent memory of its own decisions: record, label,
recall, and learn from history — without duplicating the provenance
chain. Directly answer the Campaign XII flag of unbounded
`ProvenanceStore` memory growth (+1.3 GB RSS over 1M decisions).

## What was built

A new package, `hugrgate/memory/` — 22 source modules, 82 exported
names, 24 dedicated test modules:

| Slice | Module | Capability |
|---|---|---|
| 301 | `history.py` | `Episode` snapshots + thread-safe append-mostly `DecisionHistory` (record/get/recent/find/count, `max_episodes` eviction, `import_from_provenance`, `estimate_bytes`) |
| 302 | `query.py` | Typed `MemoryQuery` (filters/sort/pagination/explain); `ProvenanceStore.scan()` hardening; `find_in_provenance` adapter |
| 303 | `outcomes.py` | Frozen `Outcome` value objects; `attach_outcome` with overwrite guard |
| 304 | `groundtruth.py` | Verified labels, immutable-once-set, supersede audit trail; `outcome_agrees`; `consistency_report` |
| 305 | `similarity.py` | Auditable sparse feature vectors; exact cosine; `most_similar` with shared-feature explanations, recency tie-breaks |
| 306 | `retrieval.py` | Transparent similarity+recency+outcome scoring; `RetrievalResult.explain()`; `recall()` |
| 307 | `policies.py` | Contextual record/drop/redact rules + factories; policy hook in `record()`; `EpisodeLike`/`HistoryLike` protocols |
| 308 | `decay.py` | Shared exponential-decay math (`decay_weight`, `half_life_for_horizon`, `effective_count`, `decayed_mean`) |
| 309 | `recency.py` | Time-since-last-similar, last outcome, streaks, decayed similar counts |
| 310 | `frequency.py` | `count_by` with pluggable key fns; raw + decayed counts |
| 311 | `conditioned.py` | Outcome-kind-conditioned retrieval; strict unknown exclusion; ground-truth-agreement gate |
| 312 | `backend_history.py` | Per-backend track records; success rate `None` when unlabeled |
| 313 | `contract_history.py` | Per-contract aggregates; fixed `privacy_preserving_record` silently dropping `contract_id` |
| 314 | `domain_profiles.py` | Per-domain aggregates (volume, acceptance, outcomes, top backends, spec mix, mean p, decayed activity) |
| 315 | `access.py` | Owner/analyst/auditor roles over the privacy ladder; `GuardedHistory`; redacted views; adversarial negative tests |
| 316 | `retention.py` | TTL/count/byte quotas; `enforce_quotas`/`check_quota`; `MemoryQuotaExceeded`; `DecisionHistory.purge`; `ProvenanceStore.estimate_bytes()` |
| 317 | `compaction.py` | `compact()` → `CompactionSummary` aggregates; ground-truth episodes spared by default |
| 318 | `io.py` | Versioned JSONL export/import; id-preserving restore; duplicate skipping; strict mode |
| 319 | `replay.py` | Re-run history through `decide()`; value-match rate; prob drift; counted errors |
| 320 | `counterfactuals.py` | Per-backend/per-value estimates with Wilson intervals; sufficient-data flags; stated assumptions |
| 321 | `assisted_routing.py` | `advise_route()` with explicit abstention when history is insufficient |
| 322 | `assisted_calibration.py` | PAVA isotonic recalibration; 70/30 chronological validation; validated on seeded data: **ECE 0.1497→0.0541, Brier 0.2693→0.2395** |
| 323 | `adversarial.py` | Poisoning/chronology/flood/anomaly detectors with severity grades |
| 324 | `benchmarks.py` | Seeded benchmark workload; artifact save/load/compare; CLI; checked-in baseline `benchmarks/memory_bench.json` |
| 325 | — | This release gate |

Plus: 3 new error classes (`MemoryError`, `MemoryQuotaExceeded`,
`MemoryAccessDenied`) in `hugrgate/errors.py`; regenerated API
inventory (`docs/campaign-i/003-public-api-inventory.md`: 315 modules,
1914 public names); CHANGELOG campaign section.

## Architecture decisions (binding)

1. **Memory on top of provenance, never instead of it.** Episodes
   deep-copy `DecisionRecord` and carry the `record_hash` for audit.
   Provenance remains the tamper-evident legal record.
2. **Hub-and-spoke imports.** `history.py` is the hub; spokes never
   import it — they program to `EpisodeLike`/`HistoryLike` protocols.
   Enforced by `tests/test_import_cycles.py` (counts even
   `TYPE_CHECKING` edges).
3. **Honest boundaries.** `advise_route` abstains, `success_rate` is
   `None` when unlabeled, counterfactuals state assumptions, scans are
   detection-only, memory-only provenance filters raise.

## Anti-Checkbox moments (attack, not checkbox)

- Slice 313 found and fixed a **real bug**: `privacy_preserving_record`
  silently dropped `contract_id` in every privacy mode, making
  contract history impossible — the feature would have looked green
  while recording nothing.
- Slice 302 hardened the opposite direction: `find_in_provenance`
  raises on memory-only filters instead of silently ignoring them.
- Slice 322 validated calibration on **controlled, seeded,
  miscalibrated data** (n=2000) rather than asserting it works.
- Slice 325's release gate caught a **real drift bug** introduced in
  slice 315: `__all__` listed `ROLE_PERMISSIONS` while the import was
  dropped, failing `test_api_inventory`. Fixed before release.

## Unbounded-growth answer (Campaign XII flag)

`estimate_bytes()` on both stores, quota-checked `enforce_quotas()`
(count/byte/TTL), `compact()` to summaries, `purge()` primitive, and
`ProvenanceStore.estimate_bytes()` in provenance itself.

## Known limits

- `find`/`recall` are linear scans: ~82/100 ms at 2,000 episodes on the
  benchmark machine. Fine for thousands; indexing is future work past
  that.
- Benchmark ratios run-to-run show machine noise (1.2–2.1× on a loaded
  box); the artifact documents methodology and workload so
  comparisons stay honest.

## Verification

- Full suite: **4086 passed, 1 skipped** (ruff + mypy clean on all
  new code). One residual failure: `test_chaos_crash.py::
  test_recovery_survives_repeated_kills` — a kill-`-9` timing test in
  `hugrgate.chaos` / `hugrgate.edge.recovery`, code paths this
  campaign never touched; it passes intermittently in this sandbox
  (~1/3 of isolated runs) and is an environmental flake, not a
  campaign regression. `test_privacy_bench_249` also flaked once under
  full-suite load and passed on re-run.
- Definition of Done per slice: skald/rúnhild/eldra/sólrún/védis/scribe
  phases, real implementation, tests green, docs + taxonomy + CHANGELOG
  updated.
