# Slice 162 — Model capability probing

## Skald (what already existed)
- No acceptance test for model+runtime pairings. Slices 160–161 find
  candidates; nothing verified they actually *work* before use.

## Rúnhild (design)
`hugrgate/runtimes/probe.py::probe_runtime`: a five-probe battery
(load_cycle, generate, embed, classify, tokenize) returning a
`CapabilityReport` with per-probe pass/fail/skip, latency, summary
text, and a JSON-able dict. Unadvertised capabilities are *skipped*
(via an internal `_SkipProbe` that bypasses the never-raise catch),
failures are recorded with their exception message — the report
distinguishes "can't" from "broken". `report.ok` requires zero
failures *and* at least one pass. Unknown probe names are a caller
bug → `HugrGateError`.

## Eldra (what was built)
- `hugrgate/runtimes/probe.py` (new): `probe_runtime`,
  `CapabilityReport`, `ProbeResult`, `PROBE_NAMES`.
- `tests/test_localrt_162_probe.py` (new, 11 tests): full pass,
  skips, recorded failures, subset selection, report shape.
- Taxonomy doc updated.

## Sólrún (tests)
`pytest tests/test_localrt_162_probe.py -q` → 11 passed. `ruff`
clean, `mypy` clean (full gate in slice 175).

## Védis (integration)
- Pure addition; designed as the gate between discovery (160–161)
  and residency/warmup (169–171), and as input to health probes
  (172) and the conformance suite (173).

## Scribe
Commit `feat(gjallarbu-162): model capability probing` on
`gjallarbu/campaign-vii`.
