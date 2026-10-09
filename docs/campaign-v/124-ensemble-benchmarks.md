# Slice 124 — Ensemble benchmarks

**Status:** complete · **Commit:** `feat(gjallarbu-124): ensemble benchmarks`

## Skald (inspect)
No measured numbers existed for ensemble strategies — accuracy,
Brier, ECE, latency were all promises, not measurements.

## Rúnhild (design)
New module `hugrgate/ensemble/benchmarks.py`:
- `benchmark_strategies(member_factory, states, spec, labels,
  strategies)` — one fresh council per strategy over the same
  labeled states; reuses `hugrgate.bench` accuracy/Brier/ECE so
  ensemble numbers compare with single-backend numbers; reports
  wall time + mean per-result latency.
- `benchmark_scaling(member_factory_n, states, spec, sizes)` —
  wall time vs council size.
- `write_benchmark_report(report, path)` — pretty JSON artifact.
- `demo_council(n)` + `regenerate_ensemble_benchmarks()` —
  deterministic demo voters (fixed correct/incorrect cycles, no
  RNG) regenerating `benchmarks/ensemble.json`.

## Eldra (code)
Real harness; demo members clearly labeled, artifact-only.

## Sólrún (tests)
`tests/test_ensemble_124_benchmarks.py` — 7 tests green:
success (all four strategies measured, accuracy 1.0 on
agreeing data; accuracy differences detected; scaling table;
report written to tmp_path; JSON-serializable),
failure (all benchmark validations),
boundary (single-state benchmark).
Campaign III rule honored: tests only touch tmp_path; the real
`benchmarks/ensemble.json` was regenerated after the final test
run, before committing. mypy clean.

## Védis (integrate)
- Benchmark functions exported; the JSON artifact feeds slice
  125's release gate. Soft voting's better Brier/ECE on the demo
  data matches theory (distributions preserved vs hard votes).

## Scribe
Committed `feat(gjallarbu-124): ensemble benchmarks`; branch
`gjallarbu/campaign-v` pushed to origin at campaign end.

## Artifacts
- `hugrgate/ensemble/benchmarks.py`
- `benchmarks/ensemble.json` (regenerated)
- `hugrgate/ensemble/__init__.py` (exports)
- `tests/test_ensemble_124_benchmarks.py`

## Commands run
- `venv/bin/python -m pytest tests/test_ensemble_124_benchmarks.py -q` → 7 passed
- `venv/bin/python -m mypy hugrgate --ignore-missing-imports --check-untyped-defs --no-incremental` → no errors
- `regenerate_ensemble_benchmarks()` → benchmarks/ensemble.json
