# Slice 474 — Autotuning benchmark

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_474_benchmark.py` (5 tests)

## What existed

Tuner quality was asserted by unit tests on synthetic data, but
there was no harness measuring "how much does this tuner actually
improve the config" end-to-end.

## What changed

- `hugrgate/autotune/benchmark.py`: `AutotuneBenchmark` runs each
  `BenchmarkScenario` end-to-end through a real controller (offline
  mode, journaling driver), then scores the baseline config and the
  tuned config with the *same* replay evaluator on the *same*
  recorded data. `BenchmarkReport` carries per-scenario
  baseline/tuned/improvement/wall-time plus a `summary()` table and
  `to_dict()`; measured figures (not wall time or random proposal
  ids) are deterministic across runs. Reports are plain data —
  persisting them is the caller's job; measurement artifacts are
  never committed.

## Verification

5 new tests (three scenarios — threshold F1, latency budget,
cache policy — all measurably beat their baselines; determinism of
measured figures; report serialization; bad-scenario rejection;
replay-crash surfacing); `ruff` and `mypy` clean.
