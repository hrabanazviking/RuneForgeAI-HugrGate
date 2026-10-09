# Slice 479 — Linux matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_479_linux.py` (9 tests)

## What existed

No platform story at all: POSIX-only API uses were never scanned,
and the "supported platform" claim rested on the developer's
laptop.

## What changed

- `hugrgate/gauntlet/platforms.py` (new): `PlatformInfo` /
  `current_platform()`, `VALIDATED_PLATFORMS` (platforms proven by
  actually running the checks — never extended by assertion),
  `record_validated()` / `is_validated()`, `scan_posix_only()` (AST
  scan for POSIX-only imports/attrs with guard analysis recognizing
  `try/except ImportError`, `sys.platform`/`os.name` conditionals),
  `linux_live_checks()` (epoll, `/proc/self`, `uname`).

## Attack findings

The scan over `hugrgate/` found 4 POSIX-only use sites: 3 guarded
`import resource` uses (correctly recognized) and **1 unguarded
`signal.SIGKILL` default argument** in `hugrgate/chaos/crash.py:98`
— evaluated at def time, it breaks Windows import. Fixed in slice
480; this slice proves the detector catches it.

## Verification

`pytest tests/test_gauntlet_479_linux.py` green (live Linux probes
pass on this host: Linux x86_64, epoll present); `ruff`/`mypy`
clean.
