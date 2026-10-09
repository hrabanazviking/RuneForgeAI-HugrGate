# Slice 161 — Model metadata scanner

## Skald (what already existed)
- Slice 160's GGUF discovery (find + parse GGUF only). No coverage of
  safetensors/ONNX/HF repos, no unified metadata record.

## Rúnhild (design)
`hugrgate/runtimes/metadata.py`: `scan_model`/`scan_directory` with a
per-format strategy. GGUF reuses slice 160's parser (parameters stay an
*estimate* from size × bits-per-weight, always labeled). safetensors
gets an **exact** parameter count by summing header tensor shapes —
no estimation where exactness is available. ONNX is a shallow scan
unless the `onnx` package imports (then producer/graph IO). HF repo
dirs read `config.json` (architecture, context window, hidden
size/layers), `tokenizer_config.json`, and README frontmatter
(license/tags/languages/pipeline tag) with a tolerant hand-rolled
frontmatter parser (no new dependency). Repo-internal files are
excluded from directory scans so a repo yields one record.

## Eldra (what was built)
- `hugrgate/runtimes/metadata.py` (new): `ModelMetadata`,
  `scan_model`, `scan_directory`, per-format scanners.
- `tests/test_localrt_161_metadata.py` (new, 15 tests): genuine
  fixture artifacts (GGUF bytes, safetensors header, HF repo).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_161_metadata.py -q` → 15 passed.
`ruff` clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; consumes `format_from_path` (151) and
  `parse_gguf_header`/`FILE_TYPES` (160). Slices 162/169–171 use
  `ModelMetadata` for probing, warmup, and residency decisions.

## Scribe
Commit `feat(gjallarbu-161): model metadata scanner` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- safetensors headers from real HF downloads (huge headers —
  the 100 MB cap); ONNX deep scan with the `onnx` package;
  frontmatter edge cases (multi-line YAML values are not parsed —
  documented limitation).
