# Slice 158 — OpenVINO adapter

## Skald (what already existed)
- Slice 154's ONNX adapter established the graph-adapter shape
  (embed/classify, `encode_fn`, auto-detected IO names). OpenVINO IR
  (`.xml` + `.bin`) fits the same shape with a different compile call.

## Rúnhild (design)
`hugrgate/runtimes/openvino.py::OpenVINORuntime`: mirrors the ONNX
adapter's honest scope (embed/classify only; `generate` refused with a
pointer to generate-capable runtimes). Reuses `softmax`/`EncodeFn`
from `hugrgate.runtimes.onnx` (no duplication — runtimes-layer
sharing is legal per the layering tests). Device string (`CPU`/`GPU`/
`AUTO`) and `NUM_STREAMS` pass straight to `Core.compile_model`;
compiled-model `__call__(feed) -> {name: values}` duck-typed for
injection. New `openvino` extra in pyproject + provider entry.

## Eldra (what was built)
- `hugrgate/runtimes/openvino.py` (new): `OpenVINORuntime`.
- `pyproject.toml`: `openvino = ["openvino>=2023.0"]` extra.
- `tests/test_dependency_rules.py`: `THIRD_PARTY_PROVIDERS["openvino"]`.
- `tests/test_localrt_158_openvino.py` (new, 17 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_158_openvino.py tests/test_dependency_rules.py
-q` → all passed. `ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; shares `softmax`/`EncodeFn` with the ONNX adapter.

## Scribe
Commit `feat(gjallarbu-158): openvino adapter` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Real `openvino` + IR model: `compile_model` device/config kwargs,
  `compiled(feed)` dict-return convention, `get_any_name()` port
  naming across openvino versions.
