# Slice 091 — Calibration registry

## What existed
`CalibratorRegistry`: name → class, nothing else. Choosing a calibrator
required tribal knowledge; deprecation had no representation.

## What changed
- `hugrgate/calibration/registry.py` (new): a metadata catalog layered over
  the untouched legacy registry — `CalibratorSpec` (family, monotonicity,
  both-classes requirement, streaming, deprecation + `replaced_by`),
  `catalog()` / `spec()` / `find()` filters / `describe()` (JSON), and
  `register_spec` for overrides. All seven calibrators carry accurate
  metadata.
- `hugrgate/calibration/__init__.py` — exports `registry`.

## Statistical validation
N/A (metadata infrastructure); verified by inspection that every legacy
registry entry has a spec and that filters return the expected sets.

## Tests
`tests/test_calib_registry.py` — 3 tests, all green.
