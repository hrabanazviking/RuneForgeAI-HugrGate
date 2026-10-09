# Slice 153 — Ollama-compatible adapter

## Skald (what already existed)
- Slice 151's `LocalRuntime` contract; no HTTP-based runtime yet.
- Ollama is a *server*, not a pip package: no optional import to gate
  on, so availability must be probed over HTTP.

## Rúnhild (design)
`hugrgate/runtimes/ollama.py::OllamaRuntime` speaks the Ollama HTTP API
(`/api/generate`, `/api/embed`, `/api/tags`, `/api/version`) using only
the stdlib (`urllib`) — zero new dependencies. The transport is a
``(method, path, payload) -> dict`` callable, injected in tests; the
default transport maps `HTTPError` 404 → `BackendError` with an
`ollama pull <tag>` hint (pulling is never a silent side effect of
`load()`), and `URLError`/timeouts → `BackendUnavailable`.
`available()` probes `GET /api/tags` with a 2 s timeout. Per-call
timeouts flow from `GenerationOptions.timeout_s` into the default
transport; builtin `TimeoutError` from any transport is converted to
HugrGate's `TimeoutError`.

## Eldra (what was built)
- `hugrgate/runtimes/ollama.py` (new): `OllamaRuntime`,
  `TransportFn` alias, `DEFAULT_HOST`, `list_models()`, honest
  `health()` (ok when the tag is on the server, degraded when the tag
  is missing or no model selected, unavailable when the server is
  down).
- `tests/test_localrt_153_ollama.py` (new, 21 tests, fake transport).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_153_ollama.py -q` → 21 passed. `ruff` clean,
`mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; no existing module changed. `privacy()` inherits
  `remote=False` from the base — correct, Ollama runs on localhost.
- Works against any Ollama-compatible endpoint (host configurable),
  including `vLLM --api` style servers that mimic `/api/generate`.

## Scribe
Commit `feat(gjallarbu-153): ollama-compatible adapter` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Against a live Ollama server: generate, embed, `/api/show`
  metadata (not yet surfaced), streaming (not yet supported —
  `stream` is accepted by the API but this adapter uses `stream:false`).
