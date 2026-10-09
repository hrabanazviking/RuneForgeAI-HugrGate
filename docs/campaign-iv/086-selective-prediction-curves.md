# Slice 086 — Selective prediction curves

## What existed
No abstention/selective-prediction analysis: no way to answer "how accurate
are we on the 50% most confident decisions?"

## What changed
- `hugrgate/calibration/selective.py` (new):
  - `selective_curve(confidences, correct, n_points)` — rows
    `{threshold, coverage, accuracy, n}` from the most confident sliver to
    full coverage.
  - `area_under_selective_curve` — trapezoid area, anchored at coverage 0
    (two real bugs caught by tests during development: the area missed the
    [0, first-grid] sliver, and `coverage_at_accuracy` kept the *last*
    passing row instead of the max — both fixed).
  - `accuracy_at_coverage` (interpolated) and `coverage_at_accuracy`
    (largest coverage holding a target accuracy).
- `hugrgate/calibration/__init__.py` — exports `selective`.

## Statistical validation
Confidence-tracks-correctness data (n = 1000): most-confident sliver more
accurate than full coverage; perfect classifier gives area exactly 1.0 and
coverage 1.0 at accuracy 1.0.

## Tests
`tests/test_calib_selective.py` — 3 tests, all green.
