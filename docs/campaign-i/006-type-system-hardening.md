# Slice 006 — Type-system hardening

**Date:** 2026-10-09 · **Tool:** mypy 2.4.0 · **Gate:** `tests/test_typecheck.py`

## Baseline

`mypy hugrgate --ignore-missing-imports` reported **41 errors** across
13 files: unguarded `Optional` attribute access (client/server/cli/daemon
`registry.get()` chains), `Optional` arithmetic on numeric-spec bounds,
`Dict` used without import (`timeout.py` — worked at runtime only because
annotations are strings), a variable reused at two types (`llm.py`
`lowered: str` then `dict`), `None`-callable pipeline (`nli.py`), and
stale `# type: ignore` comments.

## Fixes (all real, no ignore-spam)

- **Narrowing via construction invariants:** `spec.value_space()`,
  `validation.validate_result`, `fallback` safe-default check, and
  `server.UniformBackend.evaluate` now `assert` the numeric-spec bounds
  that `_validate_numeric` guarantees (`minimum`/`maximum` not None).
- **`rules.Rule.matches`**: restructured to a local-variable None check
  instead of relying on the `is_default` property for narrowing.
- **`client.HugrGateClient`**: new `_direct()` accessor encoding the
  `_direct_gate ⟺ _gate` invariant; `decide`/`health`/`backends` use it.
- **Defensive `registry.get()` handling**: `cli.cmd_backends`,
  `client.backends` (both paths), `server` `/backends` endpoint, and
  `daemon` warm pool skip a `None` backend instead of crashing on
  attribute access.
- **`circuit.CircuitRegistry._defaults`**: typed `Dict[str, Any]`
  (heterogeneous kwargs bag).
- **`llm.py`**: renamed the shadowing `lowered` dict to `by_lower`.
- **`bench.py`**: `set(result.value or [])` in multilabel branches;
  walrus-bound registry lookup for `calibration_info()`.
- **`embedding.py`**: `np.max(z)` instead of `z.max()` (stub overload).
- **`timeout.py`**: added the missing `Dict` import.
- **`nli.py`**: defensive `None` check after `_ensure_engine()`.
- Removed 5 stale `# type: ignore` comments flagged by
  `warn_unused_ignores`.

## Standing gate

- `[tool.mypy]` in `pyproject.toml` (`check_untyped_defs`,
  `warn_unused_ignores`, `warn_redundant_casts`).
- `tests/test_typecheck.py::test_mypy_reports_no_errors` runs
  `mypy hugrgate --no-incremental` (hermetic) and fails on any error;
  skips only when mypy is not installed.

## Verification

Cold-cache run: `Success: no issues found in 42 source files`.
Full suite: 363 passed before this slice's final edits; re-run at commit.
