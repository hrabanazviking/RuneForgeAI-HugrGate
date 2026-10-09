# Slice 167 — Local embedding model pack

## Skald (what already existed)
- Slice 166's pack registry machinery (`ModelPack`,
  `packs_for`/`get_pack`/`default_pack`/`find_packs`,
  `runtime_for_pack`, `describe_packs`) with only the NLI kind.
- `backends/embedding.py` ships a `HashEmbedder` (offline) but no
  neural embedding choice.

## Rúnhild (design)
Per the Anti-Checkbox Rule: extend the registry, don't duplicate it.
Four embedding packs join `EMBEDDING_PACKS`: all-MiniLM-L6-v2
(default, 384d), bge-small-en-v1.5 (384d), e5-small-v2 (384d, with
`query:`/`passage:` prefix hints in `extra`), nomic-embed-text-v1.5
(768d, long context). All are `feature-extraction` transformers
packs; `runtime_for_pack` builds them with no new code paths.

## Eldra (what was built)
- `hugrgate/runtimes/packs.py`: `KIND_EMBEDDING`, `EMBEDDING_PACKS`,
  registry entries; `__all__` updated.
- `tests/test_localrt_167_embedding_packs.py` (new, 10 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_167_embedding_packs.py
tests/test_localrt_166_nli_packs.py -q` → 22 passed. `ruff` clean,
`mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure extension; NLI slice untouched and still green.

## Scribe
Commit `feat(gjallarbu-167): local embedding model pack` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- HF ids resolve and `feature-extraction` pipelines build for each
  pack id (network + transformers required).
