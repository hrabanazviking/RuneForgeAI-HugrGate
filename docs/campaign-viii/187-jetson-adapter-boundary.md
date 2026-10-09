# Slice 187 — Jetson adapter boundary

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_npu.py` (29 tests, green — 7 new)

## What existed before

Slice 186 added the Hailo boundary; Jetson-class boards had no
adapter.

## What was built

`JetsonAdapter` in `hugrgate/edge/npu.py`:

- **Three-stage detection**: device-tree model must name an NVIDIA
  Jetson board (else `None`); `/etc/nv_tegra_release` presence and
  TensorRT importability refine the capability. A Jetson without
  TensorRT is still *detected* (the board is real) but its notes flag
  "NPU path unavailable, CPU fallback only" — degraded, not absent.
- **Spec table** (`_JETSON_SPECS`): Orin Nano 40 TOPS / 15 W, Orin NX
  100 / 25 W, Xavier NX 21 / 20 W, AGX Xavier 32 / 30 W, Nano 0.5 /
  10 W, TX2 1.3 / 15 W; unknown Jetson boards get conservative
  1.0 TOPS rather than a guessed figure.
- **`.engine`/`.plan` enforcement** in `load_model()`; missing
  TensorRT raises instead of pretending to load.
- **Honest infer**: raises `NPUError` marked
  `NEEDS_HARDWARE_VALIDATION` — same policy as Hailo: no fake NPU
  outputs.
- All of `trt`, `model_text`, `tegra_release_present` injectable for
  branch-complete tests.

## Integration

- Same ABC/registry as slices 185–186; `best_for("int8")` correctly
  prefers the 40-TOPS Orin Nano over the 13-TOPS Hailo-8L in a mixed
  registry (test-pinned); API inventory regenerated.

## Validation notes (Execution Law rule 13)

No Jetson hardware or TensorRT here. Spec figures are vendor claims;
detection branches, engine loading, and inference all need on-device
runs.

## Verification

- `pytest tests/test_edge_npu.py` — 29 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
