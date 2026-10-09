# Slice 093 — Calibration ensemble

## What existed
Calibrators were mutually exclusive choices; combining their maps had no
support.

## What changed
- `hugrgate/calibration/ensemble.py` (new): `CalibratorEnsemble`
  (registered as `"ensemble"`, a `Calibrator` subclass) fits member
  calibrators on the same data and averages their maps — mean (default),
  median, or custom weights. Zero-arg construction defaults to
  Platt + isotonic + temperature, so it also slots into slice-092
  auto-selection (verified: it now appears in `DEFAULT_CANDIDATES` and
  ranks competitively). `member_spread(score)` reports member disagreement;
  params round-trip through the registry.
- `hugrgate/calibration/__init__.py` — exports + registers `"ensemble"`;
  `registry.py` gained its metadata entry.

## Statistical validation
Overconfident data (n = 500): ensemble Brier ≤ mean of member Briers
(Jensen bound, asserted) and ≤ the worst member.

## Tests
`tests/test_calib_ensemble.py` — 3 tests, all green.
