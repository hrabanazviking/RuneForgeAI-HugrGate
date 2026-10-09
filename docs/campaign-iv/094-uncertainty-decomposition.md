# Slice 094 — Uncertainty decomposition

## What existed
Uncertainty was a single number (`1 − probability`); no split between
irreducible data noise and reducible model disagreement.

## What changed
- `hugrgate/calibration/decomposition.py` (new):
  - `decompose(predictions)` — members × classes matrix →
    `UncertaintyBreakdown(total, aleatoric, epistemic)`: total =
    entropy of the mean distribution, aleatoric = mean member entropy,
    epistemic = mutual information (their difference). Validates rows sum
    to 1, finiteness, non-negativity.
  - `decompose_dicts` — dict-distribution variant (missing keys → 0).
- `hugrgate/calibration/__init__.py` — exports `decomposition`.

## Statistical validation
Identical members → epistemic ≈ 0; confidently-disagreeing members →
epistemic > aleatoric; uniform members → total = ln(3), epistemic = 0;
`total == aleatoric + epistemic` throughout (asserted).

## Tests
`tests/test_calib_decomposition.py` — 4 tests, all green.
