# Slice 135 — Privacy-constrained objective

**Status:** complete. **Tests:** `tests/test_adaptive_privacy_objective.py` — 12 tests green,
including 4 adversarial tests.

## What existed before

`hugrgate/privacy.py` (slice 40) gave an operator-level `PrivacyGuard`, and
`DecisionPolicy` gates remote backends — but the adaptive layer had no
privacy gate of its own, and a learning router could otherwise learn its way
around those guards.

## What was built

`hugrgate/adaptive/privacy_objective.py` — `PrivacyConstrainedObjective`
wraps any `RouteObjective` with a hard admissibility gate:

- Under `privacy_class="strict"`: remote arms inadmissible; data-retaining
  arms inadmissible — mirroring the operator-level `PrivacyGuard`.
- The policy's `backend_allowed` (allowed-list + remote flag) always applies.
- **The advisory `privacy_ok` flag is never trusted**: permission is
  re-derived from `is_remote` / `data_retained` / policy. A compromised or
  buggy estimator cannot smuggle a forbidden arm past by setting a flag.
- Inadmissible arms score `-inf`; `admissible()` exposes the shortlist;
  `require_admissible()` / `best()` raise `BackendUnavailable` (the
  taxonomy's "nothing can serve this") when the gate leaves nothing.

## Integration

- Policy (`DecisionPolicy`), privacy (`PrivacyGuard` semantics mirrored),
  errors (`BackendUnavailable`, `SpecError`).

## Verification

- `pytest tests/test_adaptive_privacy_objective.py` — 12/12 green.
  Adversarial: `privacy_ok=True` on a remote arm is ignored (scores -inf);
  data-retaining local arm blocked under strict; a far-higher-scoring remote
  arm still loses to a weak local arm under the gate; empty admissible set
  fails closed with `BackendUnavailable`.
- `mypy hugrgate/adaptive` — clean.
