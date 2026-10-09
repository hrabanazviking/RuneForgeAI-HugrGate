# Slice 285 — Batch scheduler v2

**Status:** complete. Commit: `feat(gjallarbu-285)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

The daemon's `BatchingQueue` (slice 018) is asyncio-only and coupled to
daemon wire types (`spec_dict`, per-submit futures) — unusable from sync
code and un-reusable elsewhere. This slice builds the general engine.

## What was built

- `hugrgate/scheduler.py` — new module:
  - `BatchScheduler(config, executor)`: thread-safe, no event loop
    needed. `submit(fn, *args, **kwargs)` returns a
    `concurrent.futures.Future`; a background worker coalesces into
    batches (`max_batch_size` or `batch_window_s`, whichever first).
  - `BatchExecutor` protocol + `ThreadPoolBatchExecutor` default
    (per-task callables in a worker pool; exceptions routed to the
    owning task's future).
  - `SchedulerConfig` — all knobs validated, raising `SchedulerError`
    (not `ValueError`).
  - Backpressure: `max_queue_depth` overflow raises `SchedulerError`
    (recoverable); past-deadline submissions refused at the door.
  - `drain(timeout)` interrupts the batching window so queued work
    executes promptly; `shutdown()` drains then halts.
  - `stats()`: batches, tasks, avg/max batch size, queue-wait p50,
    batch-exec p50, depth, accepting flag.
  - `_Task` already carries `priority` and `deadline` — slices 287/288
    slot in without reshaping.
- `hugrgate/errors.py`: new `SchedulerError`
  (`code="scheduler_error"`, `recoverable=True`); registered in
  `tests/test_errors.py`.

## Tests

`tests/test_perf_285_scheduler.py` — 20 tests: burst coalescing
(20 tasks → ≤4 batches), max-batch splitting, per-task exception
routing, broken-executor containment, queue-full backpressure (with a
blocking executor), post-shutdown/non-callable/past-deadline
rejections, drain success + timeout-false, stats shape, 4-thread × 25
concurrent submitters (100 tasks, all correct). Stable across 3 runs.
All green; ruff clean; import-cycle test green.

## Concurrency findings (fixed during implementation)

- `drain()` first checked only queue emptiness: a batch pulled but
  still executing (or still assembling inside a long window) was
  invisible. Fixed with an atomic queue→in-flight handoff under the
  condition lock plus a `_flush_requested` flag so `drain()` interrupts
  the window instead of waiting it out.
- A `zip(futures, tasks)` variable swap routed pool futures into task
  slots — caught by tests before commit.
