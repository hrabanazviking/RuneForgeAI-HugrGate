# Slice 195 — Edge telemetry lite

**Date:** 2026-10-09 · **Tests:** `tests/test_edge_telemetry.py` (13 tests, green)

## What existed before

No metrics story for edge nodes — either ship a full observability
stack (too heavy for a Pi Zero) or fly blind.

## What was built

`hugrgate/edge/telemetry.py` — `TelemetryLite`:

- **Bounded ring buffer** (default 256 events): memory is capped no
  matter the uptime; evictions are counted (`dropped_events`), not
  hidden.
- **Counters + gauges** for cheap aggregates without per-event cost.
- **Numeric-only values by construction**: `record()` rejects
  strings, dicts, lists, bools, None, and NaN — prompts, states, and
  PII *cannot* enter telemetry, mirroring `PrivacyGuard`'s retention
  rules. Tags must be `str → str`.
- **Compact export**: one JSON-serializable dict (counters, gauges,
  events, drop count) for occasional uplink or the benchmark
  harness; `recent(n)` newest-first snapshots; `reset()` clears
  payload but keeps the sequence counter.
- Thread-safe; injectable clock for deterministic tests.

## Integration

- New module in the `edge` layer; maps + inventory regenerated;
  taxonomy unit row extended. Feeds slice 196's benchmark artifacts.

## Validation notes (Execution Law rule 13)

Uplink transport and retention policy are deployment decisions —
this module only guarantees boundedness and numeric-only payloads.

## Verification

- `pytest tests/test_edge_telemetry.py` — 13 passed
- `ruff check`, `mypy hugrgate/edge/` — clean
