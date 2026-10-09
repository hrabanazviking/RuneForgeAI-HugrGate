# Slice 258 — Cache corruption simulation

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_cache_corruption.py` (10 tests, green)

## What existed before

`DecisionCache` (slice 38) was TTL/LRU/privacy-aware and deep-copied
results across its API boundary — but the stored entries themselves
carried **no integrity protection**. Any corruption beneath the API
(bit rot, a stray in-process write, a buggy background thread
mutating a stored result) would be served to the next caller as a
perfectly good cache hit. The deep-copy discipline guards the
boundary; nothing guarded the store.

## Attack (Yrsa Law 11)

`hugrgate/chaos/cache_faults.py` — `CacheCorruptor`, a test-only
tool that tampers with stored entries *below* the public API
(reaching into the private entry store deliberately, the way
sub-API memory corruption would): `tamper` with an arbitrary
mutator, `corrupt_value`, `corrupt_metadata`. Before the hardening,
the tampered entries were served as hits — the attack succeeded.

## Hardening

`hugrgate/cache.py` now integrity-seals every entry:

- `_Entry` carries a SHA-256 `checksum` over the canonical JSON
  form of the stored result, computed at `put` time.
- `get` re-verifies the seal; on mismatch the entry is **evicted**,
  `corruptions` is incremented (lifetime counter, visible in
  `stats()`), a warning is logged, and a **miss** is reported so
  the caller recomputes instead of serving garbage. Fail safe,
  never fail silent.
- Additive only: `stats()` gains the `"corruptions"` key; no
  existing behavior changed for clean entries.

## Integration

- Privacy: the seal check runs after the privacy gate —
  privacy-forbidden entries still never touch the store.
- Provenance/observability: corruption count is a first-class
  cache stat; evictions are logged.
- No new error class: corruption is a cache *event* (miss +
  counter), not an exception.

## Verification

- 10 tests: corrupted value/metadata/arbitrary-field all evicted
  and counted; corruptions accumulate; cache recovers via
  recompute+re-put; tamper-on-miss is a clean False; **100 clean
  puts/gets produce zero false positives**; LRU touch and expiry
  sweep don't trip the seal; stats contract.
- Existing cache users (`test_ladder`, `test_thread_safety`) re-run
  green — the seal is transparent to honest traffic.
- `ruff check` clean.
