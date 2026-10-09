# Slice 484 — Dependency-latest matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_484_deplat.py` (6 tests)

## What existed

Slice 483 pinned the minimum floor; nothing recorded the
*validated-latest* set or checked for deprecated/removed
dependency APIs against current releases.

## What changed

- `hugrgate/gauntlet/deps.py`: `latest_audit()` (installed
  versions + floor conformance) and `scan_deprecated_api()` —
  regex scan for `yaml.load()` without a Loader,
  `datetime.utcnow()`, dead numpy aliases, `collections` ABCs,
  `time.clock()`, with AST span analysis so detection corpora
  (which must *name* these APIs) are not flagged.
- `tools/matrix/dep_latest_audit.py` (new, executable): runs the
  audit, writes `docs/gauntlet/484-dependency-latest-manifest.json`
  (pyyaml 6.0.3, meets floor, 0 deprecated-API findings), exits
  non-zero on violations.
- `docs/gauntlet/484-dependency-latest-manifest.json` (new): the
  measured manifest; the test asserts it byte-matches a fresh run.

## Verification

`LATEST-AUDIT OK`; `pytest` green (13 tests across 483/484);
`ruff`/`mypy` clean.
