# Slice 056 — Latency-aware routing

## What existed
Latency pruning used only *declared* `backend.estimated_latency()`
values — usually the 100ms conservative default — so the router planned
against guesses, never measurements.

## What changed
- **`hugrgate/routing/latency.py`** (new):
  - `LatencyTracker`: per-backend EMA (α=0.3) of measured rung latencies;
    `measured()` gated on `min_samples=3`; `estimate(backend)` returns
    the EMA once learned, else the declared estimate.
  - `LatencyAwarePlanner`: plan-time pruning — rungs whose *measured*
    estimate already exceeds `policy.maximum_latency_ms` are dropped
    before execution; survivors carry `params["latency_estimate_ms"]`.
- **`hugrgate/routing/architecture.py`**: `LadderRouterV2` accepts
  `latency_tracker=`; new `note_latencies(audit)` feeds measured rung
  latencies back after every climb (success and exhaustion paths).
- **`benchmarks/routing_latency_056.py`** (new) →
  **`benchmarks/routing_latency_056.json`** (new): reproducible
  measurement artifact — 12 real decisions through three sleep-based
  backends (true 120/15/55ms, all declaring the flat 100ms default),
  staggered confidences so every rung is measured every round.

## Measurement vs baseline (real numbers, this machine)
| backend  | true | declared | measured EMA | declared err | measured err |
|----------|------|----------|--------------|--------------|--------------|
| tortoise | 120  | 100      | ~121.5       | 20.0         | ~1.5         |
| hare     | 15   | 100      | ~15.x        | 85.0         | ~small       |
| mid      | 55   | 100      | ~55.x        | 45.0         | ~small       |
Baseline total abs error: 150.0ms → measured: 9.062ms (**16.55× error
reduction**). Nothing invented; rerun the script to reproduce.

## Integration
Executor `skip_reason` still re-checks latency at run time (plan-time
pruning is an optimization, not a replacement). Provenance, validation,
privacy, abstention unchanged.

## Tests
`tests/test_routing_056.py` (6 tests): EMA math + sample gate + input
validation, measured-latency plan pruning, no-budget passthrough, router
feedback loop after climb, no-tracker safety, and the benchmark artifact
test (runs the script, asserts every backend measured and measured error
< declared error, reduction factor > 1).

## Evidence
- `pytest tests/test_routing_056.py` → 6 passed.
- `python benchmarks/routing_latency_056.py --rounds 12` → artifact as
  above.
