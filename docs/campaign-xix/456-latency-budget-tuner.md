# Slice 456 — Latency-budget tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_456_latency.py` (7 tests)

## What existed

Per-stage latency budgets were hand-split with no measurement behind
them; the equal split was the de-facto default and nothing compared
against it.

## What changed

- `hugrgate/autotune/tuners/latency.py`: `LatencyBudgetTuner` splits
  a total millisecond budget across pipeline stages:
  - empirical tail P(X > b) and interpolated quantiles from measured
    samples (stdlib only);
  - seeded p99-proportional allocation, refined by coordinate
    descent on the simplex minimizing joint overflow
    `1 − prod(1 − p_i)`;
  - **explicit baseline**: the equal split measured on the *same*
    samples; both numbers land in the proposal evidence as the
    reproducible measurement artifact (re-derivable by re-running
    with the same seed — no invented numbers);
  - overflow is negated so "higher is better" like every objective.
  - Assumptions recorded: stage independence for the joint estimate,
    i.i.d. samples, millisecond budgets.

## Verification

7 new tests (quantile/tail, tuned beats equal-split on skewed stages
with budgets summing exactly to the total, determinism, silence when
equal split is optimal, spec validation, non-float rejection,
end-to-end offline); `ruff` and `mypy` clean.
