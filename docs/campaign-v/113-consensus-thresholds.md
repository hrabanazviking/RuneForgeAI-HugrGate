# Slice 113 — Consensus thresholds

**Status:** complete · **Commit:** `feat(gjallarbu-113): consensus thresholds`

## Skald (inspect)
Detection (111) classifies splits and escalation (112) reacts, but
nothing enforced a *supermajority bar* on the winner's share — a
51% squeaker was accepted exactly like unanimity.

## Rúnhild (design)
New module `hugrgate/ensemble/consensus.py`:
- `ConsensusConfig(min_agreement)` with `majority()` (0.5),
  `supermajority()` (2/3), `unanimity()` (1.0) presets; bar must be
  in (0, 1].
- `winner_share(result)`: prefers `metadata["ensemble"]["winner_share"]`
  (vote share for ballot strategies), falls back to probability.
- `apply_consensus(result, spec, config)`: never raises — a shortfall
  becomes an abstention whose reason names share and bar; passes
  record `metadata["ensemble"]["consensus"]`.
- `maybe_apply_consensus(result, spec, setting)`: accepts a float, a
  config, or a dict; `None` passes through.
- Integration: `Ensemble.evaluate` applies the gate when the
  `consensus` strategy option is set
  (`strategy_options={"consensus": 0.67}`).

## Eldra (code)
Real gate logic, no stubs; malformed settings raise `PolicyError`.

## Sólrún (tests)
`tests/test_ensemble_113_consensus.py` — 11 tests green:
success (majority passes, 2/3 boundary inclusive, unanimity needs
every ballot, strategy-option wiring, share fallback to
probability, all `maybe_apply` forms, presets),
failure (bars 0/1.5/negative, malformed settings),
boundary (soft-strategy mass 0.45 fails a 0.5 majority — the share
used is the strategy's own winner share).
Ensemble suite: 170 passed; mypy clean.

## Védis (integrate)
- `ConsensusConfig`, `winner_share`, `apply_consensus`,
  `maybe_apply_consensus` exported; the `consensus` strategy option
  is additive (unset → zero behavior change, verified by the
  untouched earlier suites).

## Scribe
Committed `feat(gjallarbu-113): consensus thresholds`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/consensus.py`
- `hugrgate/ensemble/api.py` (consensus hook),
  `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_113_consensus.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_10*.py tests/test_ensemble_11*.py -q` → 170 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
