# Slice 279 — Allocation profiling

**Status:** complete. Commit: `feat(gjallarbu-279)` on `gjallarbu/campaign-xii`.

## What existed before

Slices 276–278 profiled *time*. Nothing measured heap allocations, so
copy-heavy paths (the target of slice 280) had no evidence base. This
slice adds allocation tracking on the same integration terms as the
time profiler.

## What was built

- `hugrgate/allocprof.py` — new module:
  - `AllocationProfiler(nframes, top_n, attach_to_metadata)` over
    `tracemalloc`: `start()`/`stop()` (polite — never stops tracing it
    didn't start), `track(label)` context manager yielding a carrier
    with `.report`, `snapshot_report()` heap census,
    `profile_decision(gate, ...)` diffing the heap across one decide.
  - `AllocationReport` — `delta_bytes`, `top(n)`, `to_dict()`,
    `to_markdown()`; sites attributed to the outermost allocating
    frame (`filename:lineno`).
  - Strict-privacy rule reused from slice 276: only aggregate totals
    reach `result.metadata["allocations"]`; site lists stay local.
  - Misuse raises the slice-276 `ProfilingError` (Anti-Checkbox: reuse,
    don't duplicate).

## Tests

`tests/test_perf_279_allocprof.py` — 10 tests: site attribution of a
real 20k-int allocation, serialization, `top()` validation, constructor
validation, snapshot-without-tracing rejection, census, start/stop
idempotence + politeness toward foreign tracing, decide attach,
strict-privacy suppression. All green; ruff clean; import-cycle test
green.

## Finding worth recording

A region's allocation diff only sees *live* bytes — the first version
of the attribution test allocated and dropped a 20k list, and the diff
showed ~680 bytes of tracemalloc internals. The test now keeps the
allocation alive, which is also the correct mental model for leak
hunting: diffs measure retained growth, not churn.
