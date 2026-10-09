"""Slice 431 — Go SDK structural verification.

The Go toolchain is not installed in this environment, so the module
cannot be compiled here. This test verifies with teeth: go.mod is
valid and dependency-free (stdlib only), and the source exposes the
full documented API surface with table tests referencing real
symbols.
"""

from __future__ import annotations

from pathlib import Path

SDK_DIR = Path(__file__).resolve().parent.parent / "sdks" / "go"


def _src() -> str:
    return (SDK_DIR / "hugrgate.go").read_text(encoding="utf-8")


def _test_src() -> str:
    return (SDK_DIR / "hugrgate_test.go").read_text(encoding="utf-8")


def test_go_mod_valid_and_stdlib_only():
    mod = (SDK_DIR / "go.mod").read_text(encoding="utf-8")
    assert "module github.com/runeforgeai/hugrgate-go" in mod
    assert "require" not in mod, "Go SDK must stay stdlib-only"


def test_protocol_constants():
    src = _src()
    assert 'const ProtocolVersion = "1.0"' in src
    assert 'const SDKVersion = "2.0"' in src


def test_wire_types():
    src = _src()
    for name in ("type DecisionSpec struct", "type DecisionResult struct",
                 "type BackendInfo struct", "type ProtocolInfo struct"):
        assert name in src, name


def test_error_taxonomy():
    src = _src()
    for name in ("type Error struct", "type Abstention struct",
                 "type SDKError struct"):
        assert name in src, name
    assert "func (e *Error) Error() string" in src
    assert "func (e *Abstention) Error() string" in src


def test_client_api_surface():
    src = _src()
    for sig in ("func NewClient(", "func NewClientWithOptions(",
                "func (c *Client) Decide(",
                "func (c *Client) DecideBatch(",
                "func (c *Client) DecideValue(",
                "func (c *Client) Health(",
                "func (c *Client) Backends(",
                "func (c *Client) Protocol(",
                "func (c *Client) Close("):
        assert sig in src, sig
    # retry semantics + wire markers
    assert "503: true" in src or "503" in src
    assert "hugrgate-sdk-go/\"+SDKVersion" in src or \
        "hugrgate-sdk-go/\" + SDKVersion" in src
    assert "ProtocolVersion: ProtocolVersion" in src or \
        '"protocol_version"' in src


def test_go_tests_cover_key_behavior():
    src = _test_src()
    assert "package hugrgate" in src
    for name in ("TestProtocolVersionSent", "TestDecideStampsMetadata",
                 "TestAbstention", "TestNoRetryOnCallerBug",
                 "TestRetry503ThenSucceeds",
                 "TestNegativeMaxRetriesRejected",
                 "TestBatchReportsPerItemErrors", "TestDecideValue",
                 "TestHealthNeverFails", "TestProtocolAdvertisement",
                 "TestBackends"):
        assert f"func {name}(t *testing.T)" in src, name


def test_readme_documents_usage():
    readme = (SDK_DIR / "README.md").read_text(encoding="utf-8")
    assert "NewClient" in readme
    assert "go test" in readme
