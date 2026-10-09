# Slice 108 — Blending engine

**Status:** complete · **Commit:** `feat(gjallarbu-108): blending engine`

## Skald (inspect)
Stacking (107) trains a full meta-learner; nothing learned a single
interpretable convex weight vector on holdout data — the lean,
hard-to-overfit sibling.

## Rúnhild (design)
New module `hugrgate/ensemble/blending.py`:
- `project_simplex` (Duchi et al. Euclidean projection) and
  `log_loss` primitives, both unit-tested.
- `Blender(members)` — `fit(votes_per_sample, labels, spec)` learns
  `wᵢ ≥ 0, Σw = 1` minimizing holdout log-loss via projected
  gradient descent (uniform init, fixed iterations, deterministic);
  `blend(votes, spec)` applies the weights; `holdout_log_loss`
  reported for model selection.
- `blending_combine` registered as `"blending"`: fitted blender from
  `ctx.fitted`, else a helpful `BackendError`.

## Eldra (code)
Real optimization math in pure Python; discrete specs only.

## Sólrún (tests)
`tests/test_ensemble_108_blending.py` — 12 tests green. Centerpiece:
on holdout data (good @0.85, mid @0.6, bad confidently-wrong @0.7)
the blender puts >0.9 weight on "good" and reaches holdout log-loss
≈ 0.1625 = −log(0.85), beating uniform averaging (0.539). Also:
simplex-projection unit tests (one hand-computed expectation
corrected after verifying the true Euclidean projection),
log-loss unit, determinism, end-to-end `Ensemble(strategy="blending")`,
fit/combine validation failures, single-member identity,
spec-space mismatch guard.
Ensemble suite: 110 passed; mypy clean.

## Védis (integrate)
- `"blending"` in the registry; `Blender`, `blending_combine`,
  `project_simplex`, `log_loss` exported; inventory doc stays fresh.

## Scribe
Committed `feat(gjallarbu-108): blending engine`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/blending.py`
- `hugrgate/ensemble/api.py`, `hugrgate/ensemble/__init__.py`
- `tests/test_ensemble_108_blending.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py tests/test_ensemble_102_hard_voting.py tests/test_ensemble_103_soft_voting.py tests/test_ensemble_104_weighted_voting.py tests/test_ensemble_105_confidence_voting.py tests/test_ensemble_106_bma.py tests/test_ensemble_107_stacking.py tests/test_ensemble_108_blending.py -q` → 110 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
