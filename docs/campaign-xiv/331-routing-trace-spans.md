# Slice 331 — Routing trace spans

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_spans.py`

## What existed

Routing decisions were logged to the telemetry event log for learning,
but the trace had no routing span — the two stories could diverge.

## What changed

- `hugrgate/observability/spans_routing.py`: `routing_span()` +
  `annotate_routing()` built from the *same*
  `adaptive.telemetry.RouteEvent` the learning dataset uses
  (candidates, chosen arm, propensity, policy version, privacy class,
  shadow flag, latency/cost/energy) — trace and dataset tell the same
  story. Plain mappings with the same keys are accepted so
  non-adaptive routers emit identical spans; inconsistent events
  (empty candidates, chosen-not-in-candidates) raise `TraceError`.

## Verification

Covered in `tests/test_observability_spans.py` (RouteEvent path,
plain-mapping path, inconsistency rejection); `ruff`/`mypy` clean.
