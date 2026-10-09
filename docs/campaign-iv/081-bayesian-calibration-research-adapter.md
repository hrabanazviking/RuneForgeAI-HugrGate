# Slice 081 — Bayesian calibration research adapter

## What existed
Point-map calibrators only; no way to see how much data backs a calibrated
probability, and no prior-aware calibration for low-data regimes.

## What changed
- `hugrgate/calibration/bayes.py` (new, labeled RESEARCH ADAPTER):
  - `BetaBinomialCalibrator` (`"beta-binomial"`, a `Calibrator` subclass):
    per-bin Beta(a+pos, b+neg) posterior; `calibrate` returns the posterior
    predictive mean; `credible_interval(score, level)` returns an equal-tailed
    credible interval; params round-trip.
  - Independent `beta_quantile` via bisection on a from-scratch regularized
    incomplete beta (continued fraction, no scipy).
- `hugrgate/calibration/__init__.py` — exports + registers `"beta-binomial"`.

## Statistical validation
- `_betai` / `beta_quantile` checked against known values (I_0.5(2,2) = 0.5;
  median of Beta(2,5) ≈ 0.2644). A sign bug in `log_beta` was caught by
  these checks and fixed before commit.
- On miscalibrated synthetic data (n = 500) ECE improves; empty bins yield
  wide intervals (90% CI width > 0.8 with a uniform prior).
- Assumption: bin-wise exchangeability; the prior dominates in tiny bins —
  this is the point of the adapter (visible uncertainty), not a flaw.

## Tests
`tests/test_calib_bayes.py` — 5 tests, all green.
