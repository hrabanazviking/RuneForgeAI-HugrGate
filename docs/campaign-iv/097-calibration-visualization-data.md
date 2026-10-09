# Slice 097 — Calibration visualization data

## What existed
Metrics existed as bare numbers; frontends had no structured payloads for
reliability diagrams, confidence histograms, or per-class breakdowns.

## What changed
- `hugrgate/calibration/viz.py` (new): JSON-serializable payload builders
  with no plotting dependency — `reliability_curve_data` (points + ideal
  diagonal + ECE/MCE), `confidence_histogram`, `per_class_ece_bars`,
  `risk_coverage_points` / `selective_curve_points` (normalized
  pass-throughs of slices 086/087), and `calibration_dashboard` (summary +
  all of the above). Every builder fail-fasts on non-JSON-serializable
  output.
- `hugrgate/calibration/__init__.py` — exports `viz`.

## Statistical validation
Payload values cross-checked against `metrics` (ECE equality asserted);
`json.dumps` round-trip asserted on every payload type.

## Tests
`tests/test_calib_viz.py` — 5 tests, all green.
