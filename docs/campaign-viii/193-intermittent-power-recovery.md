# Slice 193 — Intermittent-power recovery

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_recovery.py` (10 tests, green)

## What existed before

Slice 191 made individual writes atomic, but nothing answered "what
was I doing when the power died?" — a node that loses power mid-batch
would restart with no memory of its in-flight work.

## What was built

`hugrgate/edge/recovery.py` — `CheckpointJournal`:

- **`checkpoint(state_id, payload)`** — atomically persists a
  CRC32-protected JSON record (temp → fsync → `os.replace`);
  sequence numbers survive reopen (no reuse after reboot); only the
  newest `keep` checkpoints retained.
- **`latest()` / `recover()`** — newest *valid* checkpoint; corrupt
  records are *skipped*, never trusted: a torn write (simulated by
  truncating a record mid-file) and a bit-flipped payload both fail
  CRC and the journal falls back to the previous good record
  (test-pinned).
- **`mark_complete(state_id)`** — removes finished work, turning
  at-least-once resume into at-most-once handoff.
- **Strict validation**: non-JSON payloads, empty state ids, alien
  magic, and truncated logs all raise `RecoveryError` or are skipped
  — nothing half-loads.
- Dependency-free by design: recovery works at the earliest boot
  stage, before the wear store exists.

## Integration

- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended. Pairs with slice 191's atomic flush
  (same tmp+fsync+replace discipline) and will back slice 200's
  resume-from-checkpoint flows.

## Validation notes (Execution Law rule 13)

Simulated power cuts (truncated/bit-flipped files), not real brownout
testing — on-device validation should yank power mid-checkpoint and
confirm resume.

## Verification

- `pytest tests/test_edge_recovery.py` — 10 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
