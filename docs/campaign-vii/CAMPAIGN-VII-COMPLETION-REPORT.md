# Campaign VII — Local Model Fabric: Completion Report

**Branch:** `gjallarbu/campaign-vii` · **Slices:** 151–175 (25 slices)
**Worker:** Yrsa Freydisdottir · **Status:** complete, all gates green

## What was built

A complete local-model serving fabric under `hugrgate/runtimes/` —
22 modules, one layer below `hugrgate/backends` (pinned both
directions by `test_dependency_rules.py`):

| Slice | Artifact |
|---|---|
| 151 | `runtimes/__init__.py` — `LocalRuntime` ABC v2, `RuntimeRegistry`, `ModelRef`, `GenerationOptions/Result`, capability constants, deterministic `FakeRuntime` |
| 152 | `llama_cpp.py` — llama.cpp adapter; `backends/llm.py::LlamaCppEngine` re-based as legacy-compat subclass |
| 153 | `ollama.py` — Ollama adapter (stdlib `urllib`, injectable transport) |
| 154 | `onnx.py` — ONNX Runtime adapter (embed/classify; honest generate refusal) |
| 155 | `transformers_rt.py` — Transformers adapter + `as_nli_fn()` bridge into `NLIBackend` |
| 156 | `vllm.py` — vLLM server mode + in-process |
| 157 | `mlx.py` — Apple-silicon boundary (platform gate, injectable) |
| 158 | `openvino.py` — OpenVINO adapter |
| 159 | `tensorrt.py` — TensorRT boundary (CUDA gate, explicit IO names) |
| 160 | `gguf.py` — pure-python GGUF v3 header parser |
| 161 | `metadata.py` — model metadata scanner (GGUF/safetensors/ONNX/HF-repo) |
| 162 | `probe.py` — capability probing (`probe_capabilities`; skips vs failures) |
| 163 | `structured.py` — `extract_json`, `validate`, retrying `StructuredRuntime` |
| 164 | `grammar.py` — `Grammar` builders, GBNF validation, `GrammarConstrainedRuntime` |
| 165 | `jsonschema.py` — JSON-Schema→GBNF compiler, `JsonSchemaConstrainedRuntime` |
| 166–168 | `packs.py` — curated NLI / embedding / classifier model packs |
| 169 | `warmup.py` — `WarmupManager` (idempotent, latency baselines, legacy `Backend` support) |
| 170 | `residency.py` — ref-counted residency table with leases (warm-cache semantics) |
| 171 | `eviction.py` — LRU / TTL / memory-pressure / composite eviction policies + `Evictor` |
| 172 | `health_probes.py` — liveness / model-loaded / inference / latency probe battery |
| 173 | `conformance.py` — contract suite over all 8 adapters (runs in CI) |
| 174 | `bench_matrix.py` — measured latency matrix → `benchmarks/localrt-matrix.json` |
| 175 | this release gate |

## Verification

- **Tests:** 410 across 24 `tests/test_localrt_15X/16X/17X_*.py`
  modules (all registered in
  `docs/campaign-i/023-test-taxonomy-rebuild.md`); full suite
  **944 passed, 0 failed**.
- **Gates green:** `ruff` (F,E4,E7,E9,I,UP,B,RUF,BLE001) over
  hugrgate/tools/tests; `mypy` over `hugrgate` (66 files);
  `test_taxonomy`, `test_dependency_rules` (incl. the new
  runtimes-below-backends layering law), `test_api_inventory`,
  `test_arch_map`, `test_repo_truth`, `test_errors`.
- **Docs:** `docs/campaign-vii/151-…-174-*.md` per slice plus this
  report; regenerated `docs/campaign-i/manifest.json`,
  `architecture-map.md` (new `local-runtimes` layer),
  `003-public-api-inventory.md`.
- **Benchmark artifact:** `benchmarks/localrt-matrix.json` — 18
  measured rows at full rounds; honestly labeled synthetic baseline
  (only `FakeRuntime` rows have timings; engine rows are `ok:false`
  — no engines in CI).

## Issues found and fixed during the release gate

1. **`warmup()` hook inconsistency (173):** conformance caught
   `LlamaCppRuntime.warmup()` raising `BackendUnavailable` with no
   model loaded, while ollama/transformers/onnx treat it as a no-op.
   Fixed the adapter to match the contract.
2. **Grammar/JSON-schema exclusivity (165, 175):**
   `GenerationOptions` forbids setting both `grammar` and
   `json_schema`. `JsonSchemaConstrainedRuntime` and
   `StructuredRuntime.generate_structured` both violated this;
   fixed to carry the schema separately and raise `SpecError` on
   conflict (consistent policy, regression-tested).
3. **Unload-on-zero vs warm cache (171):** writing the eviction
   policy exposed that unloading at refcount zero left nothing to
   evict. `ResidencyManager.release()` now keeps models warm;
   only `evict()` unloads (folded back into slice 170's commit).
4. **`probe_runtime` name collision (175):** `probe.py` and
   `health_probes.py` exported the same name. Capability probing
   renamed to `probe_capabilities`.
5. **Error taxonomy (175):** `GGUFError` was a bare `Exception` →
   moved into `hugrgate.errors` (code `gguf_error`, recoverable),
   re-exported from `gguf.py` and the package root, registered in
   `test_errors.py`. `ollama.py`'s `_http_error` helper and
   `HugrTimeoutError` alias violated the raise-site rule →
   restructured to raise taxonomy names directly
   (`BackendError`, `TimeoutError`; builtin timeouts caught via
   `builtins.TimeoutError`). `probe.py`'s `_SkipProbe`
   control-flow exception → capability pre-check in the loop.
6. **Dependency declarations (175):** `resource`, `concurrent`,
   `types`, `builtins` added to `_STDLIB`; `onnx` provider entry
   added and the `onnx` extra now actually provides the `onnx`
   distribution (`metadata.py` deep-scan imports it and tells
   users to install `hugrgate[onnx]`).
7. **Generator determinism (175):** `gen_api_inventory.py` embedded
   memory addresses and unordered set reprs → stable repr for
   constants. `gen_arch_map.py` gained the `local-runtimes` layer.

## Known limitations / real-world validation still needed

- No engines installed in CI: adapter happy-paths verified only via
  injected fakes. Re-run conformance + benchmark matrix on hosts
  with llama.cpp / Ollama / transformers / onnxruntime / vLLM /
  MLX / OpenVINO / TensorRT installed.
- `MemoryPressurePolicy` defaults to process RSS; real VRAM
  accounting needs a provider hook (NVML / `torch.cuda`).
- `ResidencyManager` locking is per-process; multi-process serving
  needs an external lock.
- Model-pack HF ids are curated recommendations, not verified
  downloads; label order for classifier packs should be checked
  against the real model configs.
- Parallel `warmup_all` thread-safety of `load()` on real GPU
  engines is untested.

## Commits (25)

`369a40b` (151) … `30826dd` (174), plus the 175 release-gate
commit. No force-pushes; branch `gjallarbu/campaign-vii` pushed to
origin, **not merged** — the coordinator merges.
