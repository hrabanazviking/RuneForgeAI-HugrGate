# Slice 260 — Read-only filesystem test

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_readonly_fs.py` (8 tests, green)

## What existed before

Slice 259 simulated a full disk and mapped `ENOSPC` to
`StorageError` in `WearAwareStore.flush()` — but a **read-only**
filesystem is a different failure (writes are *forbidden*, not
merely out of space), and the same raw-`OSError` leak class existed
in `CheckpointJournal.checkpoint()` (`hugrgate/edge/recovery.py`):
`EROFS`/`ENOSPC` during checkpoint writes propagated as raw
`OSError`, not the taxonomy's `RecoveryError`.

## What was built

- `read_only(errno_code=EROFS)` in `hugrgate/chaos/filesystem.py`
  (shipped with the module in slice 259, exercised here):
  write-mode opens raise `OSError(EROFS)`; reads pass through.
- Hardened `CheckpointJournal.checkpoint()`: `ENOSPC`/`EDQUOT` →
  `RecoveryError("disk full …")`, `EROFS` →
  `RecoveryError("read-only filesystem …")`, other `OSError`s →
  `RecoveryError("… write failed")`. Torn temp files removed
  best-effort; the consumed sequence number is intentionally not
  reused (the journal tolerates gaps).

## Behavior verified

- **Reads keep working** on a read-only filesystem: store `get`
  (RAM index + log replay at open) and journal `latest()`/
  `recover()` are unaffected.
- **Writes fail loudly, never silently**: buffered `put` works
  (RAM-only), `flush` raises `StorageError` (EROFS message is
  distinct from the disk-full message), and `close()` with pending
  writes propagates the `StorageError` instead of pretending the
  data was persisted.
- **Recovery**: after the read-only/full condition lifts,
  retained buffers flush and the journal checkpoints normally;
  no `.json.tmp` / `.log.tmp` debris.

## Integration

- Error semantics: `RecoveryError` (`code
  "edge_recovery_error"`, recoverable) — a read-only mount is
  retryable after remounting read-write.
- No new error class.

## Verification

- 8 tests: simulation blocks writes not reads; read-path
  survival for store and journal; buffered-put/flush/close
  failure semantics; post-recovery writes; journal `ENOSPC` and
  `EROFS` mapping with temp-file cleanup.
- Existing `test_edge_recovery.py` + `test_edge_storage.py`
  re-run green.
- `ruff check` clean.
