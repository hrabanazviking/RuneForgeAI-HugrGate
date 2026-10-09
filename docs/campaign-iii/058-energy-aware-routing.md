# Slice 058 — Energy-aware routing

## What existed
Nothing in routing accounted for energy: a 250W GPU backend and a 15W
efficient backend were interchangeable as far as the ladder was
concerned.

## What changed
- **`hugrgate/routing/energy.py`** (new):
  - `EnergyModel`: joules = latency_s × power_watts. Power from
    `hardware_requirements()["power_watts"]` when declared, else
    documented defaults (local 65W, remote 5W client-side; server-side
    energy explicitly out of scope). A backend's own
    `estimated_energy_j()` overrides the model. Measured latency beats
    declared latency when available.
  - `EnergyLedger`: per-request joule budget (`budget_j`, else
    `options.max_energy_j`); reserve/spend/remaining.
  - `EnergyAwarePlanner`: mints a fresh ledger per plan (no cross-request
    leakage), prunes rungs the budget cannot cover, annotates
    `params["energy_estimate_j"]`.
- **`hugrgate/routing/architecture.py`**: `LadderRouterV2` accepts
  `energy_ledger=`; `note_energy(backend, result)` records measured
  latency × modeled power after every attempted rung.
- **`benchmarks/routing_energy_058.py`** →
  **`benchmarks/routing_energy_058.json`**: reproducible artifact.

## Measurement vs baseline (real numbers, this machine)
Two backends, same 80ms work: `gpu-hog` (250W declared) vs `lean` (15W
declared). Baseline (energy-unaware): gpu-hog wins all 6 rounds, 121.35J
spent. Energy-aware (5J budget): gpu-hog pruned (20J estimate), lean wins
all 6 rounds, 7.22J spent. **114.13J saved, 16.80× savings factor.**
Latencies measured; power draws are declared backend figures per the
documented model — rerun the script to reproduce.

## Integration
Planner + router-feedback pattern mirrors slices 056/057. Validation,
provenance, privacy, abstention unchanged.

## Tests
`tests/test_routing_058.py` (9 tests): declared/default/remote power
resolution, measured-latency override, custom `estimated_energy_j`,
ledger accounting + validation, over-budget pruning, options-budget
fallback, empty plan → `Abstention`, measured-energy spend feedback,
no-ledger safety, and the benchmark artifact test (asserts winner sets
and joule savings).

## Evidence
- `pytest tests/test_routing_058.py` → 9 passed.
- `python benchmarks/routing_energy_058.py` → artifact as above.
