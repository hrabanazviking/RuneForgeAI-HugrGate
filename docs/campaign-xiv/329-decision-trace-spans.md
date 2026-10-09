# Slice 329 — Decision trace spans

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_spans.py`

## What existed

Decisions produced results and provenance records, but nothing
rendered a decision *as a span* with its spec, policy, and verdict.

## What changed

- `hugrgate/observability/spans_decision.py`:
  - `decision_span()` context manager + `annotate_decision()` over
    `DecisionSpec` / `DecisionResult` / `DecisionPolicy`.
  - Verdict vocabulary (`accept`/`review`/`abstain`) recorded both as
    attribute and as span event for viewer filtering.
  - Probabilities recorded as 0.1-wide *bands*, never exact values;
    `result.value` and the full distribution are excluded **by
    construction** — payload never enters observability.

## Verification

Covered in `tests/test_observability_spans.py` (nesting, abstention
path with reason event, payload exclusion); `ruff`/`mypy` clean.
