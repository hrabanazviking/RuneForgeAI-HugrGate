# Slice 196 — Edge benchmark harness

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_bench.py` (12 tests, green)

## What existed before

`hugrgate/bench.py` measured core throughput; nothing measured edge
workloads, and nothing produced a comparable artifact with hardware
context.

## What was built

`hugrgate/edge/bench.py`:

- **`EdgeBenchmark`** — named cases (warmup + timed iterations,
  mean/p50/p99/min/max, ops/s) with an injectable timer for
  deterministic tests; duplicate/degenerate definitions rejected.
- **Artifacts** (`edge-bench/1` schema): JSON carrying timestamp,
  host platform, target board baseline, and a `hardware_note` that
  states plainly whether the numbers came from real edge silicon or
  a surrogate host. `save()`/`load_artifact()` validate the schema.
- **`compare_artifacts(current, baseline, threshold)`** — per-case
  ratio/delta_pct/regressed flags; missing cases reported, never
  dropped; non-positive samples rejected.
- **`edge_bench_suite()`** — representative Campaign VIII workloads:
  `decide/rules`, `quant/int8-matvec`, `quant/int4-roundtrip`,
  `storage/put-flush`, `telemetry/record`.

## Measured artifact (real numbers, this host x86_64, 300 iterations)

`benchmarks/edge/edge-suite-host.json` (baseline copy alongside):

| case | mean | p50 | p99 |
|---|---|---|---|
| decide/rules | 109.6 µs | 90.0 µs | 321.2 µs |
| quant/int8-matvec | 13.3 µs | 12.4 µs | 60.6 µs |
| quant/int4-roundtrip | 43.2 µs | 38.4 µs | 114.0 µs |
| storage/put-flush | 375.3 µs | 121.4 µs | 4613.9 µs |
| telemetry/record | 3.2 µs | 2.7 µs | 13.9 µs |

**Real finding:** comparing two consecutive runs flagged
`storage/put-flush` at +72.5% (threshold 50%) — the append-only log
grows with every iteration, so later flushes rewrite more bytes
(p50 121 µs vs p99 4613 µs within the run). This is the design's
honest cost curve, not a bug: it argues for periodic `compact()` on
write-heavy edge workloads.

## Integration

- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended. Slices 197/198 bind board baselines.

## Validation notes (Execution Law rule 13)

x86_64 surrogate numbers — every figure needs on-device re-measurement
(slices 197/198). The artifact says so itself in `hardware_note`.

## Verification

- `pytest tests/test_edge_bench.py` — 12 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
