# Slice 131 — Offline policy learning

**Status:** complete. **Tests:** `tests/test_adaptive_offline.py` — 9 tests green.

## What existed before

The bandit (slice 130) learned online only. The telemetry log (slice 126) was
write-only — no batch training path.

## What was built

`hugrgate/adaptive/offline.py` — `OfflinePolicyLearning.fit`:

- Trains a fresh `ContextualBanditAdapter` from logged events **without
  touching production**.
- Uses only **labeled, non-shadow** events; rewards from outcome quality
  (fallback: immediate quality); **inverse-propensity weighting** clipped to
  `max_weight` corrects the logging policy's selection bias; events below
  `min_propensity` are skipped, not trusted.
- `LearningDiagnostics`: counts of used/unlabeled/shadow/bad-propensity/
  clipped events plus effective sample size — a fit on twelve events is
  reported, not hidden. `min_events` refuses degenerate fits loudly.
- `fit_store` convenience for `TelemetryStore`.

## Integration

- Telemetry schema (slice 126), bandit (slice 130); `SpecError` for
  degenerate/insufficient data.

## Verification

- `pytest tests/test_adaptive_offline.py` — 9/9 green: learns the better
  arm from biased logs, IPS weighting corrects a logging policy that loved
  the worse arm, shadow/unlabeled/bad-propensity skipping with counts,
  clipping diagnostics, min-events refusal.
- `mypy hugrgate/adaptive` — clean.
