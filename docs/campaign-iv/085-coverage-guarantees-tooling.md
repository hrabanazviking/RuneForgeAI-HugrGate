# Slice 085 — Coverage guarantees tooling

## What existed
Conformal sets carried a marginal guarantee, but nothing turned a finite
test batch into a checkable claim about achieved coverage.

## What changed
- `hugrgate/calibration/coverage.py` (new):
  - `clopper_pearson(k, n, level)` — exact binomial CI, reusing the
    slice-081 `beta_quantile` (no scipy).
  - `hoeffding_lower_bound` — one-sided distribution-free lower bound.
  - `CoverageCertificate` — n/hits/empirical/interval/`validates(target)`,
    JSON via `as_dict()`.
  - `validate_coverage(sets, labels, target)` — certifies a `PredictionSet`
    batch, recording the `holds` verdict.
  - `required_n(width, level)` — sample-size planning for CP intervals.
- `hugrgate/calibration/__init__.py` — exports `coverage`.

## Statistical validation
2000× Binomial(200, 0.9) simulation: 95% CP intervals contain 0.9 in ≥ 93%
of repetitions (asserted). A cumulative-mass-0.95 set batch (n = 300)
validates against target 0.9 and rejects target 0.999.

## Tests
`tests/test_calib_coverage.py` — 4 tests, all green.
