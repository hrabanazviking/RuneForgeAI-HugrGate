# Slice 087 — Risk-coverage curves

## What existed
Slice 086 covered accuracy-based selective curves; the loss-based view
(risk vs. coverage) with an abstention-policy lookup was missing.

## What changed
- `hugrgate/calibration/risk_coverage.py` (new):
  - `risk_coverage_curve(confidences, losses, n_points)` — mean loss over
    the top-confidence fraction at each coverage level; any non-negative
    loss (0/1 error, cost-weighted) works.
  - `aurc` — area under the RC curve (lower better), anchored at coverage 0.
  - `oracle_aurc` — the unbeatable ranking's AURC; `aurc − oracle` is the
    ranking regret (asserted: random confidences have larger regret than
    informative ones).
  - `risk_at_coverage` (interpolated) and `coverage_at_risk` — the
    abstention policy lookup ("largest coverage with risk ≤ target").
- `hugrgate/calibration/__init__.py` — exports `risk_coverage`.

## Statistical validation
Confidence-tracks-correctness data (n = 1000): risk falls as coverage
shrinks; full-coverage risk ≈ 0.3 (the Bayes error); oracle ≤ actual AURC;
a perfect ranking attains the oracle exactly.

## Tests
`tests/test_calib_risk_coverage.py` — 3 tests, all green.
