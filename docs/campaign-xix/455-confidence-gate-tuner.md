# Slice 455 — Confidence-gate tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_455_gates.py` (8 tests)

## What existed

The abstention gate ("answer only when confident") was a static
threshold. Nothing learned the coverage/selective-accuracy tradeoff
from data, and nothing gave a statistical guarantee about it.

## What changed

- `hugrgate/autotune/tuners/gates.py`: `ConfidenceGateTuner` learns
  tau from labeled (confidence, correct) pairs:
  - `accuracy_floor` mode: maximize coverage subject to the **Wilson
    lower bound** of selective accuracy >= floor at 1 − alpha;
  - `coverage_target` mode: maximize selective accuracy subject to
    coverage >= target.
  - Seeded stratified 70/30 train/validation split; selection on
    train, **the guarantee is validated on held-out data** the
    selection never saw; ties break toward less abstention.
  - `wilson_lower_bound` (with Acklam's normal quantile for
    non-tabulated alphas); never claims certainty (100/100 → < 1.0).
- Statistical validation on controlled data (per the slice's extra
  criterion): on calibrated synthetic confidences, the tuner opens the
  gate from 0.95 while the held-out Wilson LB stays ≥ 0.8, and the
  guarantee is re-checked on 5000 fresh samples the tuner never saw —
  the lower bound still holds. Metric/coverage assumptions are
  recorded in every proposal's evidence (comparable confidences,
  i.i.d. validation, ground-truth labels).

## Verification

8 new tests (Wilson sanity + textbook value, gate opening with the
guarantee intact, fresh-data guarantee transfer, impossible floor
stays silent, coverage-target mode, spec validation, end-to-end
offline); `ruff` and `mypy` clean.
