# Slice 269 — Bulkhead (per-backend concurrency caps)

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_bulkhead.py` (13 tests, green)

## What existed before

No concurrency isolation: N concurrent `decide()` calls against one
hanging backend (slice 253's HANG mode) could exhaust the caller's
threads and starve every other backend behind them. The threat was
real and demonstrated — the chaos toolkit could hang a backend, but
the core had no bulkhead to contain it.

## What was built

**`hugrgate/chaos/bulkhead.py`** — `BulkheadExecutor` (exported from
`hugrgate.chaos`):

- Per-backend semaphores: `default_cap` + per-backend `caps` dict,
  lanes created lazily, thread-safe.
- `execute(backend_name, fn, *args, timeout_s=0.0, **kwargs)`:
  fail-fast by default (`timeout_s=0` → `BulkheadRejected`
  immediately); `None` waits indefinitely; positive values wait
  up to that long. `fn` exceptions propagate unchanged; the lane
  is always released.
- `stats()` per-backend snapshot: `cap`, `in_flight`,
  `executed_total`, `rejected_total`. `cap_for()` for inspection.

**New taxonomy error** `BulkheadRejected(BackendError)` — code
`bulkhead_rejected`, `recoverable=True`, registered in
`tests/test_errors.py`. Backend-family so existing failover
handlers apply (shedding to another backend is the correct
response to a full bulkhead).

**Integration:** `HugrGate.decide`/`adecide(..., bulkhead=None)`
— opt-in, `None` keeps uncapped behavior. Composition order is
deliberate: bulkhead outermost, so one logical call holds one
lane across its retries.

**Retry policy update** (slice 268): `default_retry_policy`
excludes `BulkheadRejected` — a fail-fast rejection is a signal
to shed load, not to spin against a full bulkhead with no
backoff. `retry_with_budget` burns zero tokens on it.

## Verification

- 13 tests: fail-fast rejection with error details, backend
  isolation (stuck backend doesn't affect others), per-backend
  caps, timed wait success + expiry, 20 threads against cap 3
  (peak exactly 3), lane release on exception, stats counters,
  argument validation, policy exclusion, zero-token spin check.
- Two `decide`-level integration tests: stuck backend →
  `BulkheadRejected` fast while another backend decides fine;
  lane held across a retry (`in_flight == 1`, one retry token
  consumed, second decide rejected).
- `test_errors.py` (raise-site gate incl. the new raise),
  import-cycle gate, `ruff check` — all green.
