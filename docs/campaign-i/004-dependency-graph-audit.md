# Slice 004 — Dependency graph audit

**Date:** 2026-10-09 · **Tooling:** `tools/gen_arch_map.py`, `tests/test_dependency_rules.py`

## External dependencies

| Import | Provided by | Status |
|---|---|---|
| `yaml` | base (`pyyaml`) | ✓ base stays minimal (only `pyyaml`) |
| `numpy` | `ml`, `bench` extras | ✓ hardened: deliberate `BackendError`/`CalibrationError` naming the `ml` extra when absent |
| `sklearn`/`scipy` | `ml` extra | ✓ hardened likewise |
| `llama_cpp` | `llm` extra | ✓ already lazy (pre-existing pattern) |
| `transformers`/`torch` | `nli` extra | ✓ already lazy (pre-existing pattern) |
| `fastapi`, `uvicorn` | `server` extra | ✓ |
| `httpx` | `server` extra | **FIXED this slice** — was imported (module-level in `client.py`, lazily in `cli.py`) but declared nowhere; added `httpx>=0.27` to the `server` extra in `pyproject.toml` |
| `onnxruntime` | `onnx` extra | ⚠ declared but imported nowhere — **reserved** for a future ONNX backend; recorded in `tests/test_dependency_rules.py::RESERVED_EXTRAS` so the "no silent unused extra" test stays honest |
| `pytest` | `test` extra | ✓ |

## Internal layering (enforced by tests)

- **contracts** (`errors`, `spec`, `result`, `backend`, `policy`, `validation`) import only each other.
- **backends/*** import only contracts + `features`/`models` + sibling backends — never runtime, state, service, or calibration.
- **calibration/*** import only `errors`/`backend`/`result`/`spec` + sibling calibration modules — never runtime, state, service, or backends.
- Only **service** modules (`server`, `daemon`, `cli`, `client`) may import service modules.

## Structural fixes this slice

1. `pyproject.toml`: `httpx>=0.27` added to the `server` extra.
2. Optional-dependency hardening (following the pre-existing `llm.py`/`nli.py` lazy pattern): `features.py`, `backends/embedding.py`, `backends/logreg.py`, `backends/forest.py`, `backends/boosting.py`, and all of `calibration/` now import `numpy`/`sklearn` defensively and raise a deliberate, actionable error (`pip install 'hugrgate[ml]'`) at use time instead of `ImportError` at import time. Verified: with `numpy`/`sklearn` blocked, calibration raises `CalibrationError`, backends raise `BackendError`, and the stdlib-only path (rules backend + core) still decides correctly.

## Verification

`venv/bin/python -m pytest tests/test_dependency_rules.py -q` — 11 passed.
