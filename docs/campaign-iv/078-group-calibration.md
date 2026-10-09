# Slice 078 — Group calibration

## What existed
Only global (whole-dataset) calibration: opposite per-group biases could
cancel out and look fine on average while each group stayed miscalibrated.

## What changed
- `hugrgate/calibration/group.py` (new): `GroupCalibrator(factory)` fits one
  calibrator per group value plus a global fallback for unseen groups.
  Groups too small (< `min_group_samples`) or single-class share the global
  map instead of fitting a degenerate one. Reports per-group Brier/ECE and
  `disparity()` = max − min per-group ECE (the calibration fairness gap);
  `get_params()` is JSON-serializable.
- `hugrgate/calibration/__init__.py` — exports `group`.

## Statistical validation
Controlled two-group data (A overconfident k=2, B underconfident k=0.5,
n = 500): per-group Platt fits close the ECE gap versus a single global
Platt fit (`group_gap < glob_gap` asserted in the test).

## Tests
`tests/test_calib_group.py` — 4 tests, all green.
