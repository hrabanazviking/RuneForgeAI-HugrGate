# Slice 335 — Health dashboard data

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_dashboard.py` (10 tests)

## What existed

`HealthMonitor` scored backends and `MetricRegistry` held counters,
but nothing aggregated them into a single dashboard document.

## What changed

- `hugrgate/observability/dashboard.py`: `HealthDashboard.observe()`
  funnels each decision into the `HealthMonitor` and the registry
  (`hugrgate_decisions_total` by backend/verdict, latency
  histogram); `snapshot(alerts=(), slo_statuses=())` rolls up
  per-backend scores/quarantine/p50/p99/error rates, totals, firing
  alerts, and SLO statuses into one JSON-serializable document with
  `healthy`/`degraded`/`critical` status logic (quarantine or
  critical alert → critical; warning alert or score < 0.5 →
  degraded). Alert/SLO inputs are passed at snapshot time so the
  dashboard never depends on the alert/SLO modules. Abstentions never
  count as backend failures.

## Verification

10 tests (quarantine→critical, alert severities→status, SLO
pass-through, input validation, JSON-serializability); `ruff`/`mypy`
clean.
