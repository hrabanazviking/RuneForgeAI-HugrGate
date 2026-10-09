# Slice 191 — Flash-wear-aware storage

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_storage.py` (15 tests, green)

## What existed before

HugrGate persisted nothing itself; any edge deployment would naively
write caches, telemetry, and checkpoints straight to an SD card —
death by write amplification.

## What was built

`hugrgate/edge/storage.py` — `WearAwareStore`, a persistent
key/value store that treats flash as finite:

- **Write budget**: a lifetime byte budget; flushed bytes decrement
  it, and over-budget writes raise `StorageError` (fail closed rather
  than silently killing the card). Reopening an existing log counts
  its size as already-spent wear.
- **Coalescing buffer**: puts accumulate in RAM (default 64 KiB
  threshold) and flush as one sequential append — one erase-cycle
  hit instead of dozens (test-pinned: 50 puts → 1 flush).
- **Atomic flush**: existing log + new records → temp file → fsync →
  `os.replace`, so a power cut can never leave a torn tail (the
  foundation slice 193's recovery builds on).
- **Append-only log format** (`HGWS0001` magic, length-prefixed
  records, tombstones for deletes); index rebuilt in RAM at open;
  corrupt/truncated logs raise `StorageError`, never half-load.
- **`compact()`** rewrites only live keys, returning bytes written.
- **Wear telemetry**: `wear_stats()` reports bytes written, payload
  bytes, write amplification (`bytes_written / payload_bytes`),
  flush count, and budget remaining — JSON-serializable.

## Integration

- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended. Slices 192 (bootstrap state) and 193
  (checkpoints) will persist through this store.

## Validation notes (Execution Law rule 13)

Budget figures (lifetime bytes) must be set from the flash
datasheet/endurance rating per deployment — the store enforces
whatever it's told. fsync semantics verified on this host's
filesystem only.

## Verification

- `pytest tests/test_edge_storage.py` — 15 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
