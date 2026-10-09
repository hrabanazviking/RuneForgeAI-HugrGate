# Slice 168 — Local classifier model pack

## Skald (what already existed)
- Slices 166–167's pack registry with NLI and embedding kinds; no
  classifier choices.

## Rúnhild (design)
Two classifier packs join `CLASSIFIER_PACKS`:
twitter-roberta-base-sentiment-latest (default; positive/neutral/
negative) and roberta-base-go_emotions (27 emotions + neutral, 28
labels recorded on the pack). Both are `text-classification`
transformers packs; `runtime_for_pack` serves them unchanged. The
pack `labels` tuple lets callers sanity-check a model's output space
against the pack's documented labels.

## Eldra (what was built)
- `hugrgate/runtimes/packs.py`: `KIND_CLASSIFIER`,
  `CLASSIFIER_PACKS`, registry entries; `__all__` updated; module
  docstring finalized.
- `tests/test_localrt_168_classifier_packs.py` (new, 9 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_166_nli_packs.py
tests/test_localrt_167_embedding_packs.py
tests/test_localrt_168_classifier_packs.py -q` → 31 passed.
`ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Registry now complete for all three kinds; NLI/embedding slices
  still green.

## Scribe
Commit `feat(gjallarbu-168): local classifier model pack` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- HF ids resolve and `text-classification` pipelines build for each
  pack id; label order matches the pack's `labels` tuple.
