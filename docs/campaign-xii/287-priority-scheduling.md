# Slice 287 — Priority scheduling

**Status:** complete. Commit: `feat(gjallarbu-287)` on `gjallarbu/campaign-xii`.

## What existed before

Slice 285's scheduler was strictly FIFO; the `_Task` record carried a
`priority` field nothing read. No lane differentiation existed.

## What was built

- `hugrgate/scheduler.py`:
  - `SchedulerConfig(priority_enabled, starvation_horizon_s)` —
    validated (`bool`, `> 0`).
  - Priority mode: each batch is chosen from the window's held
    candidates by **effective priority** =
    `priority + wait_time / starvation_horizon_s`, highest first, ties
    by earliest submission. The wait-time term is an aging guard: a
    priority-0 task waiting one horizon outranks a fresh priority-1
    task, so no lane can starve under any arrival pattern. Unchosen
    tasks return to the front of the queue in arrival order.
  - FIFO mode is byte-for-byte the old behavior (fast path: stop
    collecting at cap; no re-sorting).
  - `submit(..., priority=...)` validated (`int`, else
    `SchedulerError`).
  - `stats()` reports `priority_enabled`.
- Backpressure accounting hardened along the way: tasks held in the
  in-progress assembly are now counted (`_assembly_held`) together
  with the queue against `max_queue_depth` — the restructure had made
  them invisible, which broke slice 285's queue-full test. Fixed and
  re-verified.

## Tests

`tests/test_perf_287_priority.py` — 7 tests: config/submit validation,
high-priority queue jump (batch composition asserted), deterministic
single-slot execution order (high first, then FIFO lows), FIFO
preservation with priority disabled (priorities ignored), **no
starvation under continuous high-priority pressure** (low completes;
aging math holds), stats flag. Slices 285–286 suites re-run green
(38 total, 3 consecutive runs). Ruff clean; import-cycle test green.
