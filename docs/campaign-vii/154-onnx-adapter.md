# Slice 154 — ONNX Runtime adapter

## Skald (what already existed)
- `pyproject.toml` had an `onnx = ["onnxruntime>=1.16"]` extra with a
  `RESERVED_EXTRAS` note in `tests/test_dependency_rules.py`: "reserved
  for a future ONNX backend". No ONNX code existed.

## Rúnhild (design)
`hugrgate/runtimes/onnx.py::OnnxRuntime`: honest, bounded scope. A
generic adapter cannot run autoregressive generation loops without
model-specific I/O handling, so `generate` raises `BackendError`
pointing at generate-capable runtimes instead of pretending. `embed`
and `classify` serve single-output graphs with auto-detected (or
explicit) input/output names; text reaches the graph through an
injected `encode_fn` (e.g. a HF tokenizer call) so the adapter never
smuggles in an undeclared tokenizer dependency. Pure-python `softmax`
(no numpy required). The `onnx` extra reservation is retired — this
slice is the future it waited for.

## Eldra (what was built)
- `hugrgate/runtimes/onnx.py` (new): `OnnxRuntime`, `softmax`,
  lazy `onnxruntime` import, provider validation, session options,
  idempotent load/unload/close, honest health.
- `tests/test_dependency_rules.py`: `RESERVED_EXTRAS` retired.
- `tests/test_localrt_154_onnx.py` (new, 21 tests, fake session).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_154_onnx.py tests/test_dependency_rules.py
-q` → all passed. `ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; no existing runtime/backend changed.
- `pip install 'hugrgate[onnx]'` now has a real importer, satisfying
  the dependency-coverage gate without a reservation.

## Scribe
Commit `feat(gjallarbu-154): onnx runtime adapter` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Against real `onnxruntime` + a MiniLM `.onnx` graph: embed path with
  a real tokenizer `encode_fn`; classifier graph with matching label
  count; CUDAExecutionProvider availability check.
