# Slice 338 — Abstention metrics

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_domain_metrics.py`

## What existed

Abstentions were results with `accepted=False`; nothing counted
*why* the gate refused, and abstentions risked being lumped in with
backend failures in ad-hoc monitoring.

## What changed

- `hugrgate/observability/abstention.py`: `AbstentionMetrics` —
  counters by machine-readable `abstain_reason` and backend, review
  counts by backend, bounded sliding-window abstention rate;
  `record()` returns the recorded class
  (`abstain`/`review`/`accept`). Abstentions are structurally
  separate from backend failures.

## Verification

Covered in `tests/test_observability_domain_metrics.py` (reason
breakdown, windowed rates, bounded window); `ruff`/`mypy` clean.
