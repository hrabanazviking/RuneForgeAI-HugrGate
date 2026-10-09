# Slice 172 — Model health probes

## Skald (what already existed)
- `LocalRuntime.health()` was a self-report (`ok`/`degraded`/
  `unavailable`); nothing verified the report with a real inference.

## Rúnhild (design)
`hugrgate/runtimes/health_probes.py`: a probe battery run by
`probe_runtime` (single) and `probe_all` (parallel over a registry).
Four probes: `LivenessProbe` (the runtime's own `health()`),
`ModelLoadedProbe` (a model is resident), `InferenceProbe` (a minimal
real inference per advertised capability — catches engines that
report healthy but are wedged), `LatencyProbe(warn_s, crit_s)`
(timed inference against thresholds). Probes never raise: crashes
are recorded as failed `ProbeResult`s. `HealthReport.ok` is true
only when every probe passes.

## Eldra (what was built)
- `hugrgate/runtimes/health_probes.py` (new): 4 probes,
  `HealthProbe` ABC, `ProbeResult`, `HealthReport`, `probe_runtime`,
  `probe_all`, `DEFAULT_PROBES`.
- `tests/test_localrt_172_health_probes.py` (new, 13 tests).
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_172_health_probes.py -q` → 13 passed.
`ruff` clean, `mypy` clean.

## Védis (integration)
- Pure addition. Composes with warmup (169) for bring-up checks and
  with eviction (171) to shed unhealthy residents.

## Scribe
Commit `feat(gjallarbu-172): model health probes` on
`gjallarbu/campaign-vii`.

## Real-world validation still needed
- Probe battery against real GPU runtimes (inference probe cost on
  large models; threshold tuning per engine).
