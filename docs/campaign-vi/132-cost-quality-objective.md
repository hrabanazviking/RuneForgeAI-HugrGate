# Slice 132 — Cost-quality objective

**Status:** complete. **Tests:** `tests/test_adaptive_cost_quality.py` — 12 tests green.

## What existed before

No objective functions in the repo. Also missing: a shared per-arm estimate
contract for objectives to score.

## What was built

`hugrgate/adaptive/cost_quality.py`:

- `RoutingCandidate`: the Campaign VI shared estimate contract — name,
  quality ∈ [0,1], cost/latency_ms/energy_wh ≥ 0, advisory `privacy_ok`,
  `is_remote`, `data_retained`. Validated at construction.
- `RouteObjective`: ABC — `score(candidate)`, stable `rank`.
- `CostQualityObjective`: `score = w_q·quality − w_c·(cost/cost_scale)`;
  non-negative weights, at least one positive, positive scale — an
  all-zero objective routes at random, which is rejected as a bug.
  `max_affordable_quality_loss` inverts the scalarization so operators can
  read the price of quality directly.

## Integration

- Slices 133–136 implement/consume this interface; errors via `SpecError`.

## Verification

- `pytest tests/test_adaptive_cost_quality.py` — 12/12 green: cheaper wins
  at equal quality, quality can outweigh cost, pure-cost mode, scalarization
  inversion math, tie stability, candidate bound enforcement.
- `mypy hugrgate/adaptive` — clean.
