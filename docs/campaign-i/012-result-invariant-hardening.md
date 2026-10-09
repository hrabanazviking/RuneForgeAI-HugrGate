# Slice 012 — Result invariant hardening

**Date:** 2026-10-09 · **Tests:** `tests/test_result_invariants.py` (13 tests)

## New invariants (`DecisionResult.__post_init__`)

| Invariant | Before |
|---|---|
| `latency_ms >= 0` | unchecked |
| distribution keys are non-empty strings | unchecked |
| `distribution[value] == probability` (±1e-6) for single-value results | unchecked — a result could contradict itself |

The consistency rule is skipped for multilabel results (value is a
label list; each label carries its own mass) and for abstentions
(`value=None`). NaN probabilities/distributions were already rejected
by the chained comparisons; now pinned by tests.

## Interaction found and fixed

Enforcing the rule at construction moved a `SpecError` inside the
ladder's per-rung `try` (`_attempt` catches `Exception` → rung audit →
`Abstention` on exhaustion), breaking the documented "invalid values
climb as `SpecError`" behavior (`test_ladder_rejects_invalid_backend_values`).
Fix: `ladder._attempt` now re-raises `SpecError` instead of auditing it
as a rung error — consistent with `validate_result`, which already
propagates `SpecError` from outside the `try`.

## Verification

13 new tests green; full suite 428 passed; mypy clean.
