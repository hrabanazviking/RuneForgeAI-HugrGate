# Slice 127 — Outcome feedback API

**Status:** complete. **Tests:** `tests/test_adaptive_feedback.py` — 12 tests green.

## What existed before

Telemetry (slice 126) could store outcomes, but there was no write path with
a contract: no label vocabulary, no validation, no guard against overwriting
history.

## What was built

`hugrgate/adaptive/feedback.py`:

- `OutcomeFeedbackAPI`: the single write path for outcome labels onto
  telemetry. `quality ∈ [0,1]` required; `label` restricted to
  `("success", "failure", "partial")` — mirroring `DecisionPolicy`'s
  privacy-class rule so a typo can never become a new class. Unknown
  `request_id` → `KeyError`. Outcomes immutable once attached unless the
  caller passes `allow_overwrite=True` explicitly.
- `OutcomeRecord`: frozen dataclass — quality, label, source, received_at.
- `record_immediate`: logs a route decision *and* its immediately-known
  quality in one call (result probability when the policy accepts, 0.0 on
  abstain), labeled `source="immediate"` — the online bandit's bread and
  butter, refinable later by delayed labels.

## Integration

- Policy: immediate quality derives from `DecisionPolicy.evaluate` verdict.
- Validation/errors: `SpecError` on bad quality/label/source; `KeyError` on
  unknown ids. Provenance: every outcome carries source + timestamp.

## Verification

- `pytest tests/test_adaptive_feedback.py` — 12/12 green, including
  immediate-path accept/abstain, double-record rejection, overwrite flag,
  unknown-label rejection.
- `mypy hugrgate/adaptive` — clean.
