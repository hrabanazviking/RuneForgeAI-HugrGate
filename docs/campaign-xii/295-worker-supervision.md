# Slice 295 — Worker supervision

**Status:** complete. Commit: `feat(gjallarbu-295)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

Long-running gate workers — the pool reaper (slice 290), the
scheduler loop (slice 285), per-model session pools (slice 291) —
ran as bare daemon threads: if one died (exception, stall), nothing
noticed and nothing recovered. Thread death was silent.

## What was built

- `hugrgate/supervision.py` — new module:
  - `Supervisor`: registers named workers (`target(ctx)`), starts a
    watchdog thread, restarts unhealthy workers.
  - `WorkerContext`: `heartbeat()` + `should_stop` handed to each
    target.
  - Unhealthy = heartbeat older than `heartbeat_timeout_s` **or**
    thread dead (exception captured to `last_error`, or silent
    return — both restart).
  - Restart budget: `max_restarts` per `restart_window_s`; exhaustion
    **escalates** — `on_escalation(name, reason, record)` fires, the
    worker is marked failed, no more silent restarts.
  - `remove_worker`, idempotent `stop()`, `stats()` snapshot.
- `hugrgate/errors.py`: new `SupervisionError`
  (`code="supervision_error"`, `recoverable=True`) — reserved for
  supervisor *misuse*; worker failures are handled by
  restart/escalation, never exceptions. Registered in
  `tests/test_errors.py`.

## Tests

`tests/test_perf_295_supervision.py` — 13 tests: healthy workers left
alone, stale heartbeat → restart (accumulating), one-shot exception
→ restart with healthy replacement, silent return → restart, budget
exhaustion → escalation (handler called once, no further restarts),
remove/duplicate/double-start/validation, pre-start registration,
handler-exception survival, heartbeat age in stats, idempotent stop.
Verified stable over 20 consecutive full-file runs (0 failures).

## Findings fixed during implementation

- **Real race (not a test bug):** `escalated=True` was published
  *before* the escalation handler ran (the worker join sat between),
  so a poller could observe escalation with no notification
  delivered — a broken API invariant. Restructured so the flag is
  set only after the handler returns: `escalated` in `stats()`
  now implies the notification was delivered. The test caught this
  as flakiness (9/15 failing); after the fix, 20/20 green.
