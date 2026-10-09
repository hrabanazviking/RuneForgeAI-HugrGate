# Slice 145 — Router rollback

**Status:** complete. **Tests:** `tests/test_adaptive_rollback.py` — 11 tests green.

## What existed before

Adaptive policy state (bandit weights, profiles, counters) had no
undo — a bad promotion was permanent.

## What was built

`hugrgate/adaptive/rollback.py` — `RouterRollback`:

- `checkpoint(state, note)`: archives any JSON-serializable state dict as
  `ckpt-<n>`; states are validated *strictly* (no `default=str` — a lambda
  must not stringify into a lie); the archive is bounded (`max_checkpoints`,
  oldest evicted).
- `rollback(steps=1)`: restores the state from N checkpoints back as a deep
  copy (callers can't mutate the archive); the stack is not truncated —
  restore, then re-checkpoint explicitly, keeping history honest.
- Guardrails: `steps < 1` rejected; rolling back past genesis rejected.
- `audit_log()`: append-only record of every checkpoint *and* rollback —
  rolling back never erases the fact that a rollback happened.

## Integration

- Checkpoints slice-130 bandit `to_dict()`s, slice-137 profile dicts,
  exploration snapshots — anything JSON-serializable; `SpecError` throughout.

## Verification

- `pytest tests/test_adaptive_rollback.py` — 11/11 green: round-trip,
  sequential ids, bounded eviction, deep-copy isolation, audit completeness,
  past-genesis/non-positive-step refusal, non-serializable rejection.
- `mypy hugrgate/adaptive` — clean.
