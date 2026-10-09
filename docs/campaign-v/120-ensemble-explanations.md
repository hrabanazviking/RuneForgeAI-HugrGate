# Slice 120 — Ensemble explanations

**Status:** complete · **Commit:** `feat(gjallarbu-120): ensemble explanations`

## Skald (inspect)
`metadata["ensemble"]` was machine-readable only — operators and
auditors had no plain-words account of a council decision.

## Rúnhild (design)
New module `hugrgate/ensemble/explanations.py`:
- `explain_ensemble(result, style="concise"|"verbose")` renders the
  decision from recorded metadata — every claim read straight out
  of the metadata, so the text can never drift from the decision.
- concise: one paragraph — verdict, vote split, dissenters, plus
  outcome notes (disagreement level, review flag / fallback,
  consensus pass/fail, calibration temperature, skipped ballots).
- verbose: multi-line — per-member ballots with weights, minority
  report section, notes.
- Abstentions explain themselves ("declined to decide" + reason
  notes); non-ensemble results raise `PolicyError`.

## Eldra (code)
Pure rendering, no new inference.

## Sólrún (tests)
`tests/test_ensemble_120_explanations.py` — 11 tests green:
success (concise verdict/votes/dissent; unanimous omits dissent;
verbose ballots + minority report; consensus-failure narration;
disagreement-escalation narration; calibration note),
failure (non-ensemble result, provenance-marked non-ensemble,
unknown style),
boundary (bare abstention with skipped ballot still explains).
mypy clean.

## Védis (integrate)
- `explain_ensemble` exported; narrates 112's escalation, 113's
  consensus, 114's minority report, 118's calibration from their
  recorded metadata.

## Scribe
Committed `feat(gjallarbu-120): ensemble explanations`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/explanations.py`
- `hugrgate/ensemble/__init__.py` (export)
- `tests/test_ensemble_120_explanations.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_120_explanations.py -q` → 11 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
