# Slice 163 — Structured-output adapter

## Skald (what already existed)
- No structured-output path. `LLMBackend` constrains to spec tokens
  but returns plain strings; nothing extracts or validates JSON.

## Rúnhild (design)
`hugrgate/runtimes/structured.py`: three layers. `extract_json`
pulls JSON from plain/fenced/embedded model text (string-aware
balanced-span scan). `validate` is a dependency-free JSON-schema
subset validator — enforced keywords documented, ignored keywords
(`title`, `description`, ...) *reported* rather than silently
dropped. `StructuredRuntime` wraps any inner runtime: generate →
extract → validate → re-prompt with the errors (up to `max_retries`)
→ `BackendError` on persistent failure. It also forwards
`json_schema` through `GenerationOptions` so grammar-capable inner
runtimes (slice 165) can constrain natively. Delegates
embed/classify/tokenize/lifecycle/health/privacy to inner.

## Eldra (what was built)
- `hugrgate/runtimes/structured.py` (new): `extract_json`,
  `validate` (+ `$ref`), `StructuredRuntime`.
- `tests/test_localrt_163_structured.py` (new, 30 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_163_structured.py -q` → 30 passed.
`ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; advertises `json_schema` capability on top of the
  inner runtime's set, so negotiation (slice 36) can see it.

## Scribe
Commit `feat(gjallarbu-163): structured-output adapter` on
`gjallarbu/campaign-vii`.
