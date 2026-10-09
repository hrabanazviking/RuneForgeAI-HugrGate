# Slice 009 — Logging architecture

**Date:** 2026-10-09 · **Tests:** `tests/test_logging.py` (9 tests)

## Design

New module `hugrgate.log` (state/observability layer):

- `get_logger(name)` → `hugrgate.<name>` child loggers.
- The `hugrgate` root logger installs only a `NullHandler` and sets
  no level: importing the library never emits output and never hijacks
  the host application's logging.
- `configure_logging(level, stream, json_format)` is the explicit
  opt-in; idempotent (replaces its own handler instead of stacking).
- `JsonFormatter`: one JSON object per record
  (`timestamp`, `level`, `logger`, `message`, optional `exception`).
- **Privacy rule** (module docstring + enforced by test): log metadata,
  never payload — decision `state` dicts and result `value`s must never
  appear in log records.

Level discipline: `DEBUG` per-decision internals, `INFO` lifecycle and
breaker transitions, `WARNING` recoverable failures and privacy blocks,
`ERROR` unrecoverable faults.

## Instrumentation

| Module | Events logged |
|---|---|
| `core` | backend failure (`WARNING`, name + exception type only), abstention (`DEBUG`, spec type only) |
| `fallback` | failover to next backend (`WARNING`, backend name + error code) |
| `circuit` | open / half-open / close transitions (`INFO`, breaker name) |
| `privacy` | remote backend blocked (`WARNING`, backend name), policy exclusion (`DEBUG`) |
| `cache` | hit / miss / expiry (`DEBUG`, no keys logged) |
| `daemon` | startup with bind address (`INFO`), graceful shutdown (`INFO`) |

Daemon CLI gained `--log-level` (DEBUG/INFO/WARNING/ERROR) and
`--log-json`.

## Verification

`venv/bin/python -m pytest tests/test_logging.py -q` — 9 passed,
including a negative privacy test (a state containing a fake SSN is
decided through a failing backend; no record contains the SSN).
mypy cold-cache clean; full suite 401 passed.
