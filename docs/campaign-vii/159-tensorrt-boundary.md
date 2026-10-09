# Slice 159 — TensorRT adapter boundary

## Skald (what already existed)
- Graph-adapter shape from slices 154/158. TensorRT differs in two
  ways: it needs an NVIDIA CUDA GPU (hard boundary, like MLX's Apple
  boundary) and its engines demand *explicit* IO names (no
  auto-detection — TensorRT engines should name their tensors).

## Rúnhild (design)
`hugrgate/runtimes/tensorrt.py::TensorRTRuntime`: `cuda_available()`
with injectable override (torch → nvidia-smi fallback chain for real
detection); `available()` = CUDA AND importable `tensorrt`.
`_ensure_engine()` deserializes `.engine`/`.plan` via `trt.Runtime`
for real. Execution goes through an injectable `ExecutorFn`;
`default_trt_executor` is genuine buffer management (struct-packed
host buffers, `memcpy_htod`/`dtoh`, `execute_v2`, explicit cleanup)
written against the TensorRT/pycuda APIs with stdlib-only dtype
mapping — real code awaiting GPU validation (rule 13), exercised in
tests only through injected fakes plus the pure-python
`_flatten`/`_unflatten` helpers.

## Eldra (what was built)
- `hugrgate/runtimes/tensorrt.py` (new): `TensorRTRuntime`,
  `default_trt_executor`, CUDA boundary detection.
- `pyproject.toml`: `tensorrt = ["tensorrt>=8.6", "pycuda>=2023.1"]`.
- `tests/test_dependency_rules.py`: provider entries for `tensorrt`
  and `pycuda`.
- `tests/test_localrt_159_tensorrt.py` (new, 22 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_159_tensorrt.py tests/test_dependency_rules.py
-q` → all passed. `ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; reuses `softmax`/`EncodeFn` from the ONNX adapter.

## Scribe
Commit `feat(gjallarbu-159): tensorrt adapter boundary` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- On an NVIDIA-GPU machine: `cuda_available()` true path,
  `trt.Runtime.deserialize_cuda_engine` on a real `.engine`,
  `default_trt_executor` buffer shapes/dtypes/`execute_v2` against
  installed tensorrt+pycuda versions (API drift is the risk).
