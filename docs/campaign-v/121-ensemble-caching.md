# Slice 121 — Ensemble caching

**Status:** complete · **Commit:** `feat(gjallarbu-121): ensemble caching`

## Skald (inspect)
Every `evaluate()` re-ran all members from scratch — repeated
identical states re-paid the full council cost, with no privacy
story for sensitive states.

## Rúnhild (design)
New module `hugrgate/ensemble/caching.py`:
- `EnsembleCache` — TTL + LRU keyed on the canonical
  `(state, spec, strategy)` JSON triple. `invalidate_member` drops
  every entry whose council included that member; `invalidate`
  clears all; `stats()` reports size/hits/misses/evictions.
  Deep-copy in and out (ProvenanceStore discipline) so callers
  cannot corrupt cached results.
- `CachedEnsemble` — wraps an `Ensemble`; `evaluate(..., privacy=...)`
  serves hits and fills misses. `privacy="strict"` bypasses the
  cache entirely (sensitive states are never written to it).
- Documented: changing fitted models/options without changing the
  key needs a fresh cache or `invalidate()`.

## Eldra (code)
Real cache; caught and fixed a real bug during testing (below).

## Sólrún (tests)
`tests/test_ensemble_121_caching.py` — 13 tests green:
success (repeat state served from cache, key covers state and
strategy, TTL=0 always misses, LRU eviction, member invalidation,
full invalidation, strict-privacy bypass, deep-copy isolation,
wrapper surface, supplied-cache identity),
failure (maxsize/ttl/privacy/wrap validations),
boundary (maxsize=1 keeps latest).
Notable catch: `cache or EnsembleCache()` silently replaced a
*supplied but empty* cache (falsy via `__len__`) — now
`cache if cache is not None else ...`, with a regression test.
mypy clean.

## Védis (integrate)
- `EnsembleCache`, `CachedEnsemble` exported.

## Scribe
Committed `feat(gjallarbu-121): ensemble caching`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/caching.py`
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_121_caching.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_121_caching.py -q` → 13 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
