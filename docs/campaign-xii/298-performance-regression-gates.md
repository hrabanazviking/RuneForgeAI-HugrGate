# Slice 298 — Performance regression gates

**Status:** complete. Commit: `feat(gjallarbu-298)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

Slices 292–293 produced real speedups (cache key −17%, result copy
−56%, lock hold 44µs→1µs) with **nothing preventing silent
regression**: no committed baseline, no gate. Any later change could
erase the wins unnoticed.

## What was built

- `hugrgate/perfgate.py` — new module:
  - `PerfGate`: `add_gate(name, metric_fn, direction, max_regression_frac, samples, unit)`;
    `record_baseline()` measures (median of N samples — medians
    resist the VM noise documented in slice 292) and writes
    `benchmarks/perf_baseline.json`; `evaluate()` compares live
    medians to the artifact; `check()` raises `PerfGateError`
    listing every breached gate.
  - Directions `"lower-better"` (latency) / `"higher-better"`
    (throughput); a direction change since baseline is itself an
    error (conscious re-baseline required).
  - `default_gates()`: `cache.key_us` and `cache.get_hit_us`
    (the slices 292–293 hot paths), 25% tolerance.
- `benchmarks/perf_baseline.json` — **real measured artifact**,
  recorded live on this machine: `cache.key_us` 13.42µs,
  `cache.get_hit_us` 20.08µs (median of 7).
- `hugrgate/errors.py`: new `PerfGateError`
  (`code="perfgate_error"`, **`recoverable=False`** — a breached
  gate is a hard quality signal; fix it or re-baseline, never
  catch-and-retry). Registered in `tests/test_errors.py`.

## Tests

`tests/test_perf_298_perfgate.py` — 15 tests: regression math both
directions, zero-baseline edge, registration validation, pass
within tolerance, breach raises non-recoverable with detail,
higher-better breach, improvement passes, missing baseline file,
missing gate entry, direction-change error, metric exception
wrapping, record/evaluate round-trip, median-outlier resistance,
and the default gates passing against the committed artifact. All
green; ruff clean; taxonomy and import-cycle gates green.
