# Slice 297 — GPU scheduling boundary

**Status:** complete. Commit: `feat(gjallarbu-297)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

HugrGate had no GPU awareness at all: no discovery, no inventory,
no way to pin a worker to a device. GPU placement was impossible to
even express.

## What was built

- `hugrgate/gpusched.py` — new boundary module:
  - `discover_gpus()`: runs
    `nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits`;
    returns `[]` on CPU-only machines (missing binary or non-zero
    exit are normal, not errors).
  - `parse_smi_csv()`: pure parser — column-count, numeric, and
    negativity validation; deterministic index ordering; tolerates
    `42 %` utilization spellings.
  - `GpuInfo`: frozen dataclass + `memory_used_frac`, `to_dict`.
  - `GpuScheduler`: named-worker device assignment with
    `"least-memory-used"` (default) and `"round-robin"` policies,
    idempotent re-assignment, `release`, optional
    `max_workers_per_gpu` cap, `device_of`, `stats`.
  - Placement is a hint: `assign` returns `None` with no GPUs (CPU
    fallback); callers must run correctly unpinned.
- `hugrgate/errors.py`: new `GpuschedError` (`code="gpusched_error"`,
  `recoverable=True`); registered in `tests/test_errors.py`.

## Law 13 — hardware validation status

**NOT validated on GPU hardware.** No GPU exists on this machine
(`nvidia-smi` absent). Tested: the parser against format samples
(clearly labeled fixtures, not measurements), live discovery
returning `[]` here, and the scheduler against synthetic
inventories. The module docstring carries the warning.

## Tests

`tests/test_perf_297_gpusched.py` — 20 tests, all green; ruff clean;
error-taxonomy and import-cycle gates green.
