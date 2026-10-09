# Slice 254 — Latency injection

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_latency.py` (7 tests, green)

## What existed before

`FaultyBackend` (slices 252–253) could crash or hang a backend, and
`StubBackend` had a fixed `delay` — but there was no *scripted,
seeded, measurable* latency fault: no way to assert "this backend
got 50 ms slower" and prove the number against a clean baseline.

## What was built

Wired the `LATENCY` fault mode in `hugrgate/chaos/backend_faults.py`:

- `_inject_latency` sleeps `params["delay_s"]` seconds, then
  delegates to the wrapped backend — the sleep models queueing /
  network delay *before* the backend starts work.
- `delay_s` is required and validated at arm time (number ≥ 0;
  `0` is an honest no-op). `_WIRED_MODES` is now
  `(CRASH, HANG, LATENCY)`; crash still outranks latency.

## Measurement artifact (real numbers, not invented)

`benchmarks/chaos-latency-254.json` — produced by running the
slice's measurement script against the worktree with the repo venv
(`python /tmp/measure_latency_254.py`; script retained at
`/tmp/measure_latency_254.py`):

- **Config:** `delay_s=0.05`, rate 1.0, seed 254, 30 measured calls
  (+3 warmup), same wrapper clean for the baseline.
- **Baseline:** mean ≈ 0.0000046 s (max < 0.05 s).
- **Injected:** mean ≈ 0.0502 s, min ≥ 0.05 s on every call.
- **Comparison:** mean delta **0.05020 s** vs 0.05 s configured —
  the injector is accurate to ~0.2 ms; mean ratio ≈ 10820×
  (the baseline is microseconds).

The artifact carries `schema: hugrgate.chaos-latency/1`, timestamp,
config, environment (python, platform, git sha), and a
regeneration note.

## Integration

- Observed latency is measured by the caller with
  `time.monotonic` — never `time.time`, so clock adjustments
  cannot corrupt the measurement (see slice 265).
- Provenance: latency faults count in `fault_stats()["latency"]`.
- No new error class: misuse raises `SpecError` at arm time.

## Verification

- 7 tests: injected delay observed on every call (≥ 0.05 s, mean <
  0.6 s); clean-wrapper baseline fast; rate 0 → no delay; param
  validation; seeded delayed-call pattern reproducibility;
  crash-over-latency priority (no 5 s sleep); committed artifact
  schema + self-consistency (mean delta within [0.04, 0.2] s).
- `ruff check` clean; `benchmarks/CHECKSUMS.sha256` extended with the
  new artifact.
