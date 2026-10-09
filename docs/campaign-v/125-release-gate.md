# Slice 125 — Ensemble release gate

**Status:** complete · **Commit:** `feat(gjallarbu-125): release gate`

## Skald (inspect)
No go/no-go verdict existed for an ensemble configuration —
benchmarks, diversity, cliques, adversarial evidence, and docs
lived in separate places with no single throat to choke.

## Rúnhild (design)
New module `hugrgate/ensemble/release.py`:
- `ReleaseGate(name)` — composes named checks (zero-arg callables
  returning `(passed, detail)`); `run()` executes all of them (a
  raising check fails with the exception recorded) and returns a
  `ReleaseVerdict` with `passed`, `failures`, `to_dict()`, and a
  human `summary()`.
- Built-in check factories, all real measurements:
  - `benchmark_thresholds` — accuracy/ECE/Brier floors via slice
    124's harness;
  - `diversity_floor` — mean disagreement rate (110) must clear
    the floor;
  - `no_correlated_cliques` — slice 115 finds no error cliques;
  - `adversarial_clean` — slice 123's suite: no UNEXPECTED errors,
    full decisions unless the case is in `may_refuse`;
  - `evidence_check` — wraps caller-supplied evidence (CI results,
    completion notes) the gate cannot measure itself.

## Eldra (code)
Real composition; no new inference.

## Sólrún (tests)
`tests/test_ensemble_125_release.py` — 12 tests green:
success (healthy council passes 5/5; may_refuse allows honest
refusal),
failure (each failing check blocks release with a named detail:
benchmark accuracy, diversity floor, correlated clique naming
a+b, adversarial dropout, missing evidence, raising check fails
gracefully, empty gate never passes),
failure-construction (gate/check/factory validations),
boundary (threshold at exact boundary passes).
Caught in testing: Q needs variation — identical always-wrong
histories score Q=0 (documented guard), so the clique test uses
err-together/right-together histories. mypy clean.

## Védis (integrate)
- Gate + factories exported; consumes 110/115/123/124.

## Scribe
Committed `feat(gjallarbu-125): release gate`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/release.py`
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_125_release.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_125_release.py -q` → 12 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
