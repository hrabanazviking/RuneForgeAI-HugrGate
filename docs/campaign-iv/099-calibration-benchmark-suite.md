# Slice 099 — Calibration benchmark suite

## What existed
No head-to-head comparison of the calibration methods; no reproducible
measurement artifact.

## What changed
- `hugrgate/calibration/bench.py` (new): `generate_dataset` (seeded
  overconfident / underconfident / label-noise / well-calibrated sets),
  `run_benchmark(seed, n, ...)` comparing `raw` (explicit identity
  baseline) + platt/isotonic/temperature/beta-binomial/ensemble on
  Brier/log-loss/ECE before → after.
- `benchmarks/build_calibration.py` (new): CLI builder writing the full
  artifact; `benchmarks/calibration_500.json` (24 dataset×calibrator
  cells, n = 2000 each, seed 20261009) regenerated at full rounds after
  the final test run, per the Campaign III tip.
- `hugrgate/calibration/__init__.py` — exports `bench`.

## Statistical validation / baseline comparison
Overconfident set (n = 2000): raw Brier 0.2233 / ECE 0.1153 →
platt 0.2106/0.0429, isotonic 0.2049/0.0000, temperature 0.2087/0.0186,
beta-binomial 0.2097/0.0016, ensemble 0.2073/0.0246. (Isotonic's 0.0000
in-sample ECE is memorization, not magic — the artifact's `metric_note`
says before/after are in-sample.) All numbers measured, none invented.

## Tests
`tests/test_calib_bench.py` — 2 tests at reduced rounds (n = 200, tmp
path), all green; full artifact regenerated afterwards.
