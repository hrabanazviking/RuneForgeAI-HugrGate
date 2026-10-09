# Slice 104 — Weighted voting

**Status:** complete · **Commit:** `feat(gjallarbu-104): weighted voting`

## Skald (inspect)
The weight plumbing (normalized maps, missing → 0, eager validation)
existed after slices 101/103, but no ballot-counting strategy used
it: hard voting deliberately ignores weights, soft voting averages
distributions. There was no "trusted members count more" majority
vote.

## Rúnhild (design)
`weighted_voting` in `hugrgate/ensemble/voting.py`, registered as
strategy `"weighted"`:
- `score(v) = Σᵢ wᵢ·[valueᵢ == v]`; winner = argmax of weighted
  scores; probability = weighted share `score(winner)/Σw`;
  distribution over the full spec space; uncertainty = `1 - share`.
- Deterministic ties via the shared `break_tie` (score → earliest
  ballot → lexicographic).
- `BackendError` on no countable ballots or non-positive total
  weight; discrete specs only.
- Metadata carries `weighted_tally` (in normalized-weight units).

## Eldra (code)
Real combiner reusing `_ballots`, `break_tie`, `finalize_result` —
no new machinery, no stubs.

## Sólrún (tests)
`tests/test_ensemble_104_weighted_voting.py` — 9 tests green:
success (weighted scores elect the minority-ballot winner with exact
share math, equal weights reproduce hard voting, deterministic
weighted tie-break, unnamed member gets 0 weight),
failure (no ballots, zero total weight, numeric spec),
boundary (single member full share, fractional weights).
Ensemble suite: 58 passed; mypy clean.

## Védis (integrate)
- Strategy registry gains `"weighted"`; `weighted_voting` exported
  from `hugrgate.ensemble`.
- API inventory doc regenerated at the end of the campaign picks up
  the new public name (verified fresh after this slice via the
  generator; test green).

## Scribe
Committed `feat(gjallarbu-104): weighted voting`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/voting.py` (`weighted_voting`)
- `hugrgate/ensemble/api.py`, `hugrgate/ensemble/__init__.py`
  (registration + export)
- `tests/test_ensemble_104_weighted_voting.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_10{1,2,3,4}_*.py -q` → 58 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
