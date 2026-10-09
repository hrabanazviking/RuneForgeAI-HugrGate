# Slice 437 — Config generator

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_437_configgen.py` (22 tests)

## What existed

Operators hand-wrote `spec.yaml` / `policy.yaml` / daemon configs
from docs, with misspelled keys and out-of-range values failing
only at runtime.

## What changed

- `hugrgate/configgen.py` (new):
  - `generate_daemon_config(**overrides)` — annotated
    `hugrgate.yaml` from the real `DaemonConfig` field set;
    unknown keys and invalid values raise `ConfigError`
    (the file the daemon would reject is never written).
  - `generate_spec(type, **fields)` — templates for all four
    spec types, validated with `DecisionSpec.from_dict`.
  - `generate_policy(**overrides)` — validated with
    `policy_from_dict`.
  - `load_daemon_config(path)` — validated loading for
    hand-edited files (`ConfigError` on missing/unparseable/
    unknown-key/invalid-value).
  - `write_new(path, content, force)` — refuses to overwrite
    without `--force`; `init_project(dir)` writes the four
    starter files.
- `hugrgate/cli.py`: `hugrgate init [--dir] [--force]`,
  `hugrgate gen daemon|spec|policy [--out] [--force]` with
  flag-driven customization (`--options`, `--statement`,
  `--levels`, `--min-probability`, `--max-latency-ms`), and
  `hugrgate serve --config hugrgate.yaml` — the file supplies
  values for flags left at defaults; explicit flags win.

## Verification

22 tests: every generator output round-trips through its real
validator; unknown keys/bad values rejected at generation time;
overwrite protection (+ `--force`); bad configs → exit 2;
`serve --config` overlay applies file values and explicit flags
win. `ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_437_configgen.py` — 22 passed
