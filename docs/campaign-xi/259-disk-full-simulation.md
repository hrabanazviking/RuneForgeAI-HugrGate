# Slice 259 — Disk-full simulation

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_disk_full.py` (6 tests, green)

## What existed before

`WearAwareStore.flush()` (slice 191) wrote via temp file +
`os.replace` + fsync for power-cut atomicity — but a **full disk**
broke the taxonomy contract: `open(tmp, "wb")` raising `OSError`
(`ENOSPC`) propagated as a raw `OSError`, not the taxonomy's
`StorageError`, and the torn temp file was left behind. Nothing
simulated a full disk, so the failure mode was untested.

## Attack (Yrsa Law 11)

Probed `flush()` with an `ENOSPC`-raising `open`: confirmed the raw
`OSError` escaped and the `.log.tmp` file survived. Both fixed.

## What was built

`hugrgate/chaos/filesystem.py` — deterministic filesystem fault
simulation without needing a real full disk:

- `disk_full(errno_code=ENOSPC)`: context manager patching
  `builtins.open` so write-mode opens raise `OSError(ENOSPC)`
  ("No space left on device"); reads pass through untouched.
  Single-threaded test tool, documented as such.
- (`read_only` ships in the same module for slice 260.)

Hardening in `hugrgate/edge/storage.py`:

- `flush()` wraps the write section: `ENOSPC`/`EDQUOT` →
  `StorageError("disk full while flushing …; buffer retained,
  retry after freeing space")`; other `OSError`s →
  `StorageError("flush to … failed: …")`. The torn temp file is
  removed best-effort; the coalescing buffer is **retained** so the
  write can be retried after space is freed — no data loss, no
  raw `OSError` leakage.

## Integration

- Error semantics: `StorageError` (`code "edge_storage_error"`,
  recoverable) — a full disk is retryable after freeing space.
- Recovery story verified end to end: fail under `disk_full()`,
  exit the context ("space freed"), `flush()` succeeds, data
  survives a close + reopen from the log.

## Verification

- 6 tests: simulation blocks writes not reads (incl. `r+b`,
  custom errno); `ENOSPC` → `StorageError` "disk full" with
  buffer retained and no `.log.tmp` left; recovery after space
  freed incl. reopen; non-ENOSPC `OSError` still maps to
  `StorageError`; previously-flushed data survives while pending
  data stays buffered.
- Existing `test_edge_storage.py` re-run green.
- `ruff check` clean.
