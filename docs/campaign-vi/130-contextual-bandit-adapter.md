# Slice 130 — Contextual bandit adapter

**Status:** complete. **Tests:** `tests/test_adaptive_bandit.py` — 18 tests green.

## What existed before

No learning component anywhere in the repo. Routing (Campaign III, separate
branch) plans; nothing adapted from experience.

## What was built

`hugrgate/adaptive/bandit.py` — `ContextualBanditAdapter`, a LinUCB
contextual bandit over named backend arms:

- One ridge-regression model per arm; `select` picks max
  `θ·x + α·√(xᵀA⁻¹x)`, ties broken by arm name — fully deterministic.
- **Pure standard library**: Gaussian elimination with partial pivoting for
  the small linear solves (feature dims are tens), keeping the adaptive
  package importable on the base install per the repo's stdlib-only
  contract. Singular systems raise `BackendError`, never return garbage.
- `update(arm, features, reward, weight)` folds weighted observations in
  (the IPS hook slice 131 uses).
- `seed_prior(arm, mean, strength)` for cold-start seeding (slice 140).
- `to_dict`/`from_dict` round-trip full learned state (`adaptive-bandit/v1`)
  for versioning/rollback (slices 145–146).

## Integration

- Consumes slice-129 features; validated with `SpecError` (missing columns,
  non-finite values, bad hyper-parameters); numerical failures surface as
  `BackendError` per the error taxonomy.

## Verification

- `pytest tests/test_adaptive_bandit.py` — 18/18 green: learns a contextual
  preference (arm_good iff x0=1), UCB explores untried arms, priors bias
  cold start, serialization preserves behavior, solver correctness,
  singular-matrix and bad-input rejection.
- `mypy hugrgate/adaptive` — clean.
