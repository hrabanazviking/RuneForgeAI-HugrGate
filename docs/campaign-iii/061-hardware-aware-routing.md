# Slice 061 — Hardware-aware routing

## What existed
`Backend.hardware_requirements()` existed but routing never consulted
it: a GPU-only backend was planned onto GPU-less hosts and failed (or
worse, hung) at run time.

## What changed
- **`hugrgate/routing/hardware.py`** (new):
  - `HostProfile`: cpu_count, memory_mb, has_gpu, platform,
    accelerators; `HostProfile.detect()` builds one from the real
    machine with stdlib only (`os.cpu_count`, `/proc/meminfo`,
    `nvidia-smi` presence — best-effort, documented).
  - `hardware_compatible(backend, host) -> Optional[str]`: checks
    `requires_gpu`, `min_memory_mb`, `min_cpu_count`, `platforms`;
    unknown keys ignored; boundary-equal fits; returns the reason or
    None.
  - `HardwareAwarePlanner`: prunes incompatible rungs at plan time,
    stamps `params["host_compatible"]`, records host profile in the
    rationale.

## Integration
Planner-side; composes with other aware-planners by wrapping. Run-time
`BackendUnavailable` handling in `_attempt` remains the backstop.

## Tests
`tests/test_routing_061.py` (5 tests): `detect()` sanity on this
machine, all four incompatibility reasons, boundary equality,
unknown-key tolerance, gpu-host pass, plan-time pruning, all-pruned →
`Abstention`, end-to-end win by the compatible rung.

## Evidence
- `pytest tests/test_routing_061.py` → 5 passed.
