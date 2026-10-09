"""Slice 450 — the Developer Ecosystem release gate.

Meta-checks that the campaign's deliverables agree with each
other: one protocol version everywhere, the OpenAPI the CLI
dumps is the app's live schema, every SDK covers the core
operations, every CLI command is documented, and every slice
has its doc. Marked gate: these shell out / build apps.
"""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parent.parent
PROTOCOL_VERSION = "1.0"


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


# --- 1. protocol version consistency --------------------------------------


def test_protocol_version_consistent():
    from hugrgate.protocol import PROTOCOL_VERSION as code_version
    assert code_version == PROTOCOL_VERSION

    from fastapi.testclient import TestClient

    from hugrgate.daemon import DaemonConfig, create_daemon_app
    client = TestClient(create_daemon_app(DaemonConfig()))
    body = client.get("/protocol").json()
    assert body["protocol_version"] == PROTOCOL_VERSION

    # SDKs pin the same wire version.
    assert 'PROTOCOL_VERSION = "1.0"' in _read(
        "sdks/typescript/src/index.ts")
    assert 'pub const PROTOCOL_VERSION: &str = "1.0";' in _read(
        "sdks/rust/src/lib.rs")
    assert 'const ProtocolVersion = "1.0"' in _read(
        "sdks/go/hugrgate.go")


# --- 2. OpenAPI freshness --------------------------------------------------


def test_openapi_cli_matches_live_app():
    from hugrgate.cli import main
    from hugrgate.server import dump_openapi_schema
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert main(["openapi"]) == 0
    cli_schema = json.loads(buf.getvalue())
    assert cli_schema == dump_openapi_schema()
    for path in ("/decide", "/protocol", "/health"):
        assert path in cli_schema["paths"], path


# --- 3. SDK parity matrix ---------------------------------------------------

#: sdk -> source file -> required markers (operation coverage).
PARITY_MATRIX = {
    "python": ("hugrgate/sdk.py",
               ["def decide_batch", "hugrgate-sdk-py/",
                "class HugrGateSDK"]),
    "typescript": ("sdks/typescript/src/index.ts",
                   ["async decide(", "async decideBatch(",
                    "async health()", "async protocol()",
                    "hugrgate-sdk-ts/"]),
    "rust": ("sdks/rust/src/lib.rs",
              ["pub fn decide(", "pub fn decide_batch(",
               "pub fn health(", "pub fn protocol("]),
    "go": ("sdks/go/hugrgate.go",
            ["func (c *Client) Decide(",
             "func (c *Client) DecideBatch(",
             "func (c *Client) Health(",
             "func (c *Client) Protocol("]),
    "c": ("sdks/c/include/hugrgate.h",
           ["hg_client_new(", "hg_client_decide(",
            "hg_client_free(", "hg_error_free("]),
    "mojo": ("sdks/mojo/hugrgate_mojo.mojo",
              ["fn hg_client_new(", "fn hg_client_decide(",
               "fn hg_client_protocol(", "fn hg_client_free("]),
}


def test_sdk_parity_matrix():
    gaps = []
    for sdk, (rel, markers) in PARITY_MATRIX.items():
        text = _read(rel)
        missing = [m for m in markers if m not in text]
        if missing:
            gaps.append(f"{sdk} ({rel}): missing {missing}")
    assert not gaps, "SDK parity gaps:\n" + "\n".join(gaps)


# --- 4. docs coverage -------------------------------------------------------


def _subcommands() -> list[str]:
    from hugrgate.cli import build_parser
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    raise AssertionError("no subparsers found")


def test_docs_cover_every_cli_command():
    docs = " ".join(p.read_text(encoding="utf-8")
                    for p in (REPO / "docs").rglob("*.md"))
    missing = [cmd for cmd in _subcommands()
               if f"hugrgate {cmd}" not in docs and cmd not in docs]
    assert not missing, f"undocumented commands: {missing}"


def test_campaign_slice_docs_complete():
    docs = REPO / "docs" / "campaign-xviii"
    missing = []
    for n in range(426, 450):
        if not list(docs.glob(f"{n}-*.md")):
            missing.append(n)
    assert not missing, f"slices without docs: {missing}"
    assert (docs / "CAMPAIGN-XVIII-COMPLETION-REPORT.md").exists()
