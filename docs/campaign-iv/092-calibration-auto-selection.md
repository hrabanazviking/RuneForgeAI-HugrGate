# Slice 092 — Calibration auto-selection

## What existed
Choosing a calibrator was tribal knowledge; the rich catalog (091) had no
consumer.

## What changed
- `hugrgate/calibration/autoselect.py` (new): `auto_select(scores, labels,
  candidates, metric, n_folds, seed)` — seeded K-fold CV over catalog
  candidates (default: platt, isotonic, temperature, beta-binomial),
  ranked by held-out Brier / log-loss / ECE; returns `SelectionResult`
  with the ranking and the winner refit on the full data (JSON summary via
  `as_dict()`). Degenerate folds are skipped, not crashed on.
- `hugrgate/calibration/__init__.py` — exports `autoselect`; **moved the
  seven `CalibratorRegistry.register()` calls above the submodule imports**,
  because `autoselect` reads the registry at import time (this ordering bug
  was caught by the new tests: `DEFAULT_CANDIDATES` came out empty).

## Statistical validation
Overconfident synthetic data (n = 600): the winner's held-out CV Brier is
strictly below the raw-score CV Brier; selection is seed-deterministic.

## Tests
`tests/test_calib_autoselect.py` — 3 tests, all green.
