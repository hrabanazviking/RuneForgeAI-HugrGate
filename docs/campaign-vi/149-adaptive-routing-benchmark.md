# Slice 149 — Adaptive routing benchmark

**Status:** complete. **Tests:** `tests/test_adaptive_benchmark.py` — 11 tests green.
**Artifact:** `docs/campaign-vi/artifacts/adaptive-routing-benchmark.json`
(regenerated at full rounds after the final test run, per the worker tip;
tests use reduced rounds for speed).

## What existed before

`hugrgate/bench.py` (slice 45) benchmarks *backends* on datasets. Nothing
benchmarked *routing policies* against each other.

## What was built

`hugrgate/adaptive/benchmark.py` — `AdaptiveRoutingBenchmark`:

- Replays a deterministic scenario `(rng, round_idx) -> (features, rewards)`
  for N rounds; compares `uniform`, `round_robin`, `static_first` baselines
  against the `adaptive` LinUCB policy (slice 130) learning online.
- `default_scenario`: context-dependent rewards (arm_a wins iff x0 > 0.5,
  arm_b the mirror, arm_c a constant 0.55) with σ=0.05 clipped Gaussian
  noise — a learning policy can genuinely beat static ones here.
- `BenchmarkArtifact`: every number computed — per-policy mean/total reward,
  per-arm pull counts, winner as argmax (ties by name), config; `save`/`load`
  JSON round-trip; `summary()` for humans.

## Measured results (2000 rounds, seed 7 — from the checked-in artifact)

| policy      | mean_reward | total_reward |
|-------------|-------------|--------------|
| uniform     | 0.5840      | 1168.1       |
| round_robin | 0.5764      | 1152.8       |
| static_first| 0.5991      | 1198.2       |
| **adaptive**| **0.8820**  | **1764.0**   |

Winner: **adaptive**. The baselines land where theory says they should
(uniform ≈ 0.583 on this scenario); the LinUCB policy approaches the 0.9
optimum. No numbers invented — all read from the artifact.

## Integration

- Exercises the slice-130 bandit end-to-end; `SpecError` on bad config,
  empty arms, scenario/arm mismatch.

## Verification

- `pytest tests/test_adaptive_benchmark.py` — 11/11 green: artifact
  completeness, adaptive beats uniform *and* static_first at 400 rounds,
  seed determinism (wall-clock excluded by design), scenario shape,
  save/load round-trip, custom scenarios, failure cases.
- `mypy hugrgate/adaptive` — clean.
