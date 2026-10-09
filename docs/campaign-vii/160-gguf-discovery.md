# Slice 160 — GGUF model discovery

## Skald (what already existed)
- No GGUF handling anywhere. `LlamaCppRuntime.load()` accepts GGUF
  paths but never inspects them; nothing discovers models on disk.

## Rúnhild (design)
`hugrgate/runtimes/gguf.py`: a pure-python GGUF v3 header parser
(magic/version/tensor-count/kv-count, all 13 value types incl. arrays,
tensor-info skipping) that reads only the header — tensor blobs are
never touched, so scanning multi-GB files is cheap. `parse_gguf_header`
raises `GGUFError` on corrupt input; `discover_gguf_models` converts
those to per-file `error` fields so one bad file never aborts a scan.
Extracted fields: architecture, name, context/embedding length,
block/head counts, `general.file_type` → quantization label (33 known
types, unknown labeled `file_type_N` never guessed).

## Eldra (what was built)
- `hugrgate/runtimes/gguf.py` (new): `parse_gguf_header`,
  `find_gguf_files`, `discover_gguf_models`, `GGUFModel`,
  `FILE_TYPES`, `gguf_model_size_human`.
- `tests/test_localrt_160_gguf.py` (new, 16 tests): a minimal GGUF
  *writer* builds genuine GGUF bytes in tmp dirs — the parser is
  tested against real bytes, including all value types, tensor-info
  skipping, bad magic, wrong version, truncation, corrupt-file
  tolerance.
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_160_gguf.py -q` → 16 passed. `ruff` clean,
`mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; `format_from_path()` (slice 151) already maps
  `.gguf` → `"gguf"`, and slice 161's metadata scanner consumes
  `parse_gguf_header` directly.

## Scribe
Commit `feat(gjallarbu-160): gguf model discovery` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Parse headers of real-world GGUF files (llama.cpp-quantized
  Llama/Qwen/Mistral) — kv key coverage, `file_type` values for
  newer quants (IQ1_M etc. mapped by guess from the llama.cpp enum;
  verify against actual files).
