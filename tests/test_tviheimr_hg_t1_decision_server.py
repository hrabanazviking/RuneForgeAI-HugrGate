"""HG-T1 gate tests — decision-server form.

Gate (roadmap): server answers judgment requests and event batches on
localhost with the existing test suite still green; startup/shutdown
are clean and boring.

These tests spin the real server on an ephemeral localhost port and
talk real HTTP to it (stdlib urllib — no test-client dependency).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from hugrgate.decision_server import DecisionServer

pytestmark = pytest.mark.integration


@pytest.fixture()
def server():
    srv = DecisionServer(host="127.0.0.1", port=0)
    srv.start()
    yield srv
    srv.stop()


def _call(server, method, path, body=None):
    host, port = server.address
    url = f"http://{host}:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


_SPEC = {"type": "categorical", "options": ["routine", "escalate"]}


def test_health_endpoint(server):
    status, body = _call(server, "GET", "/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["slice"] == "HG-T1"
    assert "keyword" in body["backends"]


def test_judgment_request(server):
    status, body = _call(server, "POST", "/judge", {
        "state": {"text": "escalate this incident now"},
        "spec": _SPEC, "backend": "keyword"})
    assert status == 200
    assert body["value"] == "escalate"
    assert body["backend"] == "keyword"
    assert 0.0 <= body["probability"] <= 1.0


def test_decide_alias(server):
    status, body = _call(server, "POST", "/decide", {
        "state": {"text": "routine daily summary"}, "spec": _SPEC,
        "backend": "keyword"})
    assert status == 200
    assert body["value"] in _SPEC["options"]


def test_event_batch_intake(server):
    status, body = _call(server, "POST", "/events", {
        "spec": _SPEC, "backend": None,
        "events": [
            {"text": "escalate the outage"},
            {"text": "routine heartbeat"},
            "not-an-object",
        ]})
    assert status == 200
    assert body["accepted"] == 3
    verdicts = body["verdicts"]
    assert len(verdicts) == 3  # nothing dropped silently
    assert verdicts[0]["ok"] is True
    assert verdicts[1]["ok"] is True
    assert verdicts[2]["ok"] is False
    assert "error" in verdicts[2]


def test_event_batch_bare_list(server):
    status, body = _call(server, "POST", "/events",
                         [{"text": "hello"}, {"text": "world"}])
    assert status == 200
    assert body["accepted"] == 2
    assert all(v["ok"] for v in body["verdicts"])


def test_bad_requests_are_json_errors(server):
    status, body = _call(server, "POST", "/judge", {"state": {}})
    assert status == 400
    assert "error" in body
    status, body = _call(server, "GET", "/nope")
    assert status == 404
    assert "error" in body


def test_counters_and_clean_shutdown(server):
    _call(server, "POST", "/judge",
          {"state": {"text": "x"}, "spec": _SPEC})
    status, body = _call(server, "GET", "/health")
    assert status == 200
    assert body["judgments"] >= 1
    server.stop()  # boring: no exception, thread joined
    assert server._thread is None
