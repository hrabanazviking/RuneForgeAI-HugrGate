# Slice 084 — Prediction sets

## What existed
Slice 082 returned bare `frozenset`s from conformal classification — no
audit metadata, no alternative construction strategies, no set-level
metrics.

## What changed
- `hugrgate/calibration/sets.py` (new):
  - `PredictionSet` — frozen dataclass: labels, method, params, provenance;
    `covers()`, `size`, `as_dict()`; never empty by construction.
  - Strategies: `threshold_set`, `topk_set`, `cumulative_set`
    (smallest top-label set reaching a probability mass), `from_conformal`
    (wraps a fitted `ConformalClassifier`).
  - `set_metrics` — coverage, mean/median/max size, singleton rate.
  - `size_stratified_coverage` — coverage per set size; diagnoses
    overconfidence when singletons cover worse than large sets.
- `hugrgate/calibration/__init__.py` — exports `sets`.

## Statistical validation
Well-specified 4-class data, cumulative-mass 0.9 sets (n = 800): coverage in
[0.85, 1.0]; size-stratified coverage flat within 0.15 across sizes with
n ≥ 30 (asserted).

## Tests
`tests/test_calib_sets.py` — 4 tests, all green.
