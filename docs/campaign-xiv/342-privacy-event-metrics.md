# Slice 342 — Privacy-event metrics

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_domain_metrics.py`

## What existed

Privacy enforcement blocked things but counted nothing — no
visibility into violation rates, denied flows, or redactions.

## What changed

- `hugrgate/observability/privacy_metrics.py`:
  `PrivacyEventMetrics` — violations by taxonomy code and privacy
  class, denied data flows, redactions. Labels are metadata-only by
  construction: a fixed allowlist of label names, a payload-key
  denylist, and a 256-char value cap. The violating payload is never
  an argument — callers pass the already-raised exception.
- **Adversarial tests:** attempts to smuggle payload through label
  names (`value`, `state`), oversized values, or non-string values
  are rejected, not recorded; the allowlist provably contains no
  payload key.

## Verification

Covered in `tests/test_observability_domain_metrics.py` including
the adversarial suite; `ruff`/`mypy` clean.
