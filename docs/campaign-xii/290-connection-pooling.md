# Slice 290 — Connection pooling

**Status:** complete. Commit: `feat(gjallarbu-290)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

`hugrgate/cli.py::cmd_models` minted a throwaway `httpx.Client` per
invocation — a fresh TCP+TLS handshake for every `models` call. The
RPC/SDK clients hold one long-lived client (httpx already pools
per-host inside it), so the CLI's per-command client was the real
pooling gap.

## What was built

- `hugrgate/pool.py` — new module:
  - `ResourcePool(factory, min_size, max_size, idle_timeout_s,
    max_lifetime_s, acquire_timeout_s, health_check, name)`:
    thread-safe generic pool. `acquire()` returns a context-manager
    handle (use-after-return raises `PoolError`); a background reaper
    evicts idle-expired and lifetime-retired resources while keeping
    `min_size` warm; checkout-time health checks discard sick
    resources; exhaustion waits then raises `PoolError`; `shutdown()`
    closes idle resources; `stats()` snapshots everything.
  - `shared_http_client_pool()`: process-wide pool of `httpx.Client`
    (lazy httpx import — `pool.py` has no hard dependency). One client
    per checkout, reused across checkouts, so the client's internal
    per-host connection pool survives across commands.
- `hugrgate/cli.py`: `cmd_models --url` now acquires from the shared
  pool instead of minting a throwaway client.
- `hugrgate/errors.py`: new `PoolError` (`code="pool_error"`,
  `recoverable=True`); registered in `tests/test_errors.py`.

## Tests

`tests/test_perf_290_pool.py` — 17 tests: checkout reuse (identical
object), cap + exhaustion timeout, use-after-return, discard,
idempotent release, health-check discards (incl. raising checks),
idle eviction, warm floor, lifetime retirement, config validation,
factory-failure mapping, post-shutdown rejection, shutdown semantics,
12-thread cap race (≤4 distinct resources, 12 checkouts), shared-pool
singleton + client reuse, `cmd_models` integration via monkeypatched
pool. All green; ruff clean; import-cycle test green.

## Findings fixed during implementation

- Resource *lifetime* was first stamped at checkin (per-cycle age) —
  corrected to build-time age via an `id(resource) → born` map, so
  `max_lifetime_s` is a true total-age bound.
- The reaper's `time.sleep` stalled `shutdown()` up to 5s (test suite
  took 63s); the reaper now waits wakeably on the condition — 2.3s.
