# Slice 152 — llama.cpp adapter

## Skald (what already existed)
- `hugrgate/backends/llm.py` (slice 35): `LlamaCppEngine` with the legacy
  `LLMEngine.generate(prompt, choices, max_tokens, timeout_s)` signature.
  Eager model load at construction (required the `.gguf` file to exist
  just to build the object), no grammar support, no embed/tokenize, no
  lifecycle, `n_ctx` default 2048, no `top_p`/`seed` knobs.

## Rúnhild (design)
Per the Anti-Checkbox Rule: no duplicate engine. The canonical adapter
is now `hugrgate/runtimes/llama_cpp.py::LlamaCppRuntime` implementing the
v2 `LocalRuntime` contract; `backends.llm.LlamaCppEngine` becomes a thin
legacy-compat subclass (same constructor, same `LLMChoice` return) so
`LLMBackend(engine=LlamaCppEngine(...))` keeps working and gains lazy
loading, GBNF grammar passthrough, timeouts, embed/tokenize, and
`close()` for free. New layering law: `hugrgate.runtimes` sits below
`hugrgate.backends` (pinned both directions in
`tests/test_dependency_rules.py`).

## Eldra (what was built)
- `hugrgate/runtimes/llama_cpp.py` (new): `LlamaCppRuntime` — lazy
  `llama_cpp` import, lazy model load, `generate` (temperature/top_p/
  stop/seed/grammar/logprobs-confidence), `embed` (embedding-mode
  instances), `tokenize`, `warmup`, honest `health`
  (ok/degraded/unavailable), idempotent `close`; GGUF-only `load()`.
- `hugrgate/backends/llm.py`: `LlamaCppEngine` re-based on
  `LlamaCppRuntime`; module docstring updated; public names unchanged.
- `tests/test_dependency_rules.py`: `BACKEND_ALLOWED` gains the
  runtimes layer + `_is_runtime()` helper + reverse-direction pin test.
- `tests/test_localrt_152_llamacpp.py` (new, 20 tests, fake engine).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_152_llamacpp.py tests/test_ladder.py
tests/test_dependency_rules.py -q` → all passed (incl. legacy
`LLMBackend`+`MockEngine` paths). `ruff` clean, `mypy` clean on
`touched` modules (full gate in slice 175).

## Védis (integration)
- Backward compatible: `LlamaCppEngine(model_path, n_ctx, temperature)`
  signature and `LLMChoice` returns preserved; `available()` still
  callable. One honest metadata change: `LLMBackend.capabilities()`
  now reports `"engine": "llama-cpp"` instead of `"llm-engine"`.
- Construction no longer requires the model file to exist (lazy load);
  a missing file now surfaces as `BackendUnavailable` at first
  inference — an improvement, documented here.

## Scribe
Commit `feat(gjallarbu-152): llama.cpp adapter` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Against a real `llama-cpp-python` install + GGUF file: generate,
  grammar passthrough, embedding mode, `n_gpu_layers` offload.
- `logprobs=2` kwarg accepted by installed llama-cpp-python version.
