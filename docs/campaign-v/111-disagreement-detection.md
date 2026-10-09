# Slice 111 — Disagreement detection

**Status:** complete · **Commit:** `feat(gjallarbu-111): disagreement detection`

## Skald (inspect)
Slice 110 provided raw diversity metrics but nothing turned them
into a *verdict*. No component classified a round of ballots as
agreed / mildly split / strongly split.

## Rúnhild (design)
Detection half of `hugrgate/ensemble/disagreement.py`:
- `DisagreementThresholds` — tunable bars (strong/mild disagreement
  rate, strong/mild vote entropy, mild winner-margin), validated
  (`strong >= mild`, ranges sane).
- `DisagreementDetector.detect(votes)` → `DisagreementReport`
  (level none/mild/strong, `disagree` bool, the three metrics,
  plurality value with deterministic earliest-ballot tie-break, named
  dissenters, ballot count, `to_dict`). One ballot (or zero) cannot
  disagree with itself → `none`; skipped votes excluded.
- Detection rule: strong when disagreement_rate ≥ strong bar or
  entropy ≥ strong bar; mild when either mild bar is crossed or the
  winner margin is thinner than `mild_margin`; else none.

## Eldra (code)
Real detection logic, no stubs. (Escalation 112 and minority-report
114 live in later commits on this same module.)

## Sólrún (tests)
`tests/test_ensemble_111_disagreement.py` — 12 tests green:
success (unanimous → none, 2-1 → strong, 4-1 → mild, single/empty
ballots → none, skipped excluded, custom thresholds flip the
verdict, margin-only mild, report dict, end-to-end via
`Ensemble.member_votes`),
failure (threshold misconfiguration ×4),
boundary (three-way split names both dissenters, plurality by
earliest ballot).

## Védis (integrate)
- `LEVEL_NONE/MILD/STRONG`, `DisagreementThresholds`,
  `DisagreementReport`, `DisagreementDetector` exported from
  `hugrgate.ensemble`.
- Fixed a latent repo bug found en route: `tools/gen_api_inventory.py`
  rendered function-valued constants (e.g. `STRATEGIES`) with memory
  addresses, making the "byte-identical on re-run" doc
  non-deterministic — now scrubs `0x…` addresses; verified two
  consecutive runs are byte-identical.
- Regenerated the API inventory doc (deterministic again).

## Scribe
Committed `feat(gjallarbu-111): disagreement detection`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/disagreement.py` (detection half)
- `hugrgate/ensemble/__init__.py` (exports)
- `tools/gen_api_inventory.py` (address scrubbing),
  `docs/campaign-i/003-public-api-inventory.md` (regenerated)
- `tests/test_ensemble_111_disagreement.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_111_disagreement.py -q` → 12 passed
- `venv/bin/python tools/gen_api_inventory.py` (twice; byte-identical)
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
