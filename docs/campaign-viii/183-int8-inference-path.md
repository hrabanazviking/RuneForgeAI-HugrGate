# Slice 183 — INT8 inference path

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_quant.py` (26 tests, green — 10 new)

## What existed before

Slice 182 scaffolded per-tensor affine INT8 quantization. The path
was thin: no per-channel mode, no symmetric mode, no serializable
container, no simulated inference op, and truncated blobs leaked raw
`ValueError`s.

## What was built

Hardened `hugrgate/edge/quant.py` INT8 execution path:

- **`quantize_int8(weights, *, symmetric=False, axis=None)`** — now
  returns `(codes, scales, zero_points)` arrays; per-channel
  quantization along an axis (proven by test to rescue small channels
  drowned by large ones: small-channel error drops >100x); symmetric
  mode pins zero-point to 0; rejects NaN/Inf/empty inputs with
  `QuantError`; constant tensors take the degenerate scale=1.0 path;
  fully deterministic.
- **`dequantize_int8`** — inverts both per-tensor and per-channel
  forms via broadcasting.
- **`QuantizedTensor`** — frozen, serializable container (int8 codes
  + scales + zero-points + shape + provenance flags) with a compact
  little-endian `to_bytes()`/`from_bytes()` format (`HGQT0001` magic,
  length-validated — truncated/corrupt blobs raise `QuantError`, never
  leak `struct`/`ValueError`).
- **`int8_matvec(weight_qt, x, bias=None)`** — the honest simulated
  inference op: `y = dequant(W_q) @ x + b`, computed from the int8
  codes, never from the original floats; tested against a float
  reference (tracks within half a unit).

## Integration

- `__all__` completed for the star-import gate (all public quant
  names listed); inventory regenerated and `test_api_inventory.py`
  green.
- `QuantizedTensor.to_bytes()` is the persistence format slices 189
  (residency) and 191 (flash-aware storage) will store.

## Validation notes (Execution Law rule 13)

This is simulated execution (dequantize-then-multiply in float64), not
a NEON/VNNI int8 kernel — real kernels add their own accumulation
rounding. On-device kernel validation required before latency claims.

## Verification

- `pytest tests/test_edge_quant.py` — 26 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
- `pytest tests/test_api_inventory.py` — 9 passed
