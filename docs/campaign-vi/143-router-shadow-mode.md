# Slice 143 — Router shadow mode

**Status:** complete. **Tests:** `tests/test_adaptive_shadow.py` — 10 tests green.

## What existed before

No way to evaluate a candidate policy without serving it — every policy
change was a leap of faith.

## What was built

`hugrgate/adaptive/shadow.py` — `RouterShadowMode`:

- `record_shadow(...)`: logs what the candidate *would* have chosen
  (features, candidates, propensities, shadow choice, served choice) into
  the telemetry store flagged `shadow=True`, tagged with a candidate
  policy version. Returns the served arm's flow untouched — shadow records
  never affect serving.
- Shadow events are excluded from offline training (slice 131 skips them).
- `divergence_report()`: n_shadow, n_diverged, divergence rate, per-arm
  agreement matrix — how often the candidate would have disagreed, and
  where. Disabled mode logs nothing (`None`).
- Provenance note: the served choice is kept in metadata alongside the
  shadow choice, so divergence is always joinable.

## Integration

- Telemetry store (slice 126) with the `shadow` flag contract; `SpecError`
  on bad choices/propensities.

## Verification

- `pytest tests/test_adaptive_shadow.py` — 10/10 green: shadow/served
  separation, shadow exclusion from training (labeled or not), divergence
  counting and agreement matrix, empty report, disabled mode, per-served
  filtering, version tagging.
- `mypy hugrgate/adaptive` — clean.
