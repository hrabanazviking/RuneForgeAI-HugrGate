# Slice 288 — Deadline scheduling

**Status:** complete. Commit: `feat(gjallarbu-288)` on `gjallarbu/campaign-xii`.

## What existed before

The scheduler (slices 285–287) knew nothing of time bounds: `submit`
accepted a `deadline` and validated it wasn't past, but nothing
scheduled by it. A task with a 50ms deadline could wait out a 5s
batching window.

## What was built

- `hugrgate/scheduler.py`:
  - `SchedulerConfig(deadline_enabled, drop_late)` — validated bools.
  - **Earliest-deadline-first selection**: survivors sort by
    `(deadline or +inf, ...)`; no-deadline tasks last. With priority
    also enabled, deadline is the primary key, effective priority the
    tiebreak.
  - **Deadline-aware collection**: the window wait is capped at the
    earliest candidate deadline (minus 1ms epsilon) — batching never
    blows a task's lateness budget to fill a batch.
  - **Miss accounting**: tasks already late at selection are dropped
    (future fails with `SchedulerError("... missed its deadline before
    execution")`) or executed anyway when `drop_late=False` — both
    increment `stats()["deadline_misses"]`.
  - `submit` deadline type validation (`bool` and non-numeric
    rejected with `SchedulerError`).
- Lock-order audit along the way: the miss counter lives under `_cond`
  (not nested inside `_stats_lock`) — `stats()` reads cond-guarded
  state first, then stats-guarded state. Documented lock order:
  `_cond` → `_stats`.

## Tests

`tests/test_perf_288_deadline.py` — 9 tests: config/submit validation,
EDF ordering (latest submitted first, earliest deadline still runs
first), deadline-aware collection (tight deadline beats a 5s window),
late drop (future fails, miss counted), `drop_late=False` (executes,
still counted), on-time tasks not counted, deadline+priority tiebreak,
deadlines ignored when disabled. Slices 285–287 suites re-verified
(38 green). Stable over 3 runs. Ruff clean; import-cycle test green.
