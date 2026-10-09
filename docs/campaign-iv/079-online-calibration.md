# Slice 079 — Online calibration

## What existed
Batch-only calibrators: the fit set was frozen in time, so a drifting
score→outcome relationship silently invalidated the map.

## What changed
- `hugrgate/calibration/online.py` (new): `OnlineCalibrator` (a `Calibrator`
  subclass, registered as `"online"`) keeps per-bin decayed
  (positives, total) counts; `partial_fit` incorporates a batch and forgets
  old ones via exponential `decay`; calibrated values are Laplace-smoothed
  bin rates passed through a weighted PAV so the map stays monotone.
  `fit` = reset + one `partial_fit`; `bin_stats()` / `effective_samples()`
  expose the live state; params round-trip.
- `hugrgate/calibration/__init__.py` — exports + registers `"online"`.

## Statistical validation
Two-phase drift (overconfident k=2 → underconfident k=0.5, n = 600 each):
after 6 decayed (0.9) updates on phase 2, the online map's ECE on phase-2
data is strictly below a frozen phase-1 map's ECE (asserted). Monotonicity
and [0,1] bounds checked on a 51-point grid.

## Tests
`tests/test_calib_online.py` — 4 tests, all green.
