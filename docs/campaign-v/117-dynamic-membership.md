# Slice 117 — Dynamic ensemble membership

**Status:** complete · **Commit:** `feat(gjallarbu-117): dynamic membership`

## Skald (inspect)
The member roster was frozen at construction: a degrading backend
kept voting forever, and no path existed to bench or promote members
on evidence.

## Rúnhild (design)
New module `hugrgate/ensemble/membership.py`:
- `MembershipManager(members, ...)` holds the backends and curates
  active / standby / retired statuses on Laplace-smoothed
  reliability (via slice 116's `ReliabilityTracker`):
  - active + reliability < `retire_below` over ≥ `min_observations`
    → retired (never below `min_active`);
  - standby + reliability ≥ `promote_above` over ≥
    `min_observations` → promoted;
  - no judgment before enough evidence.
- Manual `retire` / `to_standby` / `activate` controls; every
  transition appended to a sequence-numbered deterministic event log
  (for slice 119's provenance).
- `build_ensemble(strategy, **kwargs)` constructs an `Ensemble` from
  active members (local import keeps the import graph acyclic).

## Eldra (code)
Real roster logic; the strict `<` retirement boundary is pinned.

## Sólrún (tests)
`tests/test_ensemble_117_membership.py` — 12 tests green:
success (all start active, sustained failure retires with event,
standby promotion, manual transitions with ordered event log,
build_ensemble uses actives only, to_dict),
failure (all constructor/observer validations, no-actives build
rejected),
boundary (no retirement before min_observations, min_active never
breached with retire_blocked events, exact-bar reliability does not
retire).

## Védis (integrate)
- `MembershipManager`, status constants exported; composes with
  116's tracker and feeds 119's provenance via the event log.

## Scribe
Committed `feat(gjallarbu-117): dynamic membership`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/membership.py`
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_117_membership.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_117_membership.py -q` → 12 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
