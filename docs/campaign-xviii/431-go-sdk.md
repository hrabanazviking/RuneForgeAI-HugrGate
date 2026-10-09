# Slice 431 — Go SDK

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_431_go_sdk.py` (7 structural tests); `sdks/go/hugrgate_test.go` (12 Go tests)

## What existed

No Go client: Go services had to speak raw HTTP.

## What changed

- `sdks/go/` — `github.com/runeforgeai/hugrgate-go` module,
  **stdlib only** (no third-party dependencies):
  - `hugrgate.go`: `NewClient` / `NewClientWithOptions`
    (`Timeout`, `MaxRetries`, `RetryBackoff`); `Decide`,
    `DecideBatch` (per-item `BatchOutcome`s), `DecideValue`,
    `Health` (never fails on transport — reports `reachable`),
    `Backends`, `Protocol`, `Close`; `DecisionSpec`/
    `DecisionResult`/`BackendInfo`/`ProtocolInfo` types;
    error taxonomy `*Error` (code/message/recoverable/details),
    `*Abstention`, `*SDKError`; `protocol_version: "1.0"` on every
    request; `User-Agent: hugrgate-sdk-go/2.0`; exponential-backoff
    retry on transport errors and HTTP 502/503/504.
  - `hugrgate_test.go`: 12 tests against `httptest` scripted
    servers (protocol version + User-Agent, metadata stamping,
    abstention, no-retry-on-422, 503-retry, config validation,
    batch per-item errors, health never-fails, protocol/backends).
  - `go.mod`, `README.md`.

## Verification

The Go toolchain is not installed in this environment, so the
module cannot be compiled here — stated plainly.
`tests/test_deveco_431_go_sdk.py` verifies: go.mod valid and
stdlib-only, all public types/methods/error types present, retry
and wire markers present, Go tests reference real symbols.
7 passed. `go test ./...` remains the gate where a Go toolchain
exists.

## Commands run

- `pytest tests/test_deveco_431_go_sdk.py` — 7 passed
