# Slice 018 — Async-readiness audit

**Date:** 2026-10-09 · **Tests:** `tests/test_async_readiness.py` (6 tests)

## Audit of what existed

- `BatchingQueue` (daemon): async submit/worker with
  `asyncio.to_thread` for inference — the event loop never blocks.
- `server.py`: FastAPI + uvicorn — async-capable HTTP front.
- Everything else (`HugrGate.decide`, backends) is synchronous by
  design; the documented async pattern was `asyncio.to_thread`, but
  no first-class async entry point existed.

## Real bug found and fixed

`BatchingQueue.stop()` could **strand submitters forever**:
`_drain()` waited only for the queue to look empty, then cancelled
the worker — a batch pulled from the queue but still executing never
resolved its submitters' futures, and `await future` hung forever.

Fix (`hugrgate/daemon.py`):
- `_worker` counts a batch in-flight from the moment its first item
  leaves the queue (increment placed before batch assembly, so
  `_drain` cannot observe "empty and idle" mid-assembly);
- `_drain` waits for queue-empty **and** in-flight == 0;
- on drain timeout, still-queued futures fail fast with `QueueFull`
  (`_fail_pending`), and a worker cancelled mid-batch fails its
  in-flight futures instead of abandoning them.

## New capability

`HugrGate.adecide(...)` (`hugrgate/core.py`): async variant of
`decide` via `asyncio.to_thread` — same contract, same errors; the
event loop stays responsive during blocking inference (pinned by a
test that ticks the loop while a 300 ms backend runs).

## Verification

6 new tests green (incl. stop-during-in-flight and drain-timeout
scenarios that hung before the fix); full suite 481 passed; mypy
clean.
