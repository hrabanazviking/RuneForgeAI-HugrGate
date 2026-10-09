# Slice 340 — Cost metrics

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_domain_metrics.py`

## What existed

`RouteEvent.cost` existed in the telemetry log, but nothing
aggregated spend live — no totals, no per-backend breakdown, no
charge ledger.

## What changed

- `hugrgate/observability/cost.py`: `CostMetrics` — non-negative
  cost recording by backend/route/currency, filtered totals,
  bounded newest-first charge ledger. One currency label, never FX
  conversion: HugrGate does not invent exchange rates.

## Verification

Covered in `tests/test_observability_domain_metrics.py`
(aggregation, filters, ledger order, negative/NaN rejection);
`ruff`/`mypy` clean.
