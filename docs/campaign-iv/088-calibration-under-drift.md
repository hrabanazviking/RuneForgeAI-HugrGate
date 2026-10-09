# Slice 088 — Calibration under drift

## What existed
Adaptive calibrators (slices 079–080) could track drift, but nothing
*detected* it: no monitoring, no recalibration trigger.

## What changed
- `hugrgate/calibration/drift.py` (new):
  - `CalibrationDriftMonitor` — EWMA control chart over batch Brier **and**
    ECE of calibrated outputs; baseline from the first `baseline_batches`;
    alarm when either EWMA crosses `mean + k·std` (with a `min_std` floor
    against hair-trigger baselines); `recommend()` → `"recalibrate"`/`"keep"`;
    `reset_alarm()` re-arms after recalibration; `report().as_dict()` is
    JSON-serializable.
- `hugrgate/calibration/__init__.py` — exports `drift`.

## Statistical validation
Phase-1 Platt map watched on phase-1 batches (n = 500 × 12): no alarm.
Prior shift (−1.5) on the data-generating process: alarm fires within 6
batches; refitting Platt on the new regime + `reset_alarm()` returns the
monitor to quiet. Key finding during development: raw-score Brier barely
moves under score→outcome drift (0.22 → 0.22), so the monitor watches
*calibrated* outputs, where the same drift shows 0.21 → 0.24 Brier and
0.04 → 0.31 ECE.

## Tests
`tests/test_calib_drift.py` — 4 tests, all green.
