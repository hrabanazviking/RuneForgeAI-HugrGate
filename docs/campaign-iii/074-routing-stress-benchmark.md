# Slice 074 — Routing stress benchmark

## What existed
No throughput characterization of any router: v1 or v2, serial or
speculative.

## What changed
- **`benchmarks/routing_stress_074.py`** →
  **`benchmarks/routing_stress_074.json`**: measures routing-machinery
  overhead with near-instant backends and staggered confidences (full
  climb every decision). Configurations: v1 baseline serial, v2 serial,
  v2 plan-only, v2 parallel, v2 hedged, v2 early-exit × 4/16 rungs.
  Reports decisions/sec, mean/p50/p99 per decision, plus per-variant
  ratios vs the v1 baseline.

## Measurement vs baseline (real numbers, this machine, 200
decisions/config)
| config (4 rungs) | dec/s | vs v1 |
|---|---|---|
| v1 baseline serial | 10,086 | 1.000x |
| v2 serial | 5,516 | 0.547x |
| v2 early-exit | 13,888 | 1.377x |
| v2 hedged | 777 | 0.077x |
| v2 parallel | 675 | 0.067x |
| v2 plan-only | 47,411 | — |

At 16 rungs: v1 5,693/s; v2 serial 0.807x; early-exit 0.746x;
parallel 0.037x; hedged 0.050x.

**Reading:** the v2 plan/execute split costs real overhead on
instant backends (plan construction + fingerprinting ≈ 0.08ms/decision
at 4 rungs) — the price of inspectability, replay, and simulation.
Thread-pool executors (parallel/hedged) are far slower than serial when
backends are instant; speculation only pays when backends are slow
(slices 064/065 prove the win with timed tests on sleeping backends).
Plan-only throughput (47k/s) bounds how cheap planning itself is.
Nothing invented; rerun the script to reproduce.

## Integration
Benchmark-only; no routing behavior changed.

## Tests
`tests/test_routing_074.py` (1 test): runs the script at 30
decisions, asserts artifact shape, all-positive metrics,
p50 ≤ p99, 8 baseline comparisons present and positive, and
plan-only throughput > serial throughput.

## Evidence
- `pytest tests/test_routing_074.py` → 1 passed.
- `python benchmarks/routing_stress_074.py --decisions 200` →
  artifact as above.
