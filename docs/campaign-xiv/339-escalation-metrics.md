# Slice 339 — Escalation metrics

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_domain_metrics.py`

## What existed

`Supervisor` (slice 295) restarted dead workers and called an
`on_escalation` callback, but restarts and escalations were invisible
to metrics — a flapping worker left no countable trace.

## What changed

- `hugrgate/observability/escalation.py`: `EscalationMetrics` —
  restart counters by worker, escalation counters by worker+reason,
  bounded newest-first escalation history; `as_callback()` plugs
  directly into `Supervisor(on_escalation=...)`.

## Verification

Covered in `tests/test_observability_domain_metrics.py` (callback
wiring through a real `Supervisor`, restart counting, history
bounds/order); `ruff`/`mypy` clean.
