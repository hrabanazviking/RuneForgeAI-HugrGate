# Slice 328 — Trace architecture

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_trace.py` (24 tests)

## What existed

No distributed-trace model: per-decision timing lived in ad-hoc log
lines, and there was no notion of parent/child spans, sampling, or a
bounded span store.

## What changed

- `hugrgate/observability/trace.py`:
  - `Span` — W3C-format ids, validated attributes, events, causal
    links, error status, finish-once lifecycle. **Privacy gate:**
    attribute keys that could carry payload/PII (`state`, `value`,
    `input`, `prompt`, `payload`, `pii`, …) raise `TraceError` —
    spans carry metadata, never payload (same law as
    `hugrgate.log`'s `PRIVACY_RULE`).
  - `ProbabilisticSampler` — head-based, deterministic per trace id:
    traces are kept whole or dropped whole, never ragged.
  - `TraceStore` — bounded, thread-safe, with `get_trace()` trace
    reassembly in start-time order.
  - `Tracer` — `trace()` context manager + `@traced` decorator,
    ambient per-thread span, error recording that re-raises (and,
    since slice 330, first-error-wins so nested builders' specific
    taxonomy codes survive).

## Verification

24 tests (forbidden payload keys, sampler determinism and 50/50
split, eviction bounds, reassembly order, thread safety); `ruff`/`mypy`
clean.
