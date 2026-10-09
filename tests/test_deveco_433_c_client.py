"""Slice 433 — C client prototype end-to-end tests.

Compiles the real C client (``gcc -Wall -Wextra -Werror``) plus a
small driver program, then runs it against a scripted Python stub
HTTP server: success, abstention, 422/503 error mapping,
``/protocol``, protocol-version advertisement, and argument
validation. This is a live round-trip through POSIX sockets —
not a mock.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

SDK_DIR = Path(__file__).resolve().parent.parent / "sdks" / "c"
SRC = SDK_DIR / "src" / "hugrgate.c"
DRIVER = SDK_DIR / "e2e" / "smoke.c"
INCLUDE = SDK_DIR / "include"

SPEC = json.dumps({"type": "categorical", "options": ["a", "b"]})
STATE = json.dumps({"f": 1.0})


def _ok_body():
    return {"value": "a", "probability": 1.0,
            "distribution": {"a": 1.0}, "uncertainty": 0.0,
            "accepted": True, "backend": "uniform", "model": "uniform-1.0",
            "latency_ms": 0.1, "calibration_profile": "none",
            "fallback_used": False, "metadata": {}}


class StubHandler(BaseHTTPRequestHandler):
    script: ClassVar[list] = []
    requests: ClassVar[list] = []

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw) if raw else None
        StubHandler.requests.append({
            "path": self.path, "body": body,
            "user_agent": self.headers.get("User-Agent"),
        })
        status, payload = StubHandler.script.pop(0)
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_POST = _handle
    do_GET = _handle

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def stub_server():
    StubHandler.script = []
    StubHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture(scope="module")
def smoke_bin(tmp_path_factory):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not installed")
    outdir = tmp_path_factory.mktemp("c-e2e")
    binary = outdir / "smoke"
    proc = subprocess.run(
        ["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
         f"-I{INCLUDE}", str(SRC), str(DRIVER), "-o", str(binary)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"gcc failed:\n{proc.stderr}"
    return binary


def _run(binary, url, *args, timeout=20):
    proc = subprocess.run([str(binary), url, *args],
                          capture_output=True, text=True, timeout=timeout)
    assert proc.returncode == 0, proc.stderr
    lines = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            lines[key] = value
    return lines


def _url(stub_server):
    host, port = stub_server.server_address
    return f"http://{host}:{port}"


def test_decide_success_round_trip(smoke_bin, stub_server):
    StubHandler.script = [(200, _ok_body())]
    StubHandler.requests = []
    lines = _run(smoke_bin, _url(stub_server), "decide", SPEC, STATE)
    assert lines["STATUS"] == "0", lines
    assert lines["VALUE"] == '"a"', lines
    assert lines["BACKEND"] == "uniform", lines


def test_client_sends_protocol_version(smoke_bin, stub_server):
    StubHandler.script = [(200, _ok_body())]
    StubHandler.requests = []
    _run(smoke_bin, _url(stub_server), "decide", SPEC, STATE)
    req = StubHandler.requests[0]
    assert req["path"] == "/decide"
    assert req["body"]["protocol_version"] == "1.0"
    assert req["user_agent"] == "hugrgate-sdk-c/2.0"


def test_abstention_maps_to_status_10(smoke_bin, stub_server):
    StubHandler.script = [(200, {"abstained": True,
                                 "reason": "below_threshold",
                                 "message": "low confidence"})]
    lines = _run(smoke_bin, _url(stub_server), "decide", SPEC, STATE)
    assert lines["STATUS"] == "10", lines  # HG_ERR_ABSTAINED
    assert "below_threshold" in lines["MSG"], lines


def test_spec_error_maps_to_status_6_not_recoverable(smoke_bin,
                                                     stub_server):
    StubHandler.script = [(422, {"error": {
        "code": "spec_error", "message": "bad spec",
        "recoverable": False, "details": {}}})]
    lines = _run(smoke_bin, _url(stub_server), "decide", SPEC, STATE)
    assert lines["STATUS"] == "6", lines  # HG_ERR_SPEC
    assert lines["RECOVERABLE"] == "0", lines
    assert lines["SVC_CODE"] == "spec_error", lines


def test_unavailable_maps_to_status_9_recoverable(smoke_bin, stub_server):
    StubHandler.script = [(503, {"error": {
        "code": "backend_unavailable", "message": "shedding load",
        "recoverable": True, "details": {}}})]
    lines = _run(smoke_bin, _url(stub_server), "decide", SPEC, STATE)
    assert lines["STATUS"] == "9", lines  # HG_ERR_UNAVAILABLE
    assert lines["RECOVERABLE"] == "1", lines


def test_protocol_endpoint(smoke_bin, stub_server):
    StubHandler.script = [(200, {"protocol_version": "1.0",
                                 "supported_versions": ["1.0"],
                                 "service_version": "0.1.0"})]
    lines = _run(smoke_bin, _url(stub_server), "protocol")
    assert lines["STATUS"] == "0", lines
    assert '"protocol_version": "1.0"' in lines["JSON"], lines


def test_unreachable_service_is_transport_error(smoke_bin):
    # port 1 is never listening: connect must fail fast
    lines = _run(smoke_bin, "http://127.0.0.1:1", "decide", SPEC, STATE)
    assert lines["STATUS"] == "3", lines  # HG_ERR_TRANSPORT
    assert lines["RECOVERABLE"] == "1", lines


def test_https_rejected_as_invalid_arg(smoke_bin):
    lines = _run(smoke_bin, "https://127.0.0.1:1", "decide", SPEC, STATE)
    assert lines["STATUS"] == "1", lines  # HG_ERR_INVALID_ARG
    assert "TLS" in lines["MSG"], lines


def test_null_arguments_rejected(smoke_bin):
    lines = _run(smoke_bin, "http://127.0.0.1:1", "nullargs")
    assert lines["STATUS"] == "1", lines  # HG_ERR_INVALID_ARG
