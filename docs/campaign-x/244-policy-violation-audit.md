# Slice 244 — Policy violation audit

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_audit.py` (15 tests)

## What existed

Privacy denials (backend blocks, secret detections, jurisdiction
violations, local-only rejections) raised errors and logged a
line, but left no tamper-evident record — an operator could not
answer "who was blocked, when, and why".

## What changed

- New module `hugrgate/privacy_audit.py`:
  - `PrivacyAuditEvent` / `PrivacyAuditLog` — append-only,
    hash-chained event log (`record`, `verify`, `events`,
    `to_dict`/`from_dict`). Any edit or deletion of an event
    breaks `verify()`.
  - `FileAuditSink` — append-only JSON-lines durability.
  - Sink errors are logged and swallowed: auditing must never
    break the guarded operation.
- `PrivacyGuard` gained an optional `audit_log` (slice 244):
  every denial in `check_backend` (guard-level, class-level,
  jurisdiction), `enforce_local_only` strict mode, and
  `check_no_secrets` records a hash-chained event. Guards
  without a log behave exactly as before.

## Verification

- `pytest tests/test_privacy_audit.py` — 15 passed (chaining,
  tamper/deletion detection, sink round-trip, broken-sink
  resilience, guard integration for all four denial kinds).
- `mypy` and `ruff` clean; no import cycles.
