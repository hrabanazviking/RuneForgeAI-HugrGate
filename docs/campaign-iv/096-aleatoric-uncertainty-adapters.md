# Slice 096 — Aleatoric uncertainty adapters

## What existed
Epistemic adapters (095) covered the reducible half; the irreducible
data-noise half had no estimators.

## What changed
- `hugrgate/calibration/aleatoric.py` (new):
  - `predictive_entropy` — entropy of one predictive distribution.
  - `bernoulli_noise(p)` = p(1−p), the irreducible Bernoulli variance.
  - `label_noise_estimate(scores, labels, n_bins)` — binned E[p(1−p)] noise
    floor from labeled data.
  - `noise_floor_report` — JSON-serializable `AleatoricReport` with per-bin
    detail.
- `hugrgate/calibration/__init__.py` — exports `aleatoric`.

## Statistical validation
Pure noise → ≈ 0.25; perfect separation → ≈ 0; partial signal lands
strictly between (asserted). Entropy checks against ln(2), ln(4).

## Tests
`tests/test_calib_aleatoric.py` — 4 tests, all green.
