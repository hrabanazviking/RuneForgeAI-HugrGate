# Slice 077 — Per-class calibration

## What existed
`CalibratedBackend` applied one-vs-rest calibrators at serving time, but the
*fitting* side was hand-rolled by callers: no per-class diagnostics, and a
class absent from the calibration set had no defined behavior.

## What changed
- `hugrgate/calibration/perclass.py` (new):
  - `PerClassCalibrator(factory)` — fits one binary calibrator per class
    from multiclass probability dicts; records per-class
    Brier/ECE before/after; unseen classes get a constant-prior fallback
    (`_ConstantCalibrator`, registered as `"constant-prior"`) instead of
    crashing; `calibrate_dist` renormalizes; params round-trip through
    `to_profile_params` / `from_profile_params` with a `"__fallback__"` flag.
  - `build_profile(...)` — builds a `CalibrationProfile` with per-class
    metric keys (`brier_after[a]`, …).
- `hugrgate/calibration/profiles.py` — `CalibrationProfile.build_calibrators`
  now honors the `"__fallback__"` flag (backward compatible: old profiles
  without the flag behave exactly as before).
- `hugrgate/calibration/__init__.py` — exports `perclass`; registers
  `"constant-prior"`.

## Statistical validation
3-class synthetic data (n = 600, per-class overconfidence): every class
shows Brier_after ≤ Brier_before; calibrated distributions renormalize to 1.

## Tests
`tests/test_calib_perclass.py` — 5 tests, all green.
