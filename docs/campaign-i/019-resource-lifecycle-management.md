# Slice 019 — Resource lifecycle management

**Date:** 2026-10-09 · **Tests:** `tests/test_resource_lifecycle.py` (8 tests)

## Audit of what existed

Explicit lifecycles: `BatchingQueue.start/stop`, `HugrGateClient.close`,
daemon threads (`daemon=True`), timeout worker threads
(`daemon=True`). Missing: no way to release backend resources
(model weights, handles), no context-manager ergonomics, and the
provenance store grew **unbounded** (every `decide` appends forever).

## Changes

- `Backend.close()` (backend.py): new optional hook, default no-op,
  for backends holding weights/handles/subprocesses.
- `HugrGate.close()` (core.py): calls `close()` on every registered
  backend, best-effort (a failing `close()` is logged, never blocks
  the rest). `HugrGate` is now a context manager (`with HugrGate()`
  closes on exit).
- `BatchingQueue.__aenter__` / `__aexit__` (daemon.py): async context
  manager (`async with BatchingQueue(gate)` starts/stops cleanly).
- `ProvenanceStore(max_records=...)` (provenance.py): bounds memory;
  on eviction the hash of the last dropped record becomes the
  checkpoint `_floor_hash`, so `verify_chain()` stays valid across
  the eviction boundary. `evicted_count()` reports drops. Default
  remains unbounded.

## Verification

8 new tests green (incl. best-effort close with a failing backend,
context-manager close, chain verification after 7 evictions); full
suite 489 passed; mypy clean.
