# Slice 262 — CPU-starvation test

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_cpu_starvation.py` (5 tests, green)

## What existed before

`hugrgate/timeout.py` enforced deadlines on daemon worker threads —
but nothing proved the deadline machinery survives a **slow
machine**. Under CPU starvation every unit of work dilates; the
danger is a timeout system that measures "work progress" instead of
real time and never fires, hanging the caller behind ever-slower
backends.

## What was built

`CPUStarvationSimulator` in `hugrgate/chaos/resources.py`:

- `share` in (0, 1] — the fraction of CPU the process receives
  (validated); `dilation = 1/share`; `stretched(duration_s)`
  models how long work lasts when starved.
- `starve_backend(backend, base_delay_s)` wraps a backend so its
  `evaluate` dilates `base_delay_s` of work before delegating;
  transparent (name, `supports`, capabilities + `cpu_share`).

## Resilience proof

- **Deadlines fire in real time**: at 4× starvation (0.4 s of work
  → 1.6 s), a 0.5 s `TimeoutBackend` deadline still raises
  `TimeoutError` at ~0.5 s of real time — the timeout measures the
  monotonic clock, not work progress.
- **Failover under starvation**: at 10× starvation the fallback
  chain routes to the healthy backend after the deadline, never
  waiting out the 3 s of dilated work.

## Verification

- 5 tests: share validation, dilation math, backend wrapping
  transparency + arg validation, real-time deadline firing
  (0.5 ≤ elapsed < 1.6), fallback routing under 10× starvation.
- `ruff check` clean.
