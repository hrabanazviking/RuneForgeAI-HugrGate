# Slice 155 — Transformers adapter

## Skald (what already existed)
- `hugrgate/backends/nli.py` (slice 34): builds its own
  `transformers` zero-shot pipeline internally; no shared adapter.
- No generate/embed path for HF models anywhere in the repo.

## Rúnhild (design)
`hugrgate/runtimes/transformers_rt.py::TransformersRuntime`: one
pipeline task per instance (text-generation / feature-extraction /
zero-shot-classification / text-classification), capabilities derived
from the task, honest coercions (prompt-prefix stripping,
mean-pool+L2 for embeddings), cooperative timeouts documented as such,
`trust_remote_code=False` default. `as_nli_fn()` bridges a zero-shot
instance into `NLIBackend(nli_fn=...)` — the existing NLI backend gains
a runtime-backed engine without duplicating its decision logic.

## Eldra (what was built)
- `hugrgate/runtimes/transformers_rt.py` (new): `TransformersRuntime`,
  task capability sets, lazy pipeline build, NLI bridge.
- `tests/test_localrt_155_transformers.py` (new, 20 tests, fake pipe).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_155_transformers.py -q` → 20 passed.
`ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; `backends/nli.py` untouched — the bridge is opt-in
  via `NLIBackend(nli_fn=runtime.as_nli_fn())`, proven by test.
- No new dependency: uses the existing `nli` extra (`transformers`).

## Scribe
Commit `feat(gjallarbu-155): transformers adapter` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Real `transformers` + tiny model per task: generate prefix strip,
  feature-extraction pooling shapes, zero-shot score layout
  (`labels`/`scores` keys), CUDA `device=0` path.
