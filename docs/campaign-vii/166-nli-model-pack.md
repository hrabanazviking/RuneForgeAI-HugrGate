# Slice 166 — Local NLI model pack

## Skald (what already existed)
- `NLIBackend` (slice 34) hardcodes `facebook/bart-large-mnli` as its
  default model string; no curated registry of NLI choices existed.

## Rúnhild (design)
`hugrgate/runtimes/packs.py`: the pack registry machinery
(`ModelPack`, `packs_for`/`get_pack`/`default_pack`/`find_packs`,
`runtime_for_pack`, `describe_packs`) plus the NLI kind: three
zero-shot entailment models (bart-large-mnli default,
deberta-v3-large-mnli, nli-deberta-v3-small) with HF ids, tasks,
languages, licenses, and size estimates. `runtime_for_pack` builds a
`TransformersRuntime(task="zero-shot-classification")` whose
`as_nli_fn()` drops straight into `NLIBackend(nli_fn=...)` — the
documented wiring recipe, proven by test. Slices 167–168 extend the
same registry with embedding/classifier kinds.

## Eldra (what was built)
- `hugrgate/runtimes/packs.py` (new): registry machinery + NLI_PACKS.
- `tests/test_localrt_166_nli_packs.py` (new, 12 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_166_nli_packs.py -q` → 12 passed.
`ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; `backends/nli.py` untouched — wiring is opt-in via
  the `as_nli_fn` recipe.

## Scribe
Commit `feat(gjallarbu-166): local nli model pack` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- HF ids resolve and `zero-shot-classification` pipelines build for
  each pack id (network + transformers required).
