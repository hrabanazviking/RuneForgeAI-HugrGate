# Slice 174 — Local runtime benchmark matrix

## Skald (what already existed)
- `hugrgate/bench.py` benchmarks decision gates on datasets; nothing
  measured local runtime latency per operation.

## Rúnhild (design)
`hugrgate/runtimes/bench_matrix.py`: `bench_runtime` runs
`warmup_rounds` untimed + `rounds` timed iterations per advertised
capability (generate/embed/classify) and records p50/p95/mean/min/
max; failures become `ok:false` rows with the honest error, never
silenced. `bench_all` covers a registry; `BenchMatrix.to_dict()`
adds provenance (schema version, config, timestamp, python/
platform/git-sha, and a `note`). `build_default_registry()` benches
two `FakeRuntime`s (one with 50ms injected latency, proving the
apparatus resolves real delays) plus all 8 adapters.
`write_artifact` writes `benchmarks/localrt-matrix.json`;
`main()` regenerates it at full rounds. Tests use tiny configs and
`tmp_path` only — they never touch the real artifact (per the
worker tip: regenerate, don't rewrite in place).

## Eldra (what was built)
- `hugrgate/runtimes/bench_matrix.py` (new): `BenchConfig`,
  `BenchResult`, `BenchMatrix`, `bench_runtime`, `bench_all`,
  `write_artifact`, `build_default_registry`, `main`.
- `benchmarks/localrt-matrix.json` (new artifact): 18 rows at
  10 rounds × 2 warmup — 6 measured (fake p50 0.012ms, delayed
  fake 50.2ms) and 12 honest `ok:false` rows (no engines in CI).
  Labeled "Synthetic baseline" in the artifact note.
- `tests/test_localrt_174_bench_matrix.py` (new, 11 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_174_bench_matrix.py -q` → 11 passed.
`ruff` clean, `mypy` clean. Artifact regenerated after the final
test run via `python -m hugrgate.runtimes.bench_matrix`.

## Védis (integration)
- Pure addition; reuses `register_all_adapters` from slice 173.
  Artifact lives with the other benchmark JSONs.

## Scribe
Commit `feat(gjallarbu-174): local runtime benchmark matrix` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Re-run `main()` on a host with engines installed for a real
  matrix (schema identical; artifact note must be updated).
