# Slice 173 — Local runtime conformance tests

## Skald (what already existed)
- Each adapter (slices 152–159) had its own unit tests; nothing
  verified all eight against the shared v2 contract in one place.

## Rúnhild (design)
`hugrgate/runtimes/conformance.py`: a conformance suite run with
injected fakes — no engines, models, or network. Per adapter:
`available-bool`, `construct-default`, `info-wellformed` (known
capabilities, tuple devices/formats), `health-safe`,
`hooks-safe` (`unload`/`warmup`/`close`), `errors-honest`
(missing engines surface as `HugrGateError`, never foreign
exceptions), `privacy-local` (`remote=False`), plus a `happy-path`
inference for llama.cpp / Ollama / transformers (generate) and
ONNX (embed) via duck-typed fakes. `run_conformance()` covers all 8
adapters and asserts name uniqueness;
`conformance_summary()` aggregates counts;
`register_all_adapters()` builds a smoke-test registry.
`tests/test_localrt_173_conformance.py` runs the suite inside the
normal test run so contract drift fails CI.

## Eldra (what was built)
- `hugrgate/runtimes/conformance.py` (new).
- `hugrgate/runtimes/llama_cpp.py`: **bug fix** — the suite caught
  `warmup()` raising `BackendUnavailable` with no model loaded,
  while every sibling adapter (ollama, transformers, onnx) treats
  warmup-with-nothing-loaded as a no-op. `warmup()` now returns
  early when `self._model is None`, matching the contract's
  no-op-hook spirit. (Slice-152 tests still green.)
- `tests/test_localrt_173_conformance.py` (new, 6 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_173_conformance.py -q` → 6 passed;
slice-152 suite re-run → still green. `ruff` clean, `mypy` clean.

## Védis (integration)
- Additive except the one-line warmup fix, which aligns llama.cpp
  with the documented hook contract. `register_all_adapters`
  feeds the slice-174 benchmark matrix.

## Scribe
Commit `feat(gjallarbu-173): local runtime conformance tests` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Re-run conformance on hosts where engines *are* installed
  (availability paths, real happy-path inference).
