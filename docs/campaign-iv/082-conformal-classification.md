# Slice 082 — Conformal classification

## What existed
Calibration mapped scores to probabilities, but there was no finite-sample
coverage machinery: no prediction sets with a guaranteed hit rate.

## What changed
- `hugrgate/calibration/conformal.py` (new): `ConformalClassifier(alpha)`
  implements split (inductive) conformal prediction — nonconformity
  `s = 1 − p̂(y|x)`, threshold = ⌈(n+1)(1−α)⌉/n quantile, set
  `{c : p̂(c|x) ≥ 1 − q̂}`, never empty (argmax fallback). Optional Mondrian
  mode fits one threshold per group for group-conditional coverage.
  `empirical_coverage` / `mean_set_size` / `thresholds` for diagnostics.
- `hugrgate/calibration/__init__.py` — exports `conformal`.

## Statistical validation
Well-specified 4-class data, α = 0.1, calibration n = 1500, test n = 3000:
empirical coverage within [0.88, 1.0] (guarantee ≥ 0.9, tolerance for
sampling noise — asserted ≥ 0.88). Mondrian groups each hold ≈ 0.9 coverage.
Assumption: exchangeability between calibration fold and test data; the
guarantee is marginal over the calibration randomness.

## Tests
`tests/test_calib_conformal.py` — 4 tests, all green.
