# Slice 095 — Epistemic uncertainty adapters

## What existed
Uncertainty decomposition (094) could *measure* epistemic uncertainty, but
nothing *produced* it from live components or acted on it.

## What changed
- `hugrgate/calibration/epistemic.py` (new):
  - `ensemble_epistemic` / `ensemble_epistemic_dicts` — mutual information
    across ensemble members.
  - `distance_epistemic(score, fit_scores)` — OOD proxy: 0 inside the
    fit-score cloud, rising to 1 with normalized distance outside it.
  - `combine_epistemic` — conservative max combination.
  - `review_on_epistemic(result, value, threshold)` — returns
    `(result, EpistemicReport)`; flags the result for human review through
    the existing `hugrgate.abstain.mark_for_review` when triggered
    (a real integration, not a parallel invention — and a docstring bug
    claiming in-place mutation was corrected: the function returns the
    flagged copy).
- `hugrgate/calibration/__init__.py` — exports `epistemic`.

## Statistical validation
Distance adapter: 0 inside [0.2, 0.8] cloud, (0.9−0.8)/0.6 at 0.9,
clipped to 1 far away. Review gate verified against a real
`DecisionResult` (verdict/reviewer metadata, original untouched).

## Tests
`tests/test_calib_epistemic.py` — 4 tests, all green.
