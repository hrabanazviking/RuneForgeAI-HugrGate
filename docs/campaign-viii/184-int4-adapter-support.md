# Slice 184 — INT4 adapter support

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_quant.py` (33 tests, green — 7 new)

## What existed before

Slice 182's `Int4Adapter` only packed 1-D vectors, had no
serialization, and leaked `KeyError`/`ValueError` on malformed blobs —
not an adapter boundary, a sketch.

## What was built

Hardened `Int4Adapter` in `hugrgate/edge/quant.py`:

- **N-D tensors**: groups along the last axis with zero-padding when
  the axis isn't a multiple of `group_size`; shape-preserving
  pack/unpack for arbitrary ranks.
- **Strict input validation**: rejects empty tensors and NaN/Inf
  (poisoned weights must never be silently packed); rejects odd or
  non-positive `group_size`.
- **Strict blob validation** (`_validate_blob`): non-dict blobs,
  missing keys, group-size mismatch, negative dims, and truncated
  buffers all raise `QuantError` with precise messages; over-long
  blobs are tolerated by slicing the exact needed prefix.
- **Serialization**: `to_bytes()`/`from_bytes()` with `HGQ40001`
  magic, rank, dims, and length pre-checks — truncated or
  wrong-magic bytes raise `QuantError`.
- **Storage accounting**: `packed_bytes(length)` (nibbles) and
  `storage_bytes(shape)` (nibbles + fp64 scales) give exact byte
  figures for the residency planner (slice 189).
- Error bound pinned by test: round-trip max error ≤ half a per-group
  bin; determinism pinned.

## Integration

- Same module/layer as slices 182–183; no map changes needed.
  `storage_bytes()` feeds slice 189's residency budgets.

## Validation notes (Execution Law rule 13)

Simulated packing math, not a hardware int4 kernel (e.g. no
weight-only-quantized matmul microkernel). Kernel behavior and the
`quality_delta_pp` planning figure need on-device measurement.

## Verification

- `pytest tests/test_edge_quant.py` — 33 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
