# Slice 239 — Retention policies

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_retention.py` (13 tests)

## What existed

Nothing expired, ever: provenance records and cache entries lived
until evicted by size caps. Sensitive data had no maximum age.

## What changed

- New module `hugrgate/privacy_retention.py`:
  - `RetentionPolicy` — per-class maximum ages (public unbounded,
    standard 30d, sensitive 7d, strict 24h, forbidden 0 = never
    retain). Unknown classes fail closed to the strict default.
  - `purge_expired(store, policy, now, on_purge)` — removes overdue
    records; the `on_purge` hook fires per record before removal
    (slice 240 attaches secure deletion here).
  - `cache_ttl_for` — caps decision-cache TTLs by class.
- `ProvenanceStore.purge(predicate)` (in `hugrgate/provenance.py`) —
  chain-safe removal: survivors are re-chained from the floor hash
  so `verify_chain()` still passes after a purge.
- `DecisionCache.put(..., retention=None)` — optional per-class TTL
  cap; default behavior unchanged.

## Verification

- `pytest tests/test_privacy_retention.py` — 13 passed, including
  expiry boundaries, forbidden zero-retention, TTL capping (with a
  real 80ms sleep), and chain verification after middle-record
  purges.
- `test_provenance_integrity.py` + `test_ladder.py` (72) green.
- `ruff check` clean.
