# Campaign VIII — Edge Intelligence: Completion Report

**Slices 176–200 · 25 slices · branch `gjallarbu/campaign-viii` · 2026-10-09**

Campaign VIII takes HugrGate to the edge: ARM64 compatibility, Pi and
Jetson baselines, low-RAM operation, thermal/power-aware routing,
quantized inference, NPU adapters, offline-first bootstrap, and a
release gate that encodes the campaign's Definition of Done.

## Evidence

- **Full test suite: 803 passed, 0 failed** (46.8s, this host, x86_64).
- **Edge tests: 278** across 18 modules (`test_edge_*`).
- **ruff**: clean over `hugrgate/`, `tests/`, `tools/`. **mypy**: clean
  over `hugrgate/`.
- **Release gate**: `edge_release_gate(".")` → all 8 checks green
  (see slice 200 doc for the check list).
- **Benchmarks**: `benchmarks/edge/` — 4 artifacts, 300 iterations each,
  all validating under `edge-bench/1` (surrogate-host marking per
  Execution Law rule 13).

## What was built (per slice)

| Slice | Module | Essence |
|---|---|---|
| 176 | `edge/platform.py` | ARM64 audit: severity-graded findings, `audit_arm64()` |
| 177 | `edge/platform.py` | Pi baselines: `detect_pi_board()`, `pi_baseline()`, `PI_BASELINES` |
| 178 | `edge/memory.py` | `MemoryManager`: standard/low/critical modes, budgets, ledger |
| 179 | `edge/affinity.py` | `AffinityController`: CPU pinning, profiles, cpuset ceiling |
| 180 | `edge/thermal.py` | `ThermalGovernor`: hysteresis, 1.0→0.25 derating |
| 181 | `edge/power.py` + `routing.py` | Milliwatt ledger; thermal+power backend filtering beside `HugrGate` |
| 182 | `edge/quant.py` | `QuantProfileRegistry`, `select_profile()` |
| 183 | `edge/quant.py` | Real affine INT8: per-tensor/per-channel, `HGQT0001`, `int8_matvec()` |
| 184 | `edge/quant.py` | `Int4Adapter`: groupwise N-D, `HGQ40001`, exact `storage_bytes()` |
| 185 | `edge/npu.py` | `NPUAdapter` ABC, `NPURegistry.best_for()`, `MockNPUAdapter` |
| 186 | `edge/npu.py` | `HailoAdapter` (.hef boundary, lazy SDK) |
| 187 | `edge/npu.py` | `JetsonAdapter` (.engine/.plan boundary, lazy SDK) |
| 188 | `edge/npu.py` | `OpenVINOAdapter` (.xml IR boundary, lazy SDK) |
| 189 | `edge/residency.py` | `ResidencyManager`: LRU, pinning, refcounts |
| 190 | `edge/cachetune.py` | `tune_cache()`, `EdgeCache` budget-derived sizing |
| 191 | `edge/storage.py` | `WearAwareStore`: write budget, coalescing, `HGWS0001`, `compact()` |
| 192 | `edge/bootstrap.py` | `BootstrapPlan` with structural offline-first law |
| 193 | `edge/recovery.py` | `CheckpointJournal`: CRC32, torn-write skipping |
| 194 | `edge/watchdog.py` | `EdgeWatchdog`: miss policies, restart latch |
| 195 | `edge/telemetry.py` | `TelemetryLite`: 256-event ring, numeric-only values |
| 196 | `edge/bench.py` | `EdgeBenchmark`, `compare_artifacts()`, `edge_bench_suite()` |
| 197 | `edge/bench.py` | `pi_bench_suite()` |
| 198 | `edge/bench.py` | `jetson_bench_suite()`, `jetson_baseline()` |
| 199 | `edge/chaos.py` | `ChaosRunner` + 6 built-in fault scenarios |
| 200 | `edge/gate.py` + facade | `edge_release_gate()`; `hugrgate/edge/__init__.py` (109 exports) |

19 modules, ~5,200 LOC, 216 public names. Every module registered in
the architecture map (layer `edge`), the API inventory, and the test
taxonomy.

## Notable findings

- **Honest benchmark cost curve**: `storage/put-flush` flagged +72.5%
  run-to-run — append-only log growth, arguing for periodic `compact()`.
- **Real-Linux subtleties pinned by tests**: affinity validates against
  the cpuset ceiling captured before first pin; memory mode boundaries
  use `<`; Hailo-8 vs 8L needs exact device-name match.
- **The gate caught real drift**: at slice 199 the tree failed 4 repo
  gate tests (import cycle, package boundary, taxonomy raise-sites,
  dependency declarations) — fixed in slice 200, which is exactly what
  a release gate is for.

## Remaining debt / needs hardware validation

Per Execution Law rule 13, everything NPU/silicon-shaped is a testable
abstraction with injectable mocks:

- `HailoAdapter`, `JetsonAdapter`, `OpenVINOAdapter`: `detect()` paths,
  real `.hef`/`.engine`/IR loading, and all TOPS/latency/watt numbers —
  **NEEDS_HARDWARE_VALIDATION** on real Hailo-8, Jetson Orin Nano, and
  Intel NPU silicon.
- `pi_baseline()` / `jetson_baseline()` figures are structural
  placeholders, not measurements — re-run `pi_bench_suite()` /
  `jetson_bench_suite()` on real boards.
- Thermal/power sysfs sensors: paths probed, never read on this host.
- Benchmark artifacts carry `hardware_note` with SURROGATE HOST marking;
  regenerate on target hardware before quoting numbers.

## Integration points (for later campaigns)

- `EdgeRouter` sits beside `HugrGate` (core untouched); consumes
  `Backend.hardware_requirements()["edge"]` and Campaign VI's
  energy/power routing objectives.
- `edge_bench_suite()` wires a real `HugrGate` + `RuleBackend` for
  host-side comparison measurements.
- All 15 edge errors are now first-class taxonomy citizens
  (`edge_*` codes, wire-safe via `to_dict`/`from_dict`).
