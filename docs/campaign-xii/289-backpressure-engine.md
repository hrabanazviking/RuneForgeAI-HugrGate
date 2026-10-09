# Slice 289 — Backpressure engine

**Status:** complete. Commit: `feat(gjallarbu-289)` on `gjallarbu/campaign-xii`.

## What existed before

The cluster had `AdmissionController` (slice 218, token bucket for
*remote* work messages); the scheduler had only a queue-depth cap
(`SchedulerError` on overflow). Nothing limited *admission rate* or
*in-flight* (queued + executing) work locally.

## What was built

- `hugrgate/backpressure.py` — new module:
  - `TokenBucket(capacity, refill_per_second)`: thread-safe,
    `take()`/`retry_after_s()`/`available`; misconfiguration raises
    `BackpressureError`.
  - `BackpressureEngine(max_inflight, rate_per_second, burst_capacity)`:
    `lease()` admits one unit or raises `BackpressureError` with
    `reason` (`"inflight_cap"` | `"rate_limit"`) and `retry_after_s`
    details; `try_lease()` returns `None` instead; `Lease` is
    idempotent-release and a context manager; `stats()` reports
    admitted/rejected/inflight breakdowns.
  - Slice-218 lesson preserved: shedding is for *work* — `drain()` and
    `shutdown()` bypass admission (never shed the healing signal).
- `hugrgate/scheduler.py`: `BatchScheduler(..., backpressure=engine)` —
  every `submit` leases a slot, released via future done-callback when
  the task settles (success, failure, deadline drop, executor bug);
  saturation raises `BackpressureError` at the producer. Type-checked
  (`SchedulerError` otherwise). `stats()` includes engine stats.
- `hugrgate/errors.py`: new `BackpressureError`
  (`code="backpressure_error"`, `recoverable=True`); registered in
  `tests/test_errors.py`.

## Tests

`tests/test_perf_289_backpressure.py` — 15 tests: bucket take/refill/
retry-after/validation, inflight-cap rejection (reason + details
asserted), try_lease, idempotent + context-manager release, rate-limit
rejection with measured `retry_after_s`, stats shape, 20-thread
admission race (exactly 8 admitted, 12 rejected), scheduler integration
(producer-side rejection while blocked; slots free on settle;
admission works again), no-engine behavior unchanged, bad engine type
rejected. Slices 285–288 suites re-verified (47 green). Ruff clean;
import-cycle + error-taxonomy tests green.
