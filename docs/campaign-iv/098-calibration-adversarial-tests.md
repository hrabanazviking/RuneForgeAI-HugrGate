# Slice 098 — Calibration adversarial tests

## What existed
Calibration was evaluated on the distribution it was fit on — the kindest
possible test. No stress/robustness harness existed.

## What changed
- `hugrgate/calibration/adversarial.py` (new):
  - Attacks: `overconfidence_attack`, `underconfidence_attack`,
    `label_flip_attack` (seeded), `bias_shift_attack` — all bounded,
    validated, deterministic given seeds.
  - `stress_test(factory, scores, labels, attacks)` — fits on clean data,
    reports per-attack Brier/ECE degradation in a JSON-serializable
    `StressReport` with `worst_ece_degradation()`.
- `hugrgate/calibration/__init__.py` — exports `adversarial`.

## Statistical validation
Platt on overconfident data (n = 600): all five default attacks degrade
Brier; worst ECE degradation > 0.01. Notable finding: the overconfidence
attack *reduced* ECE by 0.009 while increasing Brier — ECE is binned and
not a proper scoring rule, so it can wiggle under attack; Brier is the
primary stress signal and the tests assert on it.

## Tests
`tests/test_calib_adversarial.py` — 3 tests, all green.
