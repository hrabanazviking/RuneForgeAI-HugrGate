# Slice 494 — Calibration truth audit

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_494_calibration_audit.py` (6 tests)

## What it does

The ECE metric (`hugrgate/calibration/metrics.py`) is audited
against synthetic data with *known* true probabilities, in
`hugrgate/gauntlet/calibration_audit.py`:

- `synthetic_bernoulli(n, seed)` draws `p ~ U(0,1)`, `y ~ Bern(p)`
  with a seeded RNG (bit-identical reruns);
- the perfect forecaster (reports true p) must score ECE within
  statistical noise;
- the overconfidence map `q = clip(0.5 + s·(p − 0.5))` must score
  clearly above zero;
- ECE must grow monotonically with severity `s`.

## Measured audit (n=20000, 15 bins, seed=494)

| forecaster | ECE |
|---|---|
| perfect (true p) | 0.0092 |
| overconfidence s=1.0 | 0.0092 |
| overconfidence s=1.25 | 0.0515 |
| overconfidence s=1.5 | 0.0826 |

tolerance (perfect): < 0.03 · minimum (miscalibrated): > 0.04 ·
monotone in severity: True

**Verdict: PASS** — the metric agrees with ground truth: it
scores truth near zero, detects injected miscalibration, and is
sensitive to its severity.

## Verification

6 tests green; `ruff`/`mypy` clean.
