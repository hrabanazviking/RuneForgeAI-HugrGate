# Slice 347 — Trace replay viewer data

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_explain_replay.py`

## What existed

`TraceStore.get_trace()` returned spans, but nothing shaped them for
a viewer: no nesting depths, no offsets, no error rollup, no text
fallback.

## What changed

- `hugrgate/observability/replay.py`: `TraceReplay` —
  `timeline()` with nesting depth (derived from `parent_span_id`),
  ms offsets from trace start, durations, statuses, attributes, and
  events; `to_dict()` viewer document (span count, total duration,
  error count); `render_text()` plain-text waterfall. Orphan spans
  (parent evicted or never recorded) are kept at depth 0 and flagged,
  never dropped; a cycle guard keeps malformed traces renderable.

## Verification

Covered in `tests/test_observability_explain_replay.py` (nesting,
ordering, error marking, unknown-trace rejection, orphan handling,
waterfall rendering); `ruff`/`mypy` clean.
