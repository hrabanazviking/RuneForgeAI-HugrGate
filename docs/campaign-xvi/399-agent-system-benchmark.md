# Slice 399 — Agent-system benchmark

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_399_benchmark.py` (5 tests)

## What already existed

The simulator (398) rehearses; `hugrgate.bench` benchmarks
*backends*. Nothing measured *agent systems* across scenarios.

## What was built

- `hugrgate/agents/benchmark.py` — `AgentBenchmark`:
  `run(sim_factory, config)` executes each named scenario
  `repetitions` times on fresh simulators (isolated state),
  seeds derived deterministically (`seed + rep`), aggregates
  success rate (mean/min/max), failure/loop/runaway/escalation
  totals, and wall-clock p50/p95 latencies. Cross-repetition
  variance is flagged in `notes`. `BenchmarkReport.to_dict()`
  is wire-safe for CI and the release gate.

## Verification

`pytest tests/test_agents_399_benchmark.py` — 5 passed
(aggregation math, wire-safety, nondeterminism notes,
percentile edges, config validation). `ruff check` clean,
`mypy` clean.
