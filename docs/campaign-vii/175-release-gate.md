# Slice 175 — Local Model Fabric release gate

## Skald (what already existed)
- Slices 151–174: the full fabric, each committed with its own
  tests and docs — but never reviewed as a whole against the repo's
  gates.

## Rúnhild (design)
The release gate: (1) full suite green; (2) regenerate the
machine-checked docs (`manifest.json` via `tools/audit_repo.py`,
`architecture-map.md` via `tools/gen_arch_map.py`,
`003-public-api-inventory.md` via `tools/gen_api_inventory.py`);
(3) review all 25 slices for gaps, duplication, stubs, and docs
drift — fixing what the gate owns, recording the rest; (4) write
`docs/campaign-vii/CAMPAIGN-VII-COMPLETION-REPORT.md`; (5) push.

## Eldra (what was built / fixed)
Release-gate fixes (all in this commit unless noted):
- `LlamaCppRuntime.warmup()` no-op with no model (contract
  conformance, caught by slice 173's suite).
- `StructuredRuntime.generate_structured`: grammar+schema conflict
  now `SpecError` (same policy as slice 165) + regression test.
- `probe.probe_runtime` → `probe_capabilities` (name collided with
  `health_probes.probe_runtime`).
- `GGUFError` moved into `hugrgate.errors` taxonomy (code
  `gguf_error`, recoverable); re-exported from `hugrgate` and
  `gguf.py`; registered in `test_errors.py`, package snapshots,
  `CHANGELOG.md`.
- `ollama.py`: `_http_error` helper → explicit `BackendError`
  raise; `HugrTimeoutError` alias → direct `TimeoutError` import
  (builtin timeouts caught via `builtins.TimeoutError`).
- `probe.py`: `_SkipProbe` control-flow exception replaced by a
  capability pre-check in the probe loop.
- `pyproject.toml`: `hugrgate[onnx]` now provides the `onnx`
  distribution (the metadata scanner imports it); provider entry
  added to `test_dependency_rules.py`; `resource`, `concurrent`,
  `types`, `builtins` recognized as stdlib.
- `tools/gen_api_inventory.py`: deterministic constant reprs
  (was embedding memory addresses / set order).
- `tools/gen_arch_map.py`: new `local-runtimes` layer.
- `ResidencyManager.release()` warm-cache semantics (designed in
  171, folded into 170's commit).
- `CHANGELOG.md`: Campaign VII entry.

## Sólrún (tests)
Full suite: **944 passed, 0 failed**. `ruff` clean (hugrgate,
tools, tests). `mypy` clean (66 files). Benchmark artifact
regenerated after the final test run (18 rows, full rounds).

## Védis (integration)
- All machine-checked docs regenerated; taxonomy doc covers all 24
  campaign test modules; changelog updated.

## Scribe
Commit `feat(gjallarbu-175): local model fabric release gate` on
`gjallarbu/campaign-vii`; push to origin (no merge — coordinator
merges).

## Real-world validation still needed
See `CAMPAIGN-VII-COMPLETION-REPORT.md` (engine-installed hosts,
VRAM hooks, multi-process residency, pack id verification).
