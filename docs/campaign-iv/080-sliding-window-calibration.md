# Slice 080 — Sliding-window calibration

## What existed
Slice 079's `OnlineCalibrator` tracks drift with an approximate binned map;
there was no way to keep the full fidelity of a batch calibrator
(Platt/isotonic/temperature) on recent data.

## What changed
- `hugrgate/calibration/window.py` (new): `SlidingWindowCalibrator(factory,
  window_size, refit_every, min_samples)` keeps the last `window_size`
  (score, label) pairs in a deque and refits the inner calibrator on that
  window (at most one refit per `partial_fit` call; refits are skipped for
  degenerate windows and the previous map is kept). `fit` resets and
  requires a usable window. Params (including the window) round-trip via
  `from_params`, resolving the inner factory through the registry.
- `hugrgate/calibration/__init__.py` — exports + registers
  `"sliding-window"`.

## Statistical validation
Phase drift k=2 → k=0.5 (n = 300 each, window 300): after the window slides
fully onto phase 2, ECE on phase-2 data is strictly below a frozen phase-1
Platt map (asserted).

## Tests
`tests/test_calib_window.py` — 3 tests, all green.
