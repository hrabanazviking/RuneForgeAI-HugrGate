# Slice 103 — Soft voting (hardening)

**Status:** complete · **Commit:** `feat(gjallarbu-103): soft voting hardening`

## Skald (inspect)
`soft_voting` (slice 101) averaged blindly: a member voting a bare
value with an empty distribution counted in the divisor while
contributing nothing (the average stopped summing to 1), and member
weights were ignored entirely — the documented weight semantic had no
effect on the default strategy.

## Rúnhild (design)
Two hardenings in `hugrgate/ensemble/voting.py`:
1. **Empty-distribution completion** (`_complete_distribution`): a
   bare value+probability ballot is completed to `{value: p, others:
   (1-p)/(k-1)}` — the slice-13 rules-backend semantics. A non-empty
   distribution is untouched (its missing keys are genuine zeros;
   validity already forces it to sum to 1). Completed members are
   named in `metadata["ensemble"]["completed_distributions"]`.
2. **Weight-aware averaging**: `p(v) = Σ wᵢ·distᵢ(v) / Σ wᵢ`; zero
   total weight raises `BackendError` instead of dividing by zero.

Weight-semantic bugfix across `base.py`/`api.py` (found by the new
tests): `Ensemble` validated weights but stored the raw map while
`collect_votes` defaulted unnamed members to 1.0 — contradicting
`normalize_weights`. One documented semantic now: a weights map names
the members that count (unnamed → 0); `Ensemble` stores the normalized
map; `collect_votes` uses `None` → 1.0 each, provided map → missing 0.

## Eldra (code)
Real hardening, no stubs. `soft_voting` still never raises on ordinary
disagreement; the new `BackendError`s cover only degenerate inputs
(no usable votes, non-positive total weight, uncompletable ballot).

## Sólrún (tests)
`tests/test_ensemble_103_soft_voting.py` — 11 tests green:
success (weights shift the average with exact math, unweighted average
unchanged incl. deterministic tie, empty-distribution completion,
certainty completion, 3-option completion, incomplete ballot no longer
dilutes),
failure (zero total weight, no usable votes, uncompletable ballot),
boundary (single dominant weight, partial weights map → unnamed member
gets 0 — the test that caught the semantic bug).
Full ensemble suite: 49 passed; mypy clean.

## Védis (integrate)
- No API surface change (same strategy name, richer metadata).
- API inventory doc stays fresh (no new public names).

## Scribe
Committed `feat(gjallarbu-103): soft voting hardening`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/voting.py` (`_complete_distribution`,
  weight-aware `soft_voting`)
- `hugrgate/ensemble/base.py`, `hugrgate/ensemble/api.py`
  (single weight semantic)
- `tests/test_ensemble_103_soft_voting.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_101_api.py tests/test_ensemble_102_hard_voting.py tests/test_ensemble_103_soft_voting.py -q` → 49 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
