# Slice 440 — Backend conformance kit

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_440_backend_conformance.py` (11 tests)

## What existed

The plugin SDK (slice 439) validated the *interface*; nothing
exercised a backend's *behavior* — a backend returning
out-of-space values or raising raw exceptions would only fail in
production.

## What changed

- `hugrgate/conformance.py` (new): `run_backend_conformance`
  battery — interface shape, `supports()` booleans across all
  four spec types, `evaluate()` result well-formedness
  (distribution sums to 1, probabilities in [0,1], decided value
  inside the spec's own `value_space()`, numeric exempted from
  distribution checks), error-taxonomy on invalid input,
  `health`/`privacy_properties`/`calibration_info` dict shapes,
  sane latency/cost estimates. `ConformanceReport` with
  `to_dict()`; `assert_conformance` raises `ConformanceError`.
- `hugrgate/cli.py`: `hugrgate check-backend NAME` (registry
  first, plugin loader fallback), table/json output, exit 1 on
  failure with the failure list.
- `tests/test_dependency_rules.py`: `hugrgate.conformance`
  joins the SERVICE layer.

## Weaknesses the kit found in existing code (fixed here)

- The kit initially second-guessed binary value spaces instead
  of using `DecisionSpec.value_space()` — fixed to use the
  contract's own authority.
- The kit demanded non-empty distributions for numeric specs,
  where the built-in `uniform` backend legitimately returns
  `{}` — numeric is now exempt.
- The kit failed backends that *ignore* bad state; silence is
  not a taxonomy violation, so the check now only fails on
  non-taxonomy raises.

## Verification

11 tests: both built-in backends fully conformant; skewed
distribution, raw-exception, and out-of-space backends fail
with named checks; `assert_conformance` raises the taxonomy
error; report JSON-serializable; CLI exit codes. `ruff`/`mypy`
clean.

## Commands run

- `pytest tests/test_deveco_440_backend_conformance.py` — 11 passed
