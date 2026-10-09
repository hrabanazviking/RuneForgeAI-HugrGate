# Slice 188 — OpenVINO NPU path

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_npu.py` (36 tests, green — 7 new)

## What existed before

Slices 185–187 built the NPU ABC plus Hailo and Jetson boundaries;
Intel NPUs (Core Ultra etc. via OpenVINO) had no path.

## What was built

`OpenVINOAdapter` in `hugrgate/edge/npu.py`:

- **Detection**: `openvino` must import and `Core().available_devices`
  must list an `NPU*` device — either missing returns `None`. A core
  whose device query raises is treated as absent (detection must not
  raise), covered by `test_openvino_broken_core_reports_absent`.
- **Capability**: first NPU device name, conservative 10.0 INT8 TOPS
  planning figure, `int8`/`fp16` precisions, power left `None`
  (unknown rather than invented), all flagged
  `NEEDS_HARDWARE_VALIDATION`.
- **IR enforcement**: `load_model()` requires `.xml` (OpenVINO IR =
  `.xml` + `.bin`).
- **Honest infer**: raises `NPUError` marked
  `NEEDS_HARDWARE_VALIDATION`, same policy as Hailo/Jetson.
- Injected `core` stands in for `openvino.Core()` in tests.

## Integration

- Fourth adapter on the slice-185 ABC; `NPURegistry.best_for`
  ordering across all four vendors pinned by test (Hailo-8L 13 TOPS
  beats the conservative OpenVINO 10); inventory regenerated.

## Validation notes (Execution Law rule 13)

No OpenVINO runtime or Intel NPU here. TOPS figure, device naming,
and inference all require on-device runs.

## Verification

- `pytest tests/test_edge_npu.py` — 36 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
