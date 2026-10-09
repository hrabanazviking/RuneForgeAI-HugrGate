# Slice 485 — Upgrade/migration gauntlet

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_485_migration.py` (17 tests)

## What existed

`hugrgate/contracts/migration.py` migrated spec *dicts*, but no
on-disk *store file* had a migration story:
`hugrgate/memory/io.py::_parse_line` hard-rejected any export
envelope whose version was not current, so old backups became
unreadable garbage after a format bump.

## What changed

- `hugrgate/gauntlet/store_migrate.py` (new): `Migration` /
  `MigrationRegistry` (BFS shortest-path planning, multi-hop
  chains, per-step history, failures wrapped in
  `MigrationError`), `migrate_envelope_file()` (whole-file JSON
  envelopes, `.bak` backup, idempotent).
- `hugrgate/errors.py`: new `MigrationError`
  (`code="migration_error"`, `recoverable=False`); promoted into
  the `tests/test_errors.py` taxonomy (`ALL_ERRORS`).
- `hugrgate/memory/io.py`: `MEMORY_MIGRATIONS` registry +
  `register_memory_migration()`; `_parse_line` now migrates old
  envelopes forward when a path is registered, and still raises
  `MemoryError("unsupported version")` when no path exists.

## Verification

`pytest` green (17 new + existing memory/error suites, 38 total);
a synthetic v0→v1 episode envelope imports through the real
`import_jsonl` path; `ruff`/`mypy` clean.
