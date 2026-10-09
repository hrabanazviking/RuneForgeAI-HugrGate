# Slice 013 — Policy invariant hardening

**Date:** 2026-10-09 · **Tests:** `tests/test_policy_invariants.py` (9 tests)

## Taxonomy coherence (behavior change)

Policy-domain configuration errors raised bare `ValueError`; they now
raise `PolicyError`, per the slice-007 taxonomy:

- `NumericBand.__post_init__` (lo>hi, min_probability bounds)
- `ThresholdConfig.__post_init__` (+ new: per-option keys and
  ordinal levels must be non-empty strings)
- `ordinal_cumulative_probability` (wrong spec type, unknown level)

Two existing tests in `test_deterministic.py` updated to expect
`PolicyError` (deliberate, documented change).

## Shape validation

`DecisionPolicy.review_band` now validates that the band is a
`(lo, hi)` pair (`PolicyError` on a 3-tuple etc.) instead of failing
with an unpack `ValueError`.

## Pinned invariants

- Gate precedence: `ThresholdConfig.global_minimum` overrides the
  policy floor when set; the policy floor applies otherwise.
- Abstention shape: `value=None`, `accepted=False`, `uncertainty=1.0`,
  uniform distribution over the spec space, `policy_verdict="abstain"`.
- Review preserves value + probability, sets `accepted=False`.
- Numeric band edges are inclusive; first matching band wins.

## Verification

9 new tests green; full suite 438 passed; mypy clean. (One transient
service-timing failure in a full run did not reproduce on rerun —
known flake, unrelated.)
