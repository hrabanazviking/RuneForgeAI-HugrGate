# Slice 010 — Determinism audit

**Date:** 2026-10-09 · **Tests:** `tests/test_determinism_contract.py` (5 tests)

## Audit method

- Searched the package for `random` / `os.urandom` / `uuid` /
  builtin-`hash()` in decision paths: **none found**. Time is used only
  for latency measurement and provenance timestamps (observations, not
  decisions).
- Checked every `set(...)` in decision-affecting code: all are either
  `sorted(...)`, equality comparisons, or token-overlap maxima with
  insertion-ordered tie-breaking — no hash-order leaks.
- `cache_key` uses `json.dumps(sort_keys=True)` + SHA-256:
  hash-seed-stable.
- `negotiate.select_backend` sorts by `(-quality, latency, name)`:
  fully deterministic.
- sklearn backends default to fixed `random_state` (42); training is
  reproducible for fixed data.

## Contract (pinned by tests)

Deterministic: `value`, `probability`, `distribution`, `uncertainty`,
backend selection, benchmark quality metrics — identical across
repeated runs **and** across `PYTHONHASHSEED` values (verified in
subprocesses with seeds 0/1/42/12345).

Explicitly non-deterministic (measurements, not decisions, excluded
from the contract): `latency_ms` (+ benchmark latency percentiles /
throughput), provenance `timestamp`s, report `generated_at`,
`platform` metadata, service uptime.

## Verification

`venv/bin/python -m pytest tests/test_determinism_contract.py -q` —
5 passed. No code changes were needed: the audit confirmed the
existing implementation already meets the contract; the value of the
slice is the pinned guarantee.
