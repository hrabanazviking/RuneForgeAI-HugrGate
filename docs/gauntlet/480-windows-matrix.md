# Slice 480 — Windows matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_480_windows.py` (6 tests)

## What existed

Slice 479's scan proved one Windows import-time crash: an unguarded
`signal.SIGKILL` evaluated as a default argument in
`hugrgate/chaos/crash.py:98` (`signal.SIGKILL` does not exist on
Windows).

## What changed

- `hugrgate/chaos/crash.py`: `run_worker(..., kill_signal=None)`;
  the signal is resolved at call time via the new
  `CrashOnlyHarness.default_kill_signal()` (`getattr(signal,
  "SIGKILL", signal.SIGTERM)`). Existing keyword callers are
  unaffected.
- `hugrgate/gauntlet/platforms.py`: new `check_windows_import_safety()`
  gate — zero unguarded POSIX-only uses across the tree.

## Verification

`pytest tests/test_gauntlet_480_windows.py` green, including a
simulated-Windows import (`signal.SIGKILL` deleted, module
re-imported, falls back to `SIGTERM`); existing
`tests/test_chaos_crash.py` (slow) still green; `ruff`/`mypy` clean.
