# Slice 282 — Async core path

**Status:** complete. Commit: `feat(gjallarbu-282)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

Slice 018's `HugrGate.adecide` pushed the *entire* decision into a
worker thread via `asyncio.to_thread` — including backends that could
have awaited natively. There was no async backend contract at all.

## What was built

- `hugrgate/asyncx.py` — new module:
  - `AsyncBackend`: runtime-checkable structural `Protocol` (only method
    members — `runtime_checkable` protocols reject non-method members
    in `isinstance`, found the hard way).
  - `AsyncBackendBase(Backend)`: default `aevaluate` delegates to
    `asyncio.to_thread(self.evaluate, ...)`; override for true
    non-blocking inference.
  - `is_async_backend(backend)`: structural detection — duck-typed
    backends qualify without inheritance.
  - `evaluate_async(backend, ...)`: the single dispatch — await
    natively async, thread off sync. Exceptions propagate unchanged.
- `hugrgate/core.py`:
  - `decide()` refactored into `_resolve_backend` +
    `_translate_backend_error` + `_finalize_result` (post-evaluation
    pipeline: latency stamp, result validation, policy gate,
    provenance). Sync and async share all three — one semantics, two
    transports.
  - `adecide()` rewritten: validation + backend resolution on the loop,
    `evaluate_async` for inference, shared finalizer. Same contract,
    same errors, same provenance as `decide`.
  - New `adecide_batch(states, spec, policy, max_concurrency=8)`:
    semaphore-bounded concurrent decisions, input order preserved,
    `max_concurrency` validated (`SpecError`).
- `tests/test_dependency_rules.py`: `_STDLIB` allowlist was missing
  genuine stdlib modules (`cProfile`, `pstats`, `tracemalloc`,
  `timeit`) — added with a Campaign XII comment. The gate now passes
  instead of misclassifying stdlib as undeclared third-party.

## Tests

`tests/test_perf_282_async_core.py` — 13 tests: structural protocol
detection (incl. duck-typed, inheritance-free backends), native
evaluation stays on the loop thread (thread-id assertion), sync
backends still thread off, default-base delegation, adecide/decide
contract parity (fields, verdict, provenance count), error semantics
(Abstention/BackendError/unexpected→BackendError/unknown backend),
policy abstention, batch ordering + concurrency bound (in-flight max
asserted) + bad-concurrency rejection. Existing
`test_async_readiness.py` still green. All green; ruff clean;
import-cycle and dependency gates green.

## Design note

`AsyncBackendBase.evaluate` stays abstract: an async-only backend used
on the sync path must fail loudly at instantiation, not mysteriously
at runtime.
