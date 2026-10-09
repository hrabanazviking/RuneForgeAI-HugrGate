# Slice 089 — Calibration under imbalance

## What existed
Calibrators fit on whatever data they were given; imbalance was invisible —
minority-class miscalibration hid behind majority-dominated averages, and
prior transport had no tooling.

## What changed
- `hugrgate/calibration/imbalance.py` (new):
  - `rebalance(scores, labels, target_rate, seed)` — seeded resampling to a
    target positive rate (deterministic for a given seed).
  - `saerens_prior_correction(p_cal, fit_prior, deploy_prior)` — transports
    calibrated probabilities to the deployment prior; identity when priors
    match; monotone and bounded.
  - `fit_balanced(factory, ...)` — rebalance + fit, returning the calibrator
    and a JSON-serializable `ImbalanceReport`.
  - `stratified_metrics` — Brier/ECE on positive/negative strata separately
    (note: within-stratum ECE mixes sharpness — use it comparatively).
- `hugrgate/calibration/__init__.py` — exports `imbalance`.

## Statistical validation
Train prior 10% → deploy prior 40% (n = 3000/2000, overconfident scores):
Platt fit on 50%-rebalanced data + Saerens correction to 40% achieves
strictly lower deployment Brier than the uncorrected map (asserted).

## Tests
`tests/test_calib_imbalance.py` — 4 tests, all green.
