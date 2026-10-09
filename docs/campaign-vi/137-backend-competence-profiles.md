# Slice 137 — Backend competence profiles

**Status:** complete. **Tests:** `tests/test_adaptive_competence.py` — 12 tests green.

## What existed before

`hugrgate/health.py` (slice 17) scored backend health (latency/errors/
quarantine), but nothing remembered long-run *quality* per backend.

## What was built

`hugrgate/adaptive/competence.py`:

- `CompetenceProfile`: attempts, successes (quality ≥ threshold), quality /
  latency / cost sums → means; **Wilson score lower bound** on the success
  rate as the conservative competence estimate (10/10 outranks 1/1; a
  battle-tested 85% outranks a lucky 100% on three samples).
- `BackendCompetenceProfiles`: registry with `observe` (online path),
  `update_from_telemetry` (batch path — labeled, non-shadow events only),
  `ranked` (Wilson-lower ordering — the exploitation-safe ordering),
  `to_dict`/`from_dict` (`adaptive-competence/v1`) for versioning/rollback.
- `get` returns defensive copies; the registry owns its profiles.

## Integration

- Telemetry (slice 126) as the batch source; `SpecError` on bad inputs and
  foreign schemas.

## Verification

- `pytest tests/test_adaptive_competence.py` — 12/12 green: accumulation
  math, Wilson skepticism of n=1, Wilson-ordered ranking, telemetry batch
  update skipping shadow/unlabeled, serialization, defensive copies.
- `mypy hugrgate/adaptive` — clean.
