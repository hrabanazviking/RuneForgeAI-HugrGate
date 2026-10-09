# Slice 459 — Backend-order tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_459_backends.py` (8 tests)

## What existed

The backend fallthrough order was configuration folklore. Nothing
computed the expected-cost-optimal order from measured success rates
and per-call costs.

## What changed

- `hugrgate/autotune/tuners/backends.py`: `BackendOrderTuner`
  computes the optimal fallthrough order — sorting by
  **cost-per-success ascending** (proved optimal by the pairwise
  interchange argument, documented in the module) — from measured
  (success_rate, cost) stats, and proposes rank assignments for one
  int param per backend (`{rank_prefix}.{name}`):
  - `expected_chain_cost(order, stats)` for the fallthrough
    expectation;
  - deterministic tie-break by name; negated cost as the
    higher-is-better score;
  - evidence carries per-backend ratios, baseline vs tuned order and
    cost, and the optimality argument.

## Verification

8 new tests (chain-cost math, cheapest-first shown suboptimal,
**optimality vs brute-force permutation search on 30 randomized
4-backend instances**, silence at optimum, tie-break determinism,
spec validation, missing-param surfacing, end-to-end offline);
`ruff` and `mypy` clean.
