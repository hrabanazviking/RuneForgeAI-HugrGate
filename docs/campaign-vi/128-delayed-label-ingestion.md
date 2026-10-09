# Slice 128 — Delayed-label ingestion

**Status:** complete. **Tests:** `tests/test_adaptive_delayed.py` — 10 tests green.

## What existed before

The feedback API (slice 127) assumed the label and the telemetry meet at call
time. Real outcomes arrive late — or, in streaming joins, *before* their
telemetry.

## What was built

`hugrgate/adaptive/delayed.py` — `DelayedLabelIngestion`, the patient join:

- `ingest`: applies immediately when telemetry is present and unlabeled;
  parks in a bounded pending queue (`max_pending`) when it isn't; rejects
  malformed labels *before* queueing (validated via `OutcomeRecord`).
- `drain`: applies parked labels whose telemetry has since arrived.
- `sweep`: expires labels older than `ttl_s`, applies the matchable rest,
  returns a `SweepReport` — drops are counted (`dropped_expired`), never
  swallowed. Labels arriving already stale, or duplicating an existing
  outcome, expire on arrival rather than corrupting history.

## Integration

- Builds on slice 127's `OutcomeFeedbackAPI` (single write path preserved);
  errors use `SpecError`; queue-full is a loud `SpecError`, not silent loss.

## Verification

- `pytest tests/test_adaptive_delayed.py` — 10/10 green: immediate apply,
  park/drain, TTL expiry accounting, duplicate-arrival keeps earliest,
  malformed-label rejection, queue bound, stale-duplicate drop.
- `mypy hugrgate/adaptive` — clean.
