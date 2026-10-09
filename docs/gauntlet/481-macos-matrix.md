# Slice 481 — macOS matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_481_macos.py` (9 tests)

## What existed

macOS was an untested hope: no `/proc`, no `select.epoll`, and
`spawn`-default multiprocessing were all assumed-but-unverified.

## What changed

- `hugrgate/routing/hardware.py`: `HostProfile._detect_memory_mb()`
  now probes `sysctl hw.memsize` on darwin before the 1024 MB
  conservative fallback — previously every Mac silently reported
  1 GB of RAM, which could wrongly prune memory-hungry backends.
- `hugrgate/gauntlet/platforms.py`: new `check_macos_assumptions()`
  — flags unguarded `open("/proc/...")` reads, `select.epoll` uses,
  and forced `multiprocessing` `"fork"` start methods. The live tree
  is clean on all three (0 findings).

## Verification

`pytest tests/test_gauntlet_481_macos.py` green (darwin memory path
proven with a simulated macOS: no `/proc`, fake sysctl returning
17179869184 bytes → 16384.0 MiB; sysctl failure → 1024.0 fallback);
existing routing tests green; `ruff`/`mypy` clean.
