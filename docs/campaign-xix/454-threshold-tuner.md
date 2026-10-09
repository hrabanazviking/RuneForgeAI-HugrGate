# Slice 454 — Threshold tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_454_thresholds.py` (11 tests)

## What existed

Decision thresholds (`minimum_probability`, per-option gates) were
hand-set constants with no mechanism to learn them from data. The
`tuners/` subpackage did not exist.

## What changed

- `hugrgate/autotune/tuners/_base.py`: shared tuner machinery —
  `BaseTuner` (seeded RNG, `_propose` with the `min_delta`
  significance gate), `seeded_rng`, `linspace`, stratified
  `kfold_indices`.
- `hugrgate/autotune/tuners/thresholds.py`: `ThresholdTuner` sweeps a
  float threshold over a grid with stratified k-fold CV on labeled
  score data. Metrics: f1, f_beta, accuracy, precision, recall,
  youden. Hardening beyond the naive version:
  - the baseline goes through the *same* k-fold protocol as the
    candidates (apples-to-apples);
  - selection uses the one-SE rule (mean − SE);
  - a **paired fold-by-fold significance gate** requires
    mean(d) − SE(d) ≥ min_delta where d is the per-fold win over the
    baseline — this discounts the selection bias of picking the best
    of 41 thresholds. Verified: on pure-noise data the tuner stays
    silent.

## Verification

11 new tests (metric variants, separating-threshold discovery,
silence at optimum, silence on noise, non-float rejection, dataset
validation, stratification, end-to-end through the controller);
`ruff` and `mypy` clean.
