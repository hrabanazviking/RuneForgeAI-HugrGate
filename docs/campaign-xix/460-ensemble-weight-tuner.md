# Slice 460 — Ensemble-weight tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_460_weights.py` (7 tests)

## What existed

`Blender` learned weights online with a fixed learning rate; other
ensemble weights were hand-set. Nothing computed batch-optimal
weights from labeled data.

## What changed

- `hugrgate/autotune/tuners/weights.py`: `EnsembleWeightTuner`
  maximizes mean log-likelihood of the simplex-weighted blend via
  **projected gradient ascent with backtracking line search**,
  reusing `hugrgate.ensemble.blending.project_simplex` (no
  duplication) with the exact gradient
  `dL/dw_m = mean_n p[n][m][y_n] / blend[n][y_n]`:
  - one float param per member (`{weight_prefix}.{member}`);
  - baseline = current store weights normalized to the simplex;
  - proposal requires beating the baseline by `min_delta`;
  - evidence carries both weight vectors, both log-likelihoods, and
    the iteration count.

## Verification

7 new tests (log-likelihood math, weight concentration on the best
member with simplex validity, meaningful win over uniform,
determinism, silence at optimum, spec validation, end-to-end
offline); `ruff` and `mypy` clean.
