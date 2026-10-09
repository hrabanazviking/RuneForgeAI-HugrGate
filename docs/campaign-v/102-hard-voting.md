# Slice 102 — Hard voting

**Status:** complete · **Commit:** `feat(gjallarbu-102): hard voting`

## Skald (inspect)
Slice 101 shipped the `Ensemble` API with soft voting only. No
ballot-counting combiner existed; `collect_votes` treated a member
returning an abstention-*shaped* result (`value=None`, no exception)
as a usable vote for `None` — uncountable and a corrupt ballot.

## Rúnhild (design)
`hard_voting` in `hugrgate/ensemble/voting.py`, registered as strategy
`"hard"`:
- One ballot per member (weights deliberately do **not** buy extra
  ballots — pinned by test).
- Winner = argmax of the tally; `P(winner)` = vote share;
  distribution covers the full spec value space (unvoted options get
  0); uncertainty = `1 - share`.
- Deterministic tie ladder: most self-confident tied camp (sum of the
  camp members' own probabilities) → earliest ballot → lexicographic.
  The rung used is recorded in `metadata["ensemble"]["tie_broken_by"]`.
- `base.py` hardening: `collect_votes` now records `value=None`
  results as skipped (`"abstained_result"`) instead of seating a
  `None` ballot.
- Discrete specs only (`require_discrete_spec`); no-ballot input
  raises `BackendError` (defensive: unreachable via `Ensemble`, which
  fails earlier in `collect_votes`).

## Eldra (code)
Real combiner, no stubs. `finalize_result` keeps the shared metadata
contract (strategy, tally, winner share, minority report).

## Sólrún (tests)
`tests/test_ensemble_102_hard_voting.py` — 13 tests green:
success (majority + share math, unanimity → zero uncertainty,
confidence tie-break, earliest-ballot tie-break, weights don't buy
ballots, binary/ordinal specs, single member, failing members don't
vote),
failure (no ballots → `BackendError`, numeric spec rejected,
all-abstain → `BackendError`),
boundary (abstention-shaped result skipped with reason
`"abstained_result"`, 5-member 2-2-1 split elects the more confident
camp with exact share math).

## Védis (integrate)
- Strategy registry gains `"hard"`; package `__init__` re-exports
  `hard_voting`.
- Regenerated API inventory doc picks up the new public name
  (via the slice-101 generator workflow; doc committed with 101 —
  inventory test re-verified green after this slice).

## Scribe
Committed `feat(gjallarbu-102): hard voting`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/voting.py` (`hard_voting`, `_ballots`)
- `hugrgate/ensemble/base.py` (abstention-shaped result skip)
- `hugrgate/ensemble/api.py`, `hugrgate/ensemble/__init__.py`
  (strategy registration + export)
- `tests/test_ensemble_102_hard_voting.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py tests/test_ensemble_102_hard_voting.py -q` → 38 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
