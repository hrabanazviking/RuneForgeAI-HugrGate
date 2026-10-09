# Slice 283 — Async backend API

**Status:** complete. Commit: `feat(gjallarbu-283)` on `gjallarbu/campaign-xii`.

## What existed before

Slice 282 built the async *mechanism* (`asyncx`: protocol, dispatch,
`adecide`, `adecide_batch`). Callers still had no public async API
surface: no request object, no timeout story, no streaming.

## What was built

- `hugrgate/async_backend.py` — new module, the public async API:
  - `AsyncRequest`: state/spec/policy/context/backend_name/timeout_s,
    validated (`SpecError` on bad timeout or non-mapping state).
  - `AsyncGate`: async facade over `HugrGate`:
    - `adecide(...)` — single decision with timeout;
    - `adecide_many(requests, max_concurrency)` — bounded-concurrency
      batch, input order preserved, first exception propagates with
      the rest cancelled;
    - `astream(requests, ...)` — async generator yielding
      `(index, result)` as decisions complete; breaking out stops new
      work, in-flight finishes unless its own timeout fires;
    - `register`/`close` passthroughs; closed-gate use raises
      `SpecError`; `close()` idempotent.
  - Timeout semantics (deliberate, documented): explicit `timeout_s`
    wins → else the policy's `maximum_latency_ms` → else unbounded.
    Expiry cancels the evaluation and raises taxonomy `TimeoutError`
    (`code="timeout"`, recoverable) with `budget_ms`/`elapsed_ms`
    details — never a bare `asyncio.TimeoutError`.
  - Re-exports `evaluate_async` for callers that only need dispatch.

## Tests

`tests/test_perf_283_async_api.py` — 16 tests: request validation,
single decision, explicit-timeout firing (code + details asserted),
policy-budget timeout, unbounded path, dispatch re-export, batch order
preservation, empty batch, first-error propagation, stream completion
ordering (verifiably *not* input order), early-break work bounding,
empty stream, closed-gate rejection, idempotent close. All green; ruff
clean; import-cycle test green.
