# Slice 179 — CPU affinity controls

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_affinity.py` (24 tests, green)

## What existed before

No CPU pinning anywhere in HugrGate — inference threads contend with
the watchdog, telemetry, and OS housekeeping on small ARM boards.

## What was built

`hugrgate/edge/affinity.py`:

- **`parse_cpu_list("0-3,5")`** → `frozenset`; rejects empty specs,
  negatives, reversed/non-numeric ranges.
- **`AffinityController`** —
  - `available_cpus()` introspects via `os.sched_getaffinity`, falling
    back to `os.cpu_count()` where the syscall is absent;
  - `validate()` checks requests against the **cpuset ceiling captured
    before the first pin** (a real Linux subtlety the tests caught:
    `sched_getaffinity` returns the *transient* narrowed mask, so
    validating against it would make `pinned()` unable to restore its
    own previous set);
  - `set_affinity()` validates, applies via `os.sched_setaffinity`,
    wraps `OSError` in `EdgeAffinityError`; `dry_run=True` records
    without touching the OS;
  - `profile_cpus("full"|"inference"|"isolated")` — inference leaves
    core 0 for the OS/watchdog;
  - `pinned(cpus)` context manager restores the previous set even on
    exception; `pin_callable(fn, cpus, ctl)` helper.
- All OS interaction goes through an injectable `_OsFuncs` seam;
  `FakeOs` in tests records syscalls without touching the host.

## Integration

- Registered in the `edge` architecture layer; maps + API inventory
  regenerated; test module added to the taxonomy unit row.
- `__all__` contracts hardened (star-import gate): public constants
  (`PROFILES`, memory thresholds) now listed.

## Validation notes (Execution Law rule 13)

The syscall path itself cannot be proven without a Linux host that
permits `sched_setaffinity`; `dry_run` mode and `FakeOs` cover policy.
Real cpuset/cgroup ceilings need on-device confirmation.

## Verification

- `pytest tests/test_edge_affinity.py` — 24 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
