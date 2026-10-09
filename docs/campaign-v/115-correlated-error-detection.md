# Slice 115 — Correlated-error detection

**Status:** complete · **Commit:** `feat(gjallarbu-115): correlated-error detection`

## Skald (inspect)
Slice 110 provided Q-statistics but nothing rendered a *verdict*:
members that err together look like independent votes while failing
as one — the most dangerous ensemble failure mode.

## Rúnhild (design)
New module `hugrgate/ensemble/correlation.py`:
- `detect_correlated_errors(correct, threshold=0.7)` — correctness
  history per member (aligned) → flags every pair with Q ≥ threshold
  → merges flagged pairs into cliques via union-find (chains merge
  even when the ends are weakly linked).
- `CorrelatedErrorReport` — pairs (with Q), cliques, threshold,
  `recommendations()` ("keep one, drop or downweight the rest" —
  slice 116 acts on these).
- Validation: ≥2 members, threshold in [-1, 1], aligned non-empty
  histories.

## Eldra (code)
Real detection on top of slice 110's `q_statistic`; no stubs.

## Sólrún (tests)
`tests/test_ensemble_115_correlation.py` — 8 tests green:
success (identical members flagged Q=1.0 with clique + recommendation,
independent members clean, partial clique, chained a~b~c merging to
one clique with hand-verified Q values 0.6/0.6/-0.6, threshold
sensitivity, report dict),
failure (single member, bad threshold, misaligned/empty histories),
boundary (pairs sorted by Q descending at threshold 0.0).

## Védis (integrate)
- `CorrelatedPair`, `CorrelatedErrorReport`,
  `detect_correlated_errors` exported; feeds slice 116's
  downweighting.

## Scribe
Committed `feat(gjallarbu-115): correlated-error detection`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/correlation.py`
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_115_correlation.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_115_correlation.py -q` → 8 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
