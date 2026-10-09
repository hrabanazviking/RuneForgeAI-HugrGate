# Slice 198 — Jetson benchmark suite

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_bench.py` (19 tests, green — 4 new)

## What existed before

Slice 197 bound the harness to Pi boards; Jetson-class boards had no
baseline and no suite.

## What was built

In `hugrgate/edge/bench.py`:

- **`jetson_baseline(label)`** — resolves Orin Nano / Orin NX /
  Xavier NX to `EdgeBaseline` records (CPU, RAM, TOPS, power budget,
  board notes); normalization strips a leading `jetson-` so
  `"xavier-nx"` and `"Jetson Xavier NX"` both resolve; unknown labels
  raise `ValueError` listing known boards.
- **`jetson_bench_suite(board_label, iterations)`** — the standard
  edge suite bound to the Jetson baseline plus an `npu/detect` case
  (adapter detection cost via a mock + Jetson adapter registry —
  paid on every bootstrap and NPU reselection).
- Both exported in `__all__`; inventory regenerated.

## Measured artifact (real numbers, x86_64 surrogate, 300 iterations)

`benchmarks/edge/jetson-suite-jetson-orin-nano.json`:

| case | mean | p99 |
|---|---|---|
| decide/rules | 97.2 µs | 214.0 µs |
| npu/detect | 53.1 µs | 296.5 µs |
| quant/int8-matvec | 14.8 µs | 47.1 µs |
| quant/int4-roundtrip | 42.3 µs | 169.0 µs |
| storage/put-flush | 217.9 µs | 654.0 µs |
| telemetry/record | 2.7 µs | 4.2 µs |

Compared against `edge-suite-host-baseline.json` (threshold 50%):
no regressions. The artifact's hardware note marks it SURROGATE HOST
with NEEDS_HARDWARE_VALIDATION.

## Integration

- Mirrors the Pi suite structure (slice 197) for the Jetson family;
  `npu/detect` exercises the slice-185 registry.

## Validation notes (Execution Law rule 13)

Surrogate-host numbers. On a real Orin Nano the NPU-attached cases
(not yet measurable here) would diverge most.

## Verification

- `pytest tests/test_edge_bench.py` — 19 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
