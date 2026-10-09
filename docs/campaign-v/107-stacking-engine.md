# Slice 107 — Stacking engine

**Status:** complete · **Commit:** `feat(gjallarbu-107): stacking engine`

## Skald (inspect)
No meta-learner existed: every strategy used fixed or self-reported
weights. Nothing could *learn* from labeled member predictions that
one member is sharp and another confidently wrong.

## Rúnhild (design)
New module `hugrgate/ensemble/stacking.py`:
- `SoftmaxRegression` — multinomial logistic regression in pure
  Python (zero-init batch gradient descent, fixed iterations, L2 on
  weights, bias unregularized): fully deterministic, no scikit-learn
  dependency, so the ensemble package keeps its stdlib-only
  footprint.
- `StackingEngine(members)` — owns the feature layout (each member's
  completed distribution over the spec space, concatenated; silent
  members contribute zeros), `fit(votes_per_sample, labels, spec)`,
  `predict_proba(votes, spec)`. Rejects label/space mismatches and
  unfitted use loudly.
- `stacking_combine` registered as `"stacking"`: needs a fitted
  engine in `ctx.fitted` (via `Ensemble.attach`); meta-distribution
  → argmax winner; uncertainty = normalized entropy.

## Eldra (code)
Real GD math, no stubs. Discrete specs only.

## Sólrún (tests)
`tests/test_ensemble_107_stacking.py` — 12 tests green. Centerpiece:
on controlled data (sharp always right @0.9, dull always *confidently
wrong* @0.9) the meta-learner outputs P(truth) ≈ 0.97 — it learned to
distrust the confident liar, which no fixed-weight vote can do. Also:
fit determinism (identical weights across runs), toy-problem
convergence, end-to-end `Ensemble(strategy="stacking")`,
fit/combine/predict validation failures, spec-space mismatch guard.
Ensemble suite: 98 passed; mypy clean.

## Védis (integrate)
- `"stacking"` in the registry; `SoftmaxRegression`,
  `StackingEngine`, `stacking_combine` exported from
  `hugrgate.ensemble`; inventory doc stays fresh.

## Scribe
Committed `feat(gjallarbu-107): stacking engine`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/stacking.py`
- `hugrgate/ensemble/api.py`, `hugrgate/ensemble/__init__.py`
- `tests/test_ensemble_107_stacking.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py tests/test_ensemble_102_hard_voting.py tests/test_ensemble_103_soft_voting.py tests/test_ensemble_104_weighted_voting.py tests/test_ensemble_105_confidence_voting.py tests/test_ensemble_106_bma.py tests/test_ensemble_107_stacking.py -q` → 98 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
