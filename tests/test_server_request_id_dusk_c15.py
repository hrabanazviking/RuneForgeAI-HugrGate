"""Slice 15 (dusk, Wave C) — ``X-Request-ID`` propagation.

The service echoes a client-supplied ``X-Request-ID`` response header
and mints one (uuid4 hex) when the client sent none, so every request
is traceable end to end. The request ID is also part of the
per-request log line emitted by the middleware.
"""

from __future__ import annotations

import logging
import re

from fastapi.testclient import TestClient

from hugrgate.server import REQUEST_ID_HEADER, create_app

_DECIDE_BODY = {
    "spec": {"type": "categorical", "options": ["a", "b"]},
    "state": {"signal": 0.7},
}


def _client() -> TestClient:
    return TestClient(create_app())


def test_echoes_client_supplied_request_id():
    client = _client()
    response = client.get("/health", headers={REQUEST_ID_HEADER: "client-req-9"})
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "client-req-9"


def test_generates_request_id_when_missing():
    client = _client()
    response = client.get("/health")
    generated = response.headers.get(REQUEST_ID_HEADER)
    assert generated, "expected a generated X-Request-ID"
    assert re.fullmatch(r"[0-9a-f]{32}", generated), generated


def test_generated_request_ids_are_unique():
    client = _client()
    ids = {client.get("/health").headers[REQUEST_ID_HEADER]
           for _ in range(3)}
    assert len(ids) == 3


def test_request_id_round_trips_through_decide():
    client = _client()
    response = client.post("/decide", json=_DECIDE_BODY,
                           headers={REQUEST_ID_HEADER: "decide-42"})
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "decide-42"
    # And a generated one on the happy path too.
    response2 = client.post("/decide", json=_DECIDE_BODY)
    assert response2.status_code == 200
    assert response2.headers.get(REQUEST_ID_HEADER)


def test_request_id_present_on_error_responses():
    client = _client()
    echoed = client.post("/decide", content=b"not json",
                         headers={REQUEST_ID_HEADER: "err-case"})
    assert echoed.status_code in (400, 422)
    assert echoed.headers[REQUEST_ID_HEADER] == "err-case"
    generated = client.post("/decide", json={})
    assert generated.status_code in (400, 422)
    assert generated.headers.get(REQUEST_ID_HEADER)


def test_request_id_included_in_log_fields(caplog):
    client = _client()
    with caplog.at_level(logging.INFO, logger="hugrgate.server"):
        response = client.get("/health",
                              headers={REQUEST_ID_HEADER: "log-probe"})
    assert response.status_code == 200
    records = [rec for rec in caplog.records if rec.name == "hugrgate.server"]
    assert records, "expected a per-request log record"
    assert "request_id=log-probe" in records[-1].getMessage()
