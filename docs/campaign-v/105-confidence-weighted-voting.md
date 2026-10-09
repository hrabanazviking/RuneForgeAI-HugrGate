# Slice 105 — Confidence-weighted voting

**Status:** complete · **Commit:** `feat(gjallarbu-105): confidence-weighted voting`

## Skald (inspect)
Weighted voting (104) uses fixed, operator-assigned weights. Nothing
yet let a member's *own reported confidence* modulate its influence —
the standard remedy when some members are calibrated and others are
chronically unsure.

## Rúnhild (design)
`confidence_weighted_voting` in `hugrgate/ensemble/voting.py`,
registered as strategy `"confidence"`:
- Effective weight `eᵢ = base_weightᵢ × pᵢ` (base = normalized
  assigned weight, `pᵢ` = the member's self-reported probability for
  its voted value); winner = argmax of `Σ eᵢ·[valueᵢ == v]`;
  probability = confidence-weighted share; uncertainty = `1 - share`.
- `BackendError` on no countable ballots / non-positive total
  confidence; discrete specs only; deterministic ties.
- Metadata: `confidence_scores` per value, `effective_weights` per
  member.

## Eldra (code)
Real combiner; the rank-calibration assumption is documented on the
function (an overconfident member is amplified — operator beware).

## Sólrún (tests)
`tests/test_ensemble_105_confidence_voting.py` — 9 tests green,
including the statistical validation:
- **Controlled-data validation** (`test_confident_minority_overrules_unsure_majority`):
  truth "beta"; 3 members vote "alpha" (wrong) at 0.55 confidence, 2
  vote "beta" (right) at 0.95. Hard voting elects the wrong majority
  (3-2); confidence weighting elects "beta" with exact share math
  (1.90/3.55). Validates the strategy's *purpose*, not just its math.
- Exact score math, base-weights-multiply-confidence, equal
  confidence reproduces hard voting, zero-confidence member
  contributes nothing, all-zero confidence / no ballots / numeric
  spec → `BackendError`, binary spec end-to-end.
- Ensemble suite: 67 passed; mypy clean.

**Metric/coverage assumptions (reported per the slice's extra
criterion):** the validation assumes member probabilities are
*rank-calibrated* (higher self-reported confidence → more likely
correct); it uses synthetic scripted members with exact controlled
confidences, not empirical calibration curves. Coverage: binary and
3-option categorical specs, 2–5 members. A flip of an n-vs-m
majority needs Σ(confident correct) > Σ(unsure wrong); on binary
specs a lone confident member can never outscore two unsure ones
(2×0.51 > 1.0), which the tests pin implicitly.

## Védis (integrate)
- Strategy registry gains `"confidence"`; exported from
  `hugrgate.ensemble`; inventory doc stays fresh.

## Scribe
Committed `feat(gjallarbu-105): confidence-weighted voting`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/voting.py` (`confidence_weighted_voting`)
- `hugrgate/ensemble/api.py`, `hugrgate/ensemble/__init__.py`
- `tests/test_ensemble_105_confidence_voting.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py tests/test_ensemble_102_hard_voting.py tests/test_ensemble_103_soft_voting.py tests/test_ensemble_104_weighted_voting.py tests/test_ensemble_105_confidence_voting.py -q` → 67 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
