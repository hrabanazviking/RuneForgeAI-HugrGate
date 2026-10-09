# Slice 197 — Pi benchmark suite

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_bench.py` (15 tests, green — 3 new)

## What existed before

Slice 196's harness measured generic edge workloads with no board
binding — a Pi 5 and a Pi Zero 2 W would produce identically-labeled
artifacts.

## What was built

`pi_bench_suite(board_label, iterations)` in `hugrgate/edge/bench.py`:

- Binds `edge_bench_suite()` to `pi_baseline(board_label)` — unknown
  labels raise `ValueError` listing known models (no guessed
  baselines).
- Adds two Pi-relevant cases: `platform/audit` (ARM64 audit cost, paid
  on every bootstrap) and `memory/refresh` (mode-derivation cost,
  driven by a meminfo fixture sized to the board's RAM).
- Suite name encodes the board (`pi-suite-raspberry-pi-5`); the
  artifact carries the full baseline and the surrogate-host
  hardware note.

## Measured artifact (real numbers, x86_64 surrogate, 300 iterations)

`benchmarks/edge/pi-suite-raspberry-pi-5.json`:

| case | mean | p99 |
|---|---|---|
| decide/rules | 91.8 µs | 214.2 µs |
| platform/audit | 4.9 µs | 11.4 µs |
| memory/refresh | 4.3 µs | 4.8 µs |
| quant/int8-matvec | 13.6 µs | 33.4 µs |
| quant/int4-roundtrip | 39.3 µs | 48.8 µs |
| storage/put-flush | 198.5 µs | 466.6 µs |
| telemetry/record | 3.0 µs | 5.3 µs |

Compared against `edge-suite-host-baseline.json` (threshold 50%):
no regressions; shared cases within ±9% run-to-run (ratio 0.91–1.09);
the two new cases correctly report `missing-in-baseline`.

## Integration

- Same module/layer as slice 196; inventory regenerated. Slice 198
  adds the Jetson suite beside it.

## Validation notes (Execution Law rule 13)

Surrogate-host numbers — the artifact states this itself. On a real
Pi 5, expect the audit/refresh cases to dominate relatively (slower
storage, faster relative NEON paths).

## Verification

- `pytest tests/test_edge_bench.py` — 15 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
