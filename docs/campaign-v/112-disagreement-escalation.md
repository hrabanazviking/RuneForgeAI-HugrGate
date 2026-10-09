# Slice 112 — Disagreement escalation

**Status:** complete · **Commit:** `feat(gjallarbu-112): disagreement escalation`

## Skald (inspect)
Slice 111 could *detect* disagreement but nothing *acted* on it —
a strong split flowed into the decision exactly like unanimity.

## Rúnhild (design)
Escalation half of `hugrgate/ensemble/disagreement.py`:
- `EscalationPolicy` — `mild_action` / `strong_action` in
  {none, review, abstain, fallback}, validated; `fallback` requires a
  `fallback_backend` at construction (fail fast, not at 3am).
- `escalate(result, spec, report, policy, state, context)`:
  - `none` → result passes through, report recorded in
    `metadata["ensemble"]["disagreement"]`;
  - `review` → `mark_for_review` (value preserved, `accepted=False`,
    reason names the level, rate, and dissenters);
  - `abstain` → `abstain()` with a machine-readable reason;
  - `fallback` → the fallback backend decides; its result is marked
    `fallback_used=True` with the disagreement reason; a failing
    fallback raises `BackendError` honestly (never silently).
- Never raises for the disagreement itself — only for a broken
  fallback.

## Eldra (code)
Real policy mapping reusing slice-15's `abstain`/`mark_for_review`
vocabulary; no stubs.

## Sólrún (tests)
`tests/test_ensemble_112_escalation.py` — 9 tests green:
success (none passes through, mild→review flags with value
preserved, strong→abstain refuses with named reason,
strong→fallback uses the fallback backend marked `fallback_used`,
mild→none decides anyway, end-to-end ensemble→detect→escalate),
failure (failing fallback raises `BackendError`, policy
misconfiguration ×4),
boundary (report recorded under `metadata["ensemble"]` for review
and abstain alike).

## Védis (integrate)
- `EscalationPolicy`, `escalate` exported from `hugrgate.ensemble`;
  integrates with the abstention/review vocabulary and the shared
  ensemble metadata contract.

## Scribe
Committed `feat(gjallarbu-112): disagreement escalation`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/disagreement.py` (escalation half)
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_112_escalation.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_112_escalation.py -q` → 9 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
