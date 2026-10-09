# Slice 182 — Quantized-model profiles

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_quant.py` (16 tests, green)

## What existed before

No quantization concept anywhere in HugrGate — no way to express
"this model also ships as int8" or to choose a numeric format from a
device budget.

## What was built

`hugrgate/edge/quant.py` (planning side; execution paths land in 183/184):

- **`QuantFormat`** — `fp32 | fp16 | int8 | int4`.
- **`QuantProfile`** — frozen record: name, format, `size_factor`,
  `latency_factor` (relative to fp32), informational `quality_delta_pp`,
  `min_ram_mb`; validated ranges; `to_dict()` flags
  `"planning_estimate": True`.
- **`QUANT_PROFILES`** — five canonical profiles (fp32, fp16, int8,
  int8-mixed, int4) with conservative factors.
- **`QuantProfileRegistry`** — register/get/list with duplicate
  protection (`replace=True` to override), unknown-name errors that
  list known profiles.
- **`estimate(profile, base_size_mb, base_latency_ms)`** — scales an
  fp32 reference measurement by profile factors.
- **`select_profile(registry, ram_budget_mb, latency_budget_ms, ...)`**
  — picks the smallest (or fastest) profile fitting both budgets *and*
  the profile's `min_ram_mb` (runtime overhead beyond weights);
  raises `QuantError` when nothing fits instead of silently degrading.
- Execution-path scaffolding also present (hardened in 183/184):
  affine `quantize_int8`/`dequantize_int8` and groupwise `Int4Adapter`
  nibble packing — real numpy math, deterministic, with round-trip
  error bounds.

## Integration

- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended. Slice 189 (model residency) will use
  `select_profile` when pinning models under a RAM budget.

## Validation notes (Execution Law rule 13)

All factors are planning estimates for transformer-ish decoders on
ARM64, not measurements. Per-model quality/latency calibration on
target silicon is required before production use.

## Verification

- `pytest tests/test_edge_quant.py` — 16 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
