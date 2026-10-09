# Slice 296 — NUMA awareness boundary

**Status:** complete. Commit: `feat(gjallarbu-296)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

HugrGate had no notion of NUMA topology: worker threads (scheduler,
process pool, session pools) floated wherever the OS placed them,
with no way to even *ask* which node a thread was on.

## What was built

- `hugrgate/numa.py` — new boundary module:
  - `detect_topology()`: parses `/sys/devices/system/node`
    (node→cpus, distance matrix); synthesizes a single node when
    sysfs is absent.
  - `NumaTopology`: `node_of_cpu`, `distance`, `to_dict`.
  - `current_node()`: node of the calling thread via affinity
    intersection.
  - `pin_thread(cpus)` / `pin_to_node(node)`: `sched_setaffinity`
    wrappers; unknown CPUs/nodes and empty sets raise `NumaError`.
  - `pinned_to(node)`: context manager pinning for a block and
    restoring affinity after.
  - `suggest_node(worker_index)`: round-robin striping.
  - Pinning is documented as a *hint*, never correctness.
- `hugrgate/errors.py`: new `NumaError` (`code="numa_error"`,
  `recoverable=True`); registered in `tests/test_errors.py`.

## Law 13 — hardware validation status

**NOT validated on multi-node hardware.** This VM exposes a single
NUMA node (node0, cpus 0–1) via real sysfs. All pinning round-trips
were exercised for real (affinity set/read-back/restore), but
cross-node pinning, distance-aware placement, and any locality
performance claim await a multi-socket machine. The module docstring
carries the warning; `test_single_node_hardware_noted` pins the fact
in the suite.

## Tests

`tests/test_perf_296_numa.py` — 13 tests, all green; ruff clean;
error-taxonomy and import-cycle gates green.
