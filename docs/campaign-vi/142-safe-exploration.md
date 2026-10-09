# Slice 142 — Safe exploration

**Status:** complete. **Tests:** `tests/test_adaptive_safe_exploration.py` — 9 tests green.

## What existed before

Slice 141 decided *when* to explore, but nothing constrained *where* —
exploration could have picked a policy-forbidden arm.

## What was built

`hugrgate/adaptive/safe_exploration.py` — `SafeExploration`:

- `eligible(candidates, policy)`: filters `RoutingCandidate`s through
  `DecisionPolicy.backend_allowed` (allowed-list, remote flag), the latency
  budget, the cost budget, and the strict-privacy gate (no remote, no data
  retention) — the advisory `privacy_ok` flag not consulted, same rule as
  slice 135.
- `choose(candidates, policy, exploit_arm, arm_pulls)`: returns the exploit
  arm, or — when the controls warrant — a *different* eligible arm uniformly
  at random. The exploit arm must itself be eligible; an incumbent the policy
  no longer permits is not a safe default.
- Fails closed: no eligible arms → `BackendUnavailable`, never a gamble.
- The safety invariant is structural: no code path in `choose` can return an
  ineligible arm.

## Integration

- Policy (`DecisionPolicy`), slice-141 controls, slice-132 candidates;
  `BackendUnavailable` / `SpecError` per the taxonomy.

## Verification

- `pytest tests/test_adaptive_safe_exploration.py` — 9/9 green: strict
  filters remote, allowed-list/latency/cost filtering, 50 exploration draws
  never leave the eligible set, never re-pulls the exploit arm, exploit path
  returns the incumbent, fails closed on empty eligibility, ineligible
  exploit arm rejected.
- `mypy hugrgate/adaptive` — clean.
