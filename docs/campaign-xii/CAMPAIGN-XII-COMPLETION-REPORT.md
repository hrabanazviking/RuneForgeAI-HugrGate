# Campaign XII — Performance Forge: Completion Report

**Branch:** `gjallarbu/campaign-xii`
**Slices:** 276–300 (25 slices; 276–299 implementation, 300 release gate)
**Date:** 2026-10-09
**Base:** `origin/main` @ `1139ea2`

## Mission

Profile it, measure it, harden it. Campaign XII attacked HugrGate's
performance surfaces — profiling, hot paths, allocation, serialization,
async, scheduling, pooling, caching, locking, multiprocessing,
supervision, NUMA/GPU boundaries, regression gates, and sustained
throughput — with real measurements, never placeholders.

## Slice ledger

| Slice | Commit | What was built |
|---|---|---|
| 276 | `79738c6` | `profiling.py`: DecisionProfiler, profile_region |
| 277 | `edff35d` | `flame.py`: folded stacks, SVG flamegraphs; real baseline artifact |
| 278 | `1cfde1b` | `hotpaths.py`: HotPathCollector aggregation |
| 279 | `dfa2047` | `allocprof.py`: tracemalloc allocation profiling |
| 280 | `dc86db1` | `zerocopy.py`: frozen results, zero-copy cache, SharedPayload |
| 281 | `bdbb3ba` | `serde.py`: compact positional codec (4x encode, −6.5% wire) |
| 282 | `1f2fee6` | `asyncx.py` + true-async core path (`adecide`, `adecide_batch`) |
| 283 | `618d878` | `async_backend.py`: AsyncGate, timeouts, streaming |
| 284 | `0d65818` | `ladder.py`: concurrent ladder, ordered race |
| 285 | `81d456c` | `scheduler.py`: BatchScheduler v2 (windowing, backpressure, drain) |
| 286 | `e170b92` | AIMD dynamic batch sizing |
| 287 | `935a924` | Priority scheduling with aging (starvation-free) |
| 288 | `a3e11ac` | Deadline scheduling (EDF, drop_late, miss accounting) |
| 289 | `aa20fac` | `backpressure.py`: TokenBucket engine + scheduler admission |
| 290 | `e8aa169` | `pool.py`: ResourcePool + shared HTTP pool; CLI integration |
| 291 | `7f9bcf4` | `runtimes/session_pool.py`: warm loaded sessions per ModelRef |
| 292 | `835eb47` | Cache tuning: key −17%, copy 2.3x; measured artifacts |
| 293 | `e984aa5` | `lockaudit.py`: AST audit + InstrumentedLock; cache lock hoist |
| 294 | `3f0c259` | `multiproc.py`: spawn-based process pool, picklable tasks |
| 295 | `1838800` | `supervision.py`: heartbeats, restarts, escalation |
| 296 | `e34db0f` | `numa.py`: topology detect, thread pinning (Law 13 noted) |
| 297 | `0ceae05` | `gpusched.py`: nvidia-smi discovery, device scheduler (Law 13 noted) |
| 298 | `55b67be` | `perfgate.py`: regression gates + committed baseline artifact |
| 299 | `d165902` | `millionbench.py`: real 1M run (7,845/s, 0 errors) |
| 300 | — | Release gate (this report) |

## New error taxonomy (all in `hugrgate/errors.py`, registered in `tests/test_errors.py`)

| Class | Code | Recoverable |
|---|---|---|
| ProfilingError | `profiling_error` | True |
| ZeroCopyError | `zerocopy_error` | True |
| SerdeError | `serde_error` | False |
| SchedulerError | `scheduler_error` | True |
| BackpressureError | `backpressure_error` | True |
| PoolError | `pool_error` | True |
| MultiprocError | `multiproc_error` | True |
| SupervisionError | `supervision_error` | True |
| NumaError | `numa_error` | True |
| GpuschedError | `gpusched_error` | True |
| PerfGateError | `perfgate_error` | **False** |

## Measured wins (real numbers, seeded/reproducible)

- Serde encode 4.0x faster (1.45→0.36µs); wire −6.5%.
- Cache key −17% (28.9→24.0µs median); result copy 2.3x (20.2→8.9µs).
- Cache lock hold 44µs → ~1µs; 2-thread +10%, 4-thread +19% throughput.
- Sustained: **7,845 decisions/s** over 1M (p50 80.9µs, p95 134µs, 0 errors).
- Regression gates committed (`benchmarks/perf_baseline.json`).

## Honest caveats

- **VM noise:** ±50% run-to-run on sequential microbenchmarks; decisive
  evidence came from interleaved same-process A/B. Documented per slice.
- **Law 13:** NUMA multi-node and GPU behaviors implemented but
  **not validated on real hardware** (single-node VM, no GPU here).
- **Provenance growth:** 1M decisions → +1.3 GB RSS (unbounded
  `ProvenanceStore` default); bounded mode is +23% faster with flat
  memory. Default left unchanged (audit semantics) — recommended
  follow-up: `provenance_max_records` option on `HugrGate`.
- **8-thread cache convoy:** the slice-293 lock hoist is unstable at
  8-thread saturation in a pathological tight loop (GIL convoy);
  realistic workloads show no difference. Documented, kept.

## Bugs the tests caught before commit

pstats 4-tuples; en-dash RUF002; ThreadPoolExecutor zip swap; scheduler
drain race; lock-order inversion in stats(); backpressure accounting;
reaper sleep stalling shutdown (63s→2.3s); `object()` pickles fine
(wrong test premise); raise-site taxonomy violations; supervision
escalation race (flag-before-notification); taxonomy doc drift;
API inventory drift.

## Files

- Implementation: `hugrgate/profiling.py`, `flame.py`, `hotpaths.py`,
  `allocprof.py`, `zerocopy.py`, `asyncx.py`, `async_backend.py`,
  `scheduler.py`, `backpressure.py`, `pool.py`,
  `runtimes/session_pool.py`, `lockaudit.py`, `multiproc.py`,
  `supervision.py`, `numa.py`, `gpusched.py`, `perfgate.py`,
  `millionbench.py`; extended `serde.py`, `cache.py`, `core.py`,
  `ladder.py`, `cli.py`, `errors.py`.
- Docs: `docs/campaign-xii/276-*.md` … `299-*.md` + this report.
- Artifacts: `benchmarks/flamegraphs/decide-baseline.*`,
  `benchmarks/cache_tuning*.json`, `benchmarks/perf_baseline.json`,
  `benchmarks/million_decisions.json`.
- Tests: `tests/test_perf_276_*.py` … `tests/test_perf_299_*.py`
  (24 modules; 6 slow-marked); taxonomy doc unit/slow rows updated.

## Release gate (slice 300)

- Full suite: **3252 passed, 1 skipped** (baseline on origin/main:
  2936 passed, 1 skipped; +316 net new tests), 2026-10-09.
- Ruff: clean. Mypy gate: clean. API inventory, arch map, repo-truth
  manifest, test taxonomy, package boundaries: all green
  (release-gate pass fixed drift in each).
- `git push origin gjallarbu/campaign-xii`: done 2026-10-09; remote
  HEAD `ab6ead2` verified via `git ls-remote`.
