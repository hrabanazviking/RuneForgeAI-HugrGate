# Slice 482 — ARM64 matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_482_arm64.py` (8 tests)

## What existed

No architecture axis in the platform matrix: `platform.machine()`
aliases (`aarch64` on Linux vs `arm64` on macOS for the same ISA)
would have been recorded as different platforms, and nothing
scanned for x86-64-only assumptions.

## What changed

- `hugrgate/gauntlet/platforms.py`: `normalize_arch()` canonicalizes
  machine strings (`aarch64`→`arm64`, `AMD64`→`x86_64`, ...);
  `PlatformInfo.arch_key` / `platform_key` use the normalized form,
  so `record_validated()`/`is_validated()` unify the aliases;
  `check_arch_assumptions()` flags raw ISA tokens, SIMD intrinsic
  references, and exact `platform.machine()` string comparisons
  (which must go through `normalize_arch()`). The live tree is
  clean: 0 findings.

## Verification

`pytest` green across all four platform test modules (32 tests);
`ruff`/`mypy` clean.
