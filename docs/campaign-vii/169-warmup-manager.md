# Slice 169 — Model warmup manager

## Skald (what already existed)
- `LocalRuntime.warmup()` and `Backend.warmup()` were per-instance
  no-op hooks (slices 151, 019); nothing orchestrated a fleet warmup,
  recorded results, or measured baselines.

## Rúnhild (design)
`hugrgate/runtimes/warmup.py`: `WarmupManager` with three entry
points — `warmup_runtime` (load → runtime `warmup()` hook → `repeat`
timed probes per advertised capability, recording p50/p95 latencies
in `WarmupResult`), `warmup_all` (parallel over a `RuntimeRegistry`,
never raises, optional per-runtime `ModelRef` map), and
`warmup_backend` (legacy `Backend.warmup()` hook, so the old stack
warms through the same manager). Idempotent via a warmed-set;
`rewarm`/`reset` control re-runs; failures recorded with the
exception class + message, never raised.

## Eldra (what was built)
- `hugrgate/runtimes/warmup.py` (new): `WarmupManager`,
  `WarmupResult` (with `latency_p50_s`/`latency_p95_s`/`to_dict`).
- `tests/test_localrt_169_warmup.py` (new, 15 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_169_warmup.py -q` → 15 passed.
`ruff` clean, `mypy` clean.

## Védis (integration)
- Pure addition; runtimes and backends untouched. The manager
  consumes only public contracts (`load`, `warmup`, `generate`,
  `embed`, `classify`, `info`).

## Scribe
Commit `feat(gjallarbu-169): model warmup manager` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Parallel `warmup_all` against real GPU runtimes (thread-safety of
  concurrent `load()` on actual engines).
