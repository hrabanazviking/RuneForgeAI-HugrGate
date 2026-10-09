# Slice 123 — Ensemble adversarial tests

**Status:** complete · **Commit:** `feat(gjallarbu-123): adversarial tests`

## Skald (inspect)
Fault isolation was designed but never attacked: no systematic
proof that dropout, corruption, abstention waves, tie storms, or
slow members degrade gracefully instead of crashing or silently
corrupting.

## Rúnhild (design)
New module `hugrgate/ensemble/adversarial.py`:
- Deterministic saboteur backends (every-k-th-call patterns, no
  RNG): `SaboteurBackend` base + `DropoutBackend` (BackendError),
  `CorruptBackend` (mass≠probability — the contract catches it),
  `AbstainBackend` (Abstention), `SlowBackend` (sleeps, stays
  honest).
- `tie_storm_members(n, values, dist)` — an evenly split
  electorate to pin the documented tie-break.
- `AdversarialCase` + `run_adversarial_suite(cases)` — per-case
  summaries: decided values, errors (BackendError vs UNEXPECTED),
  min usable votes, skip-reason counts.

## Eldra (code)
Production-safe: the tie-storm backend is defined in-module (no
test-fake imports); `Backend.name` overridden as a plain
attribute per the base class.

## Sólrún (tests)
`tests/test_ensemble_123_adversarial.py` — 9 tests green:
success (dropout isolated with 2/3 usable, intermittent dropout
deterministic counts, corrupt ballots rejected as invalid_result,
abstention wave refuses honestly via BackendError, tie storm
resolves to earliest ballot, slow member doesn't block,
multi-case suite),
failure (all saboteur/suite validations),
boundary (every=1 sabotages always).
mypy clean.

## Védis (integrate)
- All scenario helpers exported; suite output feeds slice 125's
  release gate evidence.

## Scribe
Committed `feat(gjallarbu-123): adversarial tests`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/adversarial.py`
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_123_adversarial.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_123_adversarial.py -q` → 9 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
