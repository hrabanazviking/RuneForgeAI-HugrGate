# Slice 428 — Python SDK v2

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_428_sdk.py` (13 tests)

## What existed

`hugrgate.client.HugrGateClient` (v1, slice 43) was the only Python
client: no context-manager support, no retries, and HTTP error
responses leaked raw `httpx.HTTPStatusError` instead of the HugrGate
taxonomy. Production integrations had to hand-roll all of that.

## What changed

- `hugrgate/sdk.py` (new): `HugrGateSDK`, a strict superset of the
  v1 client (v1 untouched, keeps working):
  - context-manager use with idempotent `close()`,
  - exponential-backoff retry (`max_retries`, `retry_backoff_s`) on
    **recoverable** faults only — transport errors and HTTP
    502/503/504; caller bugs (`spec_error` 422s) are never retried,
  - HTTP error envelopes mapped back onto the taxonomy
    (`SpecError`, `BackendUnavailable`, ...; unparseable bodies get a
    generic `BackendError` instead of leaking httpx),
  - `decide_batch()` returning per-item results/errors (a batch is a
    report, never a transaction), `decide_value()` convenience,
  - versioned `User-Agent: hugrgate-sdk-py/2.0` header,
  - `SDKError` (`sdk_error`, recoverable) when the transport is
    exhausted and in-process fallback is disabled.
- `pyproject.toml`: `pydantic>=2.0` added to the `server` extra
  (slice 427 made it a direct import of `hugrgate.server`);
  `tests/test_dependency_rules.py` provider map updated.
- Deliberately *not* exported from `hugrgate/__init__`: importing it
  would drag `httpx` (a `server`-extra dependency) into the base
  install. Import it as `from hugrgate.sdk import HugrGateSDK`.

## Verification

13 new tests (User-Agent, context-manager close/idempotence,
retry-then-succeed, give-up-as-`SDKError`, no-retry-on-422,
503-retry, taxonomy mapping, unparseable-body fallback,
per-item batch errors, `decide_value`, config validation,
in-process gate path); `ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_428_sdk.py` — 13 passed
