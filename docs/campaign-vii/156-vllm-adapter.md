# Slice 156 — vLLM local adapter

## Skald (what already existed)
- No vLLM support. The Ollama adapter (153) established the
  stdlib-HTTP-to-a-server pattern; vLLM's OpenAI-compatible server
  fits the same shape.

## Rúnhild (design)
`hugrgate/runtimes/vllm.py::VLLMRuntime` with two honest modes:
**server mode** (default) speaks `POST /v1/completions` /
`/v1/embeddings` / `GET /v1/models` with stdlib `urllib` — no vLLM
install in this process; **in-process mode** drives an injected
`vllm.LLM`-compatible object, or builds one via
`VLLMRuntime.in_process(...)` which lazily imports `vllm` (new
`vllm` extra in pyproject, provider entry in the dependency gate).
`available()` is true when the import works *or* a server answers.
In-process embedding is refused with a pointer to `--task embed`
server mode instead of pretending.

## Eldra (what was built)
- `hugrgate/runtimes/vllm.py` (new): `VLLMRuntime`, `in_process`
  builder, OpenAI-protocol mapping, honest health (ok only when the
  model id is actually served).
- `pyproject.toml`: new `vllm = ["vllm>=0.4"]` extra.
- `tests/test_dependency_rules.py`: `THIRD_PARTY_PROVIDERS["vllm"]`.
- `tests/test_localrt_156_vllm.py` (new, 24 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_156_vllm.py tests/test_dependency_rules.py
-q` → all passed. `ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition. The extra is consumed by a real importer, so the
  dependency gate stays satisfied.

## Scribe
Commit `feat(gjallarbu-156): vllm local adapter` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Against `vllm serve`: completions payload shape, usage counts,
  `/v1/models` id matching, `--task embed` server embeddings.
- In-process: `vllm.LLM` + `SamplingParams` kwargs against installed
  vLLM version (API drift is the risk).
