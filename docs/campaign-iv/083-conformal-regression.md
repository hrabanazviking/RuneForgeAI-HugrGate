# Slice 083 — Conformal regression

## What existed
Conformal machinery covered classification only (slice 082); numeric
predictions had no finite-sample intervals.

## What changed
- `hugrgate/calibration/conformal_regression.py` (new):
  `ConformalRegressor(alpha)` — split-conformal intervals with absolute
  residuals (constant width) or difficulty-normalized residuals (locally
  adaptive widths). `predict_interval(s)` / `predict_intervals`,
  `empirical_coverage`, `mean_width`; weighted mode refuses mismatched
  prediction calls loudly.
- `hugrgate/calibration/__init__.py` — exports `conformal_regression`.

## Statistical validation
Unbiased predictor, Gaussian noise, α = 0.1, n_cal = 1500, n_test = 3000:
empirical coverage ≥ 0.88 (guarantee 0.9, sampling tolerance). Heteroscedastic
variant: coverage holds and hard points get strictly wider intervals than
easy ones. Assumption: exchangeability of calibration and test residuals.

## Tests
`tests/test_calib_conformal_reg.py` — 3 tests, all green.
