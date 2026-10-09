# Slice 439 — Backend plugin SDK

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_439_plugins.py` (15 tests)

## What existed

Backends were registered in-process by hand; there was no
contract for third-party backends to plug in, no discovery, and
no validation — a broken backend class failed wherever it was
first touched.

## What changed

- `hugrgate/plugins.py` (new) — the plugin SDK over the
  `hugrgate.backends` entry-point group:
  - `discover_plugins(on_error)` → `(loaded, failed)`; one
    broken plugin is isolated and reported, never fatal
    (unless `on_error="raise"`).
  - `load_plugin(name)` — imports, instantiates (class or
    instance entry points), and validates; every failure is a
    `PluginError` (`plugin_error`, recoverable) with the plugin
    name attached.
  - `validate_plugin(backend)` — `Backend` instance, non-blank
    name, callable `capabilities`/`supports`/`evaluate`,
    dict capabilities, `supports()` returning bool on a probe
    spec without raising.
  - `register_discovered_plugins(registry)` → `PluginReport`
    (registered / skipped-duplicates / errors); duplicates
    skipped unless `replace=True`.
- `hugrgate/cli.py`: `hugrgate plugins` lists discovered
  plugins with ok/FAILED status (exit 1 when any failed),
  honoring `--format`.
- `tests/test_dependency_rules.py`: `hugrgate.plugins` joins
  the SERVICE layer.

## Verification

15 tests with fake entry points: isolation of an import bomb,
wrong-type object, blank name, and bad capabilities;
raise-mode; missing names; duplicate skip; and a loaded plugin
deciding end-to-end through a real `HugrGate`. CLI listing in
json and table forms. `ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_439_plugins.py` — 15 passed
