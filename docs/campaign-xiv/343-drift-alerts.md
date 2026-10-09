# Slice 343 — Drift alerts

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_alerts_slo.py` (16 tests)

## What existed

Drift *detection* existed (`hugrgate/drift.py` PSI monitors,
`adaptive/drift_detect.py`) but had no alerting layer: no severity
mapping, no dedup, no cooldown — a drifting detector would spam.

## What changed

- `hugrgate/observability/alerts.py`:
  - `alert_for_drift_report()` — maps detector verdicts to alerts
    (`watch`→warning, `action`→critical, `none`→no alert); unknown
    severities raise `AlertError`.
  - `Alert` — validated value object (name, severity, dedup key,
    message, details); JSON-serializable.
  - `AlertRule` + `AlertManager` — rule evaluation with dedup keys
    and cooldowns: re-fires inside cooldown are *suppressed and
    counted*, never re-emitted. Broken rule conditions abort loudly
    instead of silently passing. `fire()` primitive for pre-built
    alerts (used by `evaluate_drift()`).

## Verification

16 tests (severity mapping, cooldown dedup + suppression counts,
broken-rule abort, end-to-end drift evaluation); `ruff`/`mypy` clean.
