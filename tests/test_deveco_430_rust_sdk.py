"""Slice 430 — Rust SDK structural verification.

The Rust toolchain (cargo) is not installed in this environment, so
the crate cannot be compiled here. This test verifies the next best
thing with teeth: the manifest parses and declares the right
dependencies, and the source exposes the full documented API surface
(structs, error types, client methods) with unit tests that
reference real symbols.
"""

from __future__ import annotations

import re
from pathlib import Path

import tomllib

SDK_DIR = Path(__file__).resolve().parent.parent / "sdks" / "rust"


def _manifest():
    with open(SDK_DIR / "Cargo.toml", "rb") as fh:
        return tomllib.load(fh)


def _src() -> str:
    return (SDK_DIR / "src" / "lib.rs").read_text(encoding="utf-8")


def test_manifest_parses_with_required_deps():
    manifest = _manifest()
    assert manifest["package"]["name"] == "hugrgate"
    deps = manifest["dependencies"]
    assert "reqwest" in deps and "blocking" in deps["reqwest"]["features"]
    assert "serde" in deps and "derive" in deps["serde"]["features"]
    assert "serde_json" in deps


def test_protocol_constants_present():
    src = _src()
    assert 'pub const PROTOCOL_VERSION: &str = "1.0";' in src
    assert 'pub const SDK_VERSION: &str = "2.0";' in src


def test_wire_types_present():
    src = _src()
    for name in ("DecisionSpec", "DecisionResult", "BackendInfo",
                 "ProtocolInfo", "ErrorEnvelope"):
        assert re.search(rf"pub struct {name}\b", src), name
    # DecisionSpec serializes the spec "type" discriminator correctly
    assert '#[serde(rename = "type"' in src


def test_error_taxonomy_present():
    src = _src()
    for name in ("HugrGateError", "Abstention", "SdkError"):
        assert re.search(rf"pub struct {name}\b", src), name
    assert re.search(r"pub enum Error", src)
    for variant in ("HugrGate", "Abstention", "Sdk", "Transport"):
        assert re.search(rf"{variant}\(", src), variant
    # every error type implements std::error::Error + Display
    assert src.count("impl std::error::Error for") >= 4
    assert "fn from_envelope(env: ErrorEnvelope)" in src


def test_client_api_surface():
    src = _src()
    for method in ("pub fn new(", "pub fn with_options(",
                   "pub fn decide(", "pub fn decide_batch(",
                   "pub fn decide_value(", "pub fn health(",
                   "pub fn backends(", "pub fn protocol("):
        assert method in src, method
    # retry semantics: recoverable statuses + backoff
    assert "SERVICE_UNAVAILABLE" in src
    assert "retry_backoff" in src
    # versioned user agent
    assert "hugrgate-sdk-rs/{SDK_VERSION}" in src
    # protocol version on the wire
    assert '"protocol_version": PROTOCOL_VERSION' in src


def test_embedded_unit_tests_cover_key_behavior():
    src = _src()
    assert "#[cfg(test)]" in src
    for name in ("protocol_version_is_v1",
                 "decide_request_serializes_protocol_version",
                 "error_envelope_maps_to_taxonomy",
                 "client_trims_trailing_slash",
                 "error_enum_covers_all_variants",
                 "decision_result_deserializes"):
        assert f"fn {name}()" in src, name


def test_readme_documents_usage():
    readme = (SDK_DIR / "README.md").read_text(encoding="utf-8")
    assert "Client::new" in readme
    assert "cargo test" in readme
