# Slice 461 — Calibration selector

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_461_calibration.py` (12 tests)

## What existed

`auto_select` (slice 092) picked the argmin-mean calibrator with two
blind spots: it could never conclude "no calibration beats raw
scores", and it would dethrone an incumbent on a noise-level win.
Per the Anti-Checkbox Rule this slice hardens the existing
capability instead of duplicating it.

## What changed

- `hugrgate/calibration/autoselect.py` (hardened, backward
  compatible — all existing tests pass unchanged):
  - `"none"` pseudo-candidate: the identity calibrator, so selection
    can conclude raw scores are already best;
  - `incumbent` + `min_win`: a challenger replaces the incumbent only
    when its **paired fold-by-fold win** (mean − SE over common fold
    indices, via new `paired_win()`) clears `min_win`; otherwise the
    incumbent is kept ("do no harm");
  - `SelectionResult` gains `incumbent`, `kept_incumbent`,
    `paired_win_vs_incumbent`.
- `hugrgate/autotune/tuners/calibration_select.py`:
  `CalibrationSelectorTuner` — the deployed calibrator is a tunable
  str param; the current value is the incumbent; proposes only on a
  significant win; evidence carries the ranking, the paired win, and
  the statistical assumptions.

## Verification (statistical behavior on controlled data)

On systematically overconfident synthetic scores the selector moves
off `"none"` to a calibrator that lowers **held-out** ECE (train/test
split the tuner never crosses); on calibrated scores it keeps
`"none"` even as incumbent. 12 new tests; `ruff` and `mypy` clean.

Metric/coverage assumptions (in every proposal's evidence):
scores/labels i.i.d. with deployment traffic; the selection metric
matches the operator's calibration goal; the refit-on-full-data
winner is what gets deployed.
