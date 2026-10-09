# Slice 430 — Rust SDK

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_430_rust_sdk.py` (7 structural tests); crate-internal `#[cfg(test)]` unit tests (6)

## What existed

No Rust client: systems-language integrations had to speak raw HTTP.

## What changed

- `sdks/rust/` — `hugrgate` crate v0.1.0 (`reqwest` blocking +
  `serde`):
  - `src/lib.rs`: `Client::new` / `with_options` (`timeout`,
    `max_retries`, `retry_backoff`); `decide`, `decide_batch`
    (per-item `Result`s), `decide_value`, `health` (never fails on
    transport — reports `reachable`), `backends`, `protocol`;
    `DecisionSpec`/`DecisionResult`/`BackendInfo`/`ProtocolInfo`/
    `ErrorEnvelope` serde types; error taxonomy `HugrGateError`
    (+ `from_envelope`), `Abstention`, `SdkError`, unified `Error`
    enum — all implementing `std::error::Error` + `Display`;
    `protocol_version: "1.0"` on every request;
    `User-Agent: hugrgate-sdk-rs/2.0`; exponential-backoff retry on
    transport errors and HTTP 502/503/504; immediate taxonomy
    errors for caller bugs.
  - 6 embedded unit tests (protocol constant, request
    serialization, envelope mapping, URL normalization, error-enum
    coverage, result deserialization).
  - `Cargo.toml`, `README.md`.

## Verification

The Rust toolchain is not installed in this environment, so the
crate cannot be compiled here — stated plainly rather than
pretended. `tests/test_deveco_430_rust_sdk.py` verifies with
teeth: manifest parses as TOML with the right deps/features, all
public types/methods/error variants exist in source, retry and
wire-format markers present, embedded unit tests reference real
symbols. 7 passed. `cargo test` remains the gate where a Rust
toolchain exists.

## Commands run

- `pytest tests/test_deveco_430_rust_sdk.py` — 7 passed
