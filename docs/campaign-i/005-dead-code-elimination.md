# Slice 005 — Dead-code elimination

**Date:** 2026-10-09 · **Method:** coverage-guided (89% statement coverage
over the full suite) + AST reference analysis · **Tests:** `tests/test_dead_code.py`

## Removed

9 genuinely unused imports (each referenced exactly once — at its own
import line; verified against string-annotation false positives):

| File | Removed |
|---|---|
| `hugrgate/bench.py` | `field` (dataclasses) |
| `hugrgate/bench_report.py` | `Dict` |
| `hugrgate/cli.py` | `Mapping`, `DaemonConfig` (lazy), redundant `Abstention as _A` |
| `hugrgate/ladder.py` | `field` (dataclasses) |
| `hugrgate/negotiate.py` | `Dict` |
| `hugrgate/policy.py` | `field` (dataclasses) |
| `hugrgate/server.py` | `DecisionPolicy` |
| `hugrgate/backends/embedding.py` | `math` |

## Revived instead of removed

Two public names had zero in-repo references but are live API, not dead code:

- **`register_model`** (`hugrgate/server.py`) — the write side of the
  `/models` catalogue (`list_models()` / `hugrgate models` read it).
  Now pinned by `test_register_model_round_trips_through_catalogue`.
- **`BenchmarkConfig`** (`hugrgate/bench.py`) — a public dataclass whose
  fields duplicated `run_benchmark`'s kwargs with no consumer. It is now
  a first-class input: `run_benchmark(..., config=BenchmarkConfig(...))`;
  explicit keywords still win over config fields (backward compatible).
  Pinned by `test_benchmark_config_drives_run_benchmark`.

Private (`_`-prefixed) functions: none are never-called (dunder false
positives excluded). No fully-unexecuted public function exists at
current coverage.

## Standing guard

`test_no_unused_imports_in_package` fails the suite if any import under
`hugrgate/` becomes unreferenced again.

## Verification

`venv/bin/python -m pytest tests/test_dead_code.py -q` — 5 passed;
full suite green (see group push notes).
