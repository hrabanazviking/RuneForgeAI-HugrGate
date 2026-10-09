# Slice 344 — SLO definitions

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_alerts_slo.py`

## What existed

No SLO concept: targets like "99.9% availability" lived in prose,
not in validated, serializable objects anything could evaluate.

## What changed

- `hugrgate/observability/slo.py`: immutable `SLODefinition`
  (name, target in (0,1], positive `window_s`, kind in
  `availability`/`latency`/`abstention_rate`/`custom`; the latency
  kind requires `params["latency_budget_ms"]`); `error_budget`
  property; `to_dict()`/`from_dict()` round-trip with `SLOError` on
  malformed input. Bad definitions raise at construction — an SLO
  that cannot be stated precisely cannot be evaluated honestly.

## Verification

Covered in `tests/test_observability_alerts_slo.py` (validation of
every field, serialization round-trip); `ruff`/`mypy` clean.
