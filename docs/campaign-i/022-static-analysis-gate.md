# Slice 022 — Static-analysis gate

**Date:** 2026-10-09 · **Tests:** `tests/test_static_analysis.py` (3 tests)

## What the gate covers

`ruff check` over `hugrgate/`, `tools/`, `tests/` with
`[tool.ruff.lint]` in pyproject: pyflakes (dead names), pycodestyle
errors, isort ordering, pyupgrade modernization (target py310),
bugbear, ruff rules, and blind-except — each deliberate broad
`except` carries a justified `# noqa: BLE001`. `ruff format` is
deliberately *not* gated (pre-existing style; reformat would be pure
churn). New `lint = ["ruff>=0.8"]` extra, mapped in
`test_dependency_rules.py`.

## What the first run caught (all fixed, none waived)

- 715 safe autofixes (modernized annotations/imports, sorted
  imports/`__all__`, removed dead imports).
- 68 manual fixes, several real: 20 `zip()` without `strict=` now
  `strict=True` (silent truncation → loud error); 8
  `raise ... from` chains added; ambiguous `l` variables renamed;
  `int(round(...))` → `round(...)`; `warnings.warn` gained
  `stacklevel=2`; mutable class-default registry → `ClassVar`;
  ambiguous unicode in docstrings → ASCII.
- One autofix casualty caught by the mypy gate: pyupgrade rewrote
  `List[str]` → `list[str]` inside `BackendRegistry`, where the
  method name `list` shadows the builtin — fixed with module-level
  `_StrList`/`_BackendList` aliases.

## Verification

`ruff check` clean; mypy clean on 44 files; full suite 499 passed.
