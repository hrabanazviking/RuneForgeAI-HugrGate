# Slice 194 — Edge watchdog

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_watchdog.py` (8 tests, green)

## What existed before

No supervision anywhere in the edge runtime — a wedged inference
loop on a remote Pi would sit silent until someone noticed.

## What was built

`hugrgate/edge/watchdog.py` — `EdgeWatchdog`:

- **Heartbeat/deadline**: the supervised loop calls `heartbeat()`;
  `check()` returns `"ok"`/`"missed"` against an injected clock
  (deterministic tests, no sleeps).
- **Miss policies**: `LOG` records; `RESTART` invokes the restart
  callback and re-arms the deadline; a custom `on_miss(misses)`
  callable can page, shed load, or escalate. Policy callbacks run
  outside the lock so they may call back into the watchdog.
- **`max_misses` latch**: once reached, the watchdog records further
  misses but stops firing the policy — a flapping restart loop is
  worse than a recorded death.
- **Background supervision**: optional daemon thread on a
  configurable interval; `start()`/`stop()` idempotent.
- `status()` is JSON-serializable (misses, restarts, exhausted,
  seconds-to-deadline).

## Integration

- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended. The watchdog is the supervisor slice
  192's bootstrap and slice 180's "leave core 0 for the watchdog"
  affinity profile were built for.

## Validation notes (Execution Law rule 13)

Timeout values are deployment-specific; the restart callback's real
behavior (process restart vs. systemd notify) is integration-defined.

## Verification

- `pytest tests/test_edge_watchdog.py` — 8 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
