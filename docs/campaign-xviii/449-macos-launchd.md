# Slice 449 — macOS launchd guide

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_449_macos.py` (6 tests)

## What existed

No macOS story.

## What changed

- `deploy/macos/com.hugrgate.daemon.plist` (new): per-user
  launchd agent — `hugrgate serve --config`, `RunAtLoad`,
  `KeepAlive` (crashes only), 30 s throttle, log capture.
- `deploy/macos/hugrgate.yaml` (new): macOS daemon config
  (loopback bind), validated through `load_daemon_config`.
- `docs/macos-launchd.md` (new): prerequisites, install,
  operate, per-user vs system daemon notes.
- `tests/test_deveco_449_macos.py` (new): plistlib parse +
  key assertions, config validation, guide coverage.

## Verification

6 passed (plistlib is real validation of the plist XML).
`ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_449_macos.py` — 6 passed
