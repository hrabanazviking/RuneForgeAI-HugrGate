# Slice 017 — Thread-safety baseline

**Date:** 2026-10-09 · **Tests:** `tests/test_thread_safety.py` (4 tests)

## Audit of what existed

Already locked: `CircuitBreaker` (`threading.Lock`), health monitor
(`threading.RLock`), daemon server list / stop event. **Not locked:**
`DecisionCache` (shared `OrderedDict` + hit/miss counters mutated on
every request — the daemon serves concurrent requests), and the
mutate-while-iterate races in `BackendRegistry.supporting()` vs
`register()` and `ProvenanceStore.verify_chain()` vs `append()`.

## Changes

- `DecisionCache`: new `threading.RLock` guarding `get` / `put` /
  `invalidate_backend` / `invalidate_model` / `clear` / `__len__` /
  `stats`. (`get` delegates to `_get_locked`; RLock allows the
  `stats()` → `len()` nesting. `stats()` now reads the entry count
  directly under the lock instead of sweeping via `len(self)`.)
- `BackendRegistry`: `threading.RLock` on every method touching
  `_backends` (register/unregister/get/get_or_raise/list/supporting/
  `__contains__`/`__len__`).
- `ProvenanceStore`: `threading.RLock`; `by_hash` / `verify_chain`
  snapshot the list under the lock, then work on the snapshot.

## Concurrency contract (pinned by tests)

16 threads × 250 ops hammering cache get/put/invalidate, registry
register/unregister/get/supporting/list, provenance append/recent/
by_hash, and full `HugrGate.decide` calls: zero exceptions, hit+miss
counters exactly consistent, registry internally consistent, and the
provenance hash chain verifies afterwards.

## Verification

4 new tests green; full suite 475 passed; mypy clean.
