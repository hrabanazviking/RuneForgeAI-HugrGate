# Slice 382 — Notification gating

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_382_notify.py` (8 tests)

## What already existed

The observability layer defines alert severities and dedup
philosophy (`AlertManager`), but nothing gated outbound
notifications from agentic loops — a flapping escalator could page
fifty times.

## What was built

- `hugrgate/agents/notify.py` — `NotificationGate`: per-channel
  `ChannelConfig` (enable/disable, minimum severity, per-minute
  rate limit, dedup window). `notify()` checks channel known →
  enabled → severity ≥ minimum → dedup-key suppression → rate
  limit, then calls a pluggable `sender` (the gate never touches
  the network). Sender failures are decisions (`sender_failed`),
  not exceptions. Successful sends publish `notify.sent` on the
  bus with trace continuity.
- Severity ladder is the observability `SEVERITIES` tuple — one
  urgency vocabulary across the system.

## Verification

`pytest tests/test_agents_382_notify.py` — 8 passed (severity
filter, dedup window, rate refill, disabled/unknown channels,
sender failure, per-channel stats). `ruff check` clean, `mypy`
clean.
