# Slice 462 — Hardware-aware tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_462_hardware.py` (9 tests)

## What existed

One static config served every host from a 2-core edge box to a
64-core server. Nothing adapted configuration to the hardware it
actually ran on.

## What changed

- `hugrgate/autotune/tuners/hardware.py`:
  - `detect_hardware()`: stdlib-only host detection (cpu count,
    `/proc/meminfo` RAM with a conservative unknown-memory fallback,
    arch, OS);
  - `HardwareTier`: named minimum cpu/memory requirements plus a
    parameter profile; unknown memory waives the memory requirement
    rather than failing closed on non-Linux hosts;
  - `HardwareAwareTuner`: picks the most demanding satisfied tier,
    diffs its profile against live config, proposes only differing
    params (each validated through the store's type/bounds);
  - injectable hardware profile for deterministic tests/dry-runs;
  - honest limitation recorded in evidence: profile *quality* on the
    hardware still needs real-world validation (slice 474).

## Verification

9 new tests (real detection smoke test, tier selection across three
classes, unknown-memory waiver, full/partial profile proposals,
silence when matching, out-of-bounds profile rejection, tier spec
validation, end-to-end offline); `ruff` and `mypy` clean.
