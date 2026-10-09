# Slice 185 — NPU capability abstraction

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_npu.py` (14 tests, green)

## What existed before

No accelerator concept in HugrGate — backends were CPU-shaped, and
there was no boundary where a Hailo, Jetson, or OpenVINO NPU could
plug in.

## What was built

`hugrgate/edge/npu.py`:

- **`NPUCapability`** — frozen record: vendor, device, INT8 TOPS,
  precisions (validated against a known set), optional power/drive;
  `supports(precision)`; JSON-serializable.
- **`NPUAdapter`** (ABC) — the vendor boundary contract:
  - `detect()` returns a capability or `None`; **never raises for
    missing hardware/driver** — absence is data, not an error;
  - `load_model()` / `infer()` raise `NPUError` when unavailable;
  - SDK imports are lazy inside methods, never at module top, so
    `import hugrgate.edge.npu` needs no vendor SDK installed;
  - `require_available()` raises a `NEEDS_HARDWARE_VALIDATION`-noted
    `NPUError` naming the missing device.
- **`MockNPUAdapter`** — deterministic in-memory twin (scripted
  presence, canned load/infer with call counting) so all
  routing/selection logic is testable without silicon.
- **`NPURegistry`** — register/get with duplicate protection,
  `detect_all()` (skips absent devices), `best_for(precision,
  min_tops)` highest-TOPS selection.

## Integration

- New module in the `edge` layer; maps + inventory regenerated; gate
  tests green. Slices 186–188 implement the Hailo, Jetson, and
  OpenVINO adapters against this ABC.

## Validation notes (Execution Law rule 13)

Every real detection path is stubbed to absence here; vendor TOPS and
precision claims are vendor-declared figures. All three vendor
adapters require on-device validation.

## Verification

- `pytest tests/test_edge_npu.py` — 14 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
- `pytest tests/test_api_inventory.py tests/test_arch_map.py` — 15 passed
