# Slice 122 — Ensemble batch mode

**Status:** complete · **Commit:** `feat(gjallarbu-122): ensemble batch mode`

## Skald (inspect)
`Ensemble.decide_batch` was a naive per-state loop — members with a
real `batch()` fast path never got to use it, and N states meant N
full vote collections.

## Rúnhild (design)
New module `hugrgate/ensemble/batch.py`:
- `batch_collect_votes(members, states, spec, ...)` — one
  `member.batch()` call per member for the whole batch, transposed
  into per-state ballot lists. Fault isolation mirrors
  `collect_votes` per (member, state):
  - `batch()` raising → per-state `evaluate` fallback for that
    member;
  - wrong-length batch results → member skipped for every state
    (`batch_length_mismatch`);
  - each result validated; abstention-shaped/invalid results become
    named skip votes;
  - `BackendError` only when a state has < min_members usable votes
    (names the state index).
- `Ensemble.decide_batch` now collects via the batch path, then
  combines each state's ballots exactly as `evaluate()` does —
  same combiner, same consensus option, per-state latency timing.
- Also renamed `hugrgate/ensemble/caching.py` → `cache.py` to match
  the pre-registered arch-map module names.

## Eldra (code)
No new inference; pure orchestration over existing contracts.

## Sólrún (tests)
`tests/test_ensemble_122_batch.py` — 10 tests green:
success (fast path called once per member, batch == single
evaluates incl. weights, batch-raise fallback keeps isolation,
length-mismatch skips member, per-state fault isolation with named
skip reasons, consensus applied per state, empty batch),
failure (per-state min_members BackendError, min_members
validation),
boundary (single-state batch matches evaluate).
Full ensemble suite: 262 passed. mypy clean (62 files).

## Védis (integrate)
- `batch_collect_votes` exported; `decide_batch` keeps its
  signature — backward compatible, now faster.

## Scribe
Committed `feat(gjallarbu-122): ensemble batch mode`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/batch.py`
- `hugrgate/ensemble/api.py` (decide_batch via batch path)
- `hugrgate/ensemble/cache.py` (renamed from caching.py)
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_122_batch.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_122_batch.py -q` → 10 passed
- `venv/bin/python -m pytest tests/ -q -k ensemble` → 262 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
