# Slice 426 — Stable protocol v1

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_426_protocol.py` (25 tests), `tests/test_errors.py` (extended)

## What existed

The HTTP wire protocol was implicit: the client sent `{"spec", "state",
"backend_name", "context"}` and the service answered with the bare
decision JSON, an abstention envelope, or `{"error": {...}}` — with no
version anywhere. A future protocol change would have been
undetectable at the wire level, and clients had no way to ask the
service what it speaks before sending a doomed request.

## What changed

- `hugrgate/protocol.py` (new): single source of truth for the
  versioned wire protocol — `PROTOCOL_VERSION = "1.0"`,
  `parse_protocol_version()`, `negotiate_version()` (absent field →
  v1; any `1.x` minor → canonical `"1.0"`; other majors →
  `ProtocolError`), and a frozen `Envelope` dataclass with
  `to_dict()`/`from_dict()` round-tripping plus `build_envelope()`.
- `hugrgate/errors.py`: `ProtocolError` (`protocol_error`,
  not recoverable — version skew is a caller bug, never a transient
  fault) plus the rest of the Campaign XVIII taxonomy up front:
  `SDKError`, `PluginError`, `ConformanceError`, `ConfigError`,
  `ScaffoldError` with deliberate codes and recoverable flags.
- `hugrgate/server.py`: new `GET /protocol` endpoint advertising
  `protocol_version`, `supported_versions`, `service_version`;
  `/decide` negotiates the version **before** spec/policy parsing and
  stamps the negotiated version into `result.metadata`; unsupported
  or malformed versions return HTTP 422 with the `protocol_error`
  taxonomy code.
- `hugrgate/client.py`: every `decide` payload now carries
  `protocol_version`; new `client.protocol()` probes `/protocol`
  (with in-process and in-process-fallback modes that never touch
  the network).

## Verification

25 new tests (negotiation success/failure/boundary, envelope
round-trip, `/protocol` advertisement, legacy-request version
stamping, 422 rejection with the taxonomy code, client version
advertisement, client probe modes); error-taxonomy tests extended
(codes, recoverable flags, raise-site audit); `ruff` and `mypy`
clean.

## Commands run

- `pytest tests/test_deveco_426_protocol.py tests/test_errors.py` — 37 passed
