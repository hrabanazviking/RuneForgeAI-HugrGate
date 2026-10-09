# Slice 276 — Profiler integration

**Status:** complete. Commit: `feat(gjallarbu-276)` on `gjallarbu/campaign-xii`.

## What existed before

Campaign XII had no profiling story at all: `hugrgate/bench.py` (slice 45)
measured decision-level accuracy/latency/throughput, and the edge
benchmarks (slices 196–198) measured platform suites, but nothing could
say *where* time went inside a `decide()` call. This slice closes that
gap rather than duplicating the benchmark harnesses.

## What was built

- `hugrgate/profiling.py` — new module:
  - `DecisionProfiler.profile(fn, ...)` — runs any callable under
    `cProfile`, returns `(result, ProfileReport)`; callable exceptions
    propagate untouched.
  - `DecisionProfiler.profile_decision(gate, state, spec, policy, ...)`
    — profiles one `HugrGate.decide`; attaches a compact top-10 summary
    to `result.metadata["profile"]` **unless** the policy's
    `privacy_class` is `"strict"` (profile frames name backend
    internals — strict privacy must not leak them into records).
  - `ProfileReport` — `top(n)` (cumtime-ranked), `to_dict()`,
    `to_markdown()` renderers.
  - `profile_region(name)` / `region_report()` — nested cheap timers for
    coarse instrumentation without cProfile overhead.
- `hugrgate/errors.py` — new `ProfilingError` (`code="profiling_error"`,
  `recoverable=True`); registered in `tests/test_errors.py`
  (`ALL_ERRORS`, `EXPECTED_CODES`, `EXPECTED_RECOVERABLE`).

## Tests

`tests/test_perf_276_profiling.py` — 16 tests: profile success frames,
error propagation, top-ordering, bad-`n` rejection, serialization,
config validation (sort key, max_entries), metadata attach, strict-privacy
suppression, opt-out, entry trimming, region nesting/reset/exception
accounting. All green; ruff gate clean; import-cycle test green.

## Architectural notes

- Profiler config mistakes raise taxonomy errors, never stdlib `ValueError`.
- Privacy integration is load-bearing, not decorative: the suppression
  path is tested.
- `max_entries` trimming keeps reports bounded for long-lived processes.
