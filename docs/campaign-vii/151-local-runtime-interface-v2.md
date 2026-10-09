# Slice 151 — Local runtime interface v2

## Skald (what already existed)
- `hugrgate/backends/llm.py` (slice 35): `LLMEngine` — generate-only,
  legacy signature `generate(prompt, choices, max_tokens, timeout_s)`.
  Only one engine (`LlamaCppEngine`), no embedding/classification,
  no model lifecycle, no capability advertisement.
- `hugrgate/backends/nli.py`, `embedding.py`: separate per-task backends,
  each with its own injection pattern; no shared runtime abstraction.
- No registry, no format detection, no unified health/privacy story for
  local engines.

## Rúnhild (design)
New package `hugrgate/runtimes/` with a v2 contract `LocalRuntime`:
generation + embedding + classification + tokenize, model
load/unload lifecycle, capability advertisement (`RuntimeInfo`),
unified error semantics (`BackendUnavailable` when the engine is
absent, `BackendError` for unsupported capabilities, `SpecError` for
bad inputs), and `privacy()` always reporting `remote=False`.
Optional engines stay lazily imported; `available()` is a classmethod so
callers can probe without instantiating. `FakeRuntime` gives the
conformance suite (173) and benchmark matrix (174) a deterministic,
dependency-free engine.

## Eldra (what was built)
- `hugrgate/runtimes/__init__.py` (new, ~430 lines): `LocalRuntime` ABC,
  `RuntimeRegistry`, value objects (`ModelRef`, `GenerationOptions`,
  `GenerationResult`, `EmbeddingResult`, `ClassificationResult`,
  `RuntimeInfo`), capability constants (`CAP_GENERATE/EMBED/CLASSIFY/
  GRAMMAR/JSON_SCHEMA/STREAM/TOKENIZE`), `KNOWN_FORMATS` +
  `format_from_path()`, deterministic `FakeRuntime`.
- `tests/test_localrt_151_interface.py` (new, 30 tests).
- Taxonomy doc updated (unit row).

## Sólrún (tests)
`venv/bin/python -m pytest tests/test_localrt_151_interface.py -q` → 30 passed.
`ruff check hugrgate/runtimes tests/test_localrt_151_interface.py` → clean.
`mypy hugrgate/runtimes` → clean (full-package gate run in slice 175).

## Védis (integration)
- No existing module changed (pure addition); `backends/llm.py`
  `LLMEngine` left intact — slice 152 rewires it onto the new contract
  without breaking its public signature.
- Backward compatible: nothing in the package imports `hugrgate.runtimes`
  yet, so no behavior change for existing users.

## Scribe
Commit `feat(gjallarbu-151): local runtime interface v2` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
None for the interface itself; adapter slices (152–159) must validate
each engine binding against real installations.
