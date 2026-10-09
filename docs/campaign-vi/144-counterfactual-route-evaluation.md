# Slice 144 — Counterfactual route evaluation

**Status:** complete. **Tests:** `tests/test_adaptive_counterfactual.py` — 11 tests green.

## What existed before

"What would policy π have earned?" had no answer except serving π.

## What was built

`hugrgate/adaptive/counterfactual.py` — `CounterfactualEvaluator`:

- `estimate(events, target_policy, estimator)`: off-policy value estimation
  from logged `(features, candidates, chosen, propensity, reward)` tuples.
- Three estimators: `"ips"` (unbiased, high-variance), `"snips"`
  (self-normalized; the default), `"dr"` (doubly robust — IPS on the
  residual of a bandit reward model trained on the same log; unbiased if
  *either* propensities or the model are right).
- Only labeled, non-shadow, positive-propensity events participate;
  everything skipped is counted in `PolicyValueEstimate` (n_used,
  n_skipped, effective sample size). No reward imputation — unusable events
  are excluded, not invented.
- Target policies choosing unlogged arms are rejected (`SpecError`).

## Integration

- Telemetry (slice 126), offline learner (slice 131) as the DR reward
  model, bandit (slice 130).

## Verification

- `pytest tests/test_adaptive_counterfactual.py` — 11/11 green: SNIPS/IPS
  recover the true 0.8 policy value on uniform logs, DR recovers 0.3 for the
  bad policy, good-vs-bad policy ordering, a contextual target policy
  evaluated at its true 0.9, rogue-arm rejection, empty-log refusal.
- `mypy hugrgate/adaptive` — clean.
