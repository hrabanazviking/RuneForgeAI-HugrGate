# Slice 186 — Hailo adapter boundary

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_npu.py` (22 tests, green — 8 new)

## What existed before

Slice 185 defined the `NPUAdapter` ABC and a mock twin; no vendor
adapter existed.

## What was built

`HailoAdapter` in `hugrgate/edge/npu.py`:

- **Two-stage detection**: the HailoRT SDK must import *and* a Hailo
  PCI device (vendor `0x1e60`) must be enumerable via sysfs — either
  missing returns `None` (absent, not broken). `sdk` and
  `pci_vendor_ids` are injectable so every branch is testable without
  hardware or the SDK.
- **Device distinction**: `scan_devices()` results map `Hailo-8` →
  26 TOPS vs the conservative `Hailo-8L` → 13 TOPS default (a
  too-clever substring match that misclassified "Hailo-8" was caught
  by tests and replaced with exact matching).
- **`.hef` enforcement**: `load_model()` rejects non-HEF paths with
  `NPUError` naming the Hailo Executable Format requirement.
- **Honest infer**: without the on-device HailoRT runtime, `infer()`
  raises `NPUError` marked `NEEDS_HARDWARE_VALIDATION` rather than
  faking outputs — a fake NPU result would be worse than none.
- Capability advertises `int8`-only precision and 2.5 W, both flagged
  as vendor figures.

## Integration

- Registered against the slice-185 ABC; `NPURegistry.detect_all()`
  picks it up; API inventory regenerated.

## Validation notes (Execution Law rule 13)

No Hailo hardware or SDK here. Detection logic, PCI IDs, TOPS/power
figures, and the entire infer path require on-device validation.

## Verification

- `pytest tests/test_edge_npu.py` — 22 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
