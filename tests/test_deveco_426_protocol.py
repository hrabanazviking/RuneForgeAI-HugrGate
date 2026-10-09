"""Slice 426 — stable protocol v1.

Tests the versioned wire protocol: version parsing/negotiation,
envelope serde, the ``/protocol`` advertisement endpoint, version
stamping on ``/decide`` responses, and rejection of unsupported
versions with the ``protocol_error`` taxonomy code.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hugrgate import DecisionSpec
from hugrgate.errors import ProtocolError
from hugrgate.protocol import (
    PROTOCOL_VERSION,
    Envelope,
    build_envelope,
    negotiate_version,
    parse_protocol_version,
)
from hugrgate.server import create_app


def _spec() -> DecisionSpec:
    return DecisionSpec.from_dict({"type": "categorical",
                                   "options": ["a", "b"]})


# --- version parsing / negotiation -------------------------------------------

def test_parse_protocol_version_ok():
    assert parse_protocol_version("1.0") == (1, 0)
    assert parse_protocol_version("1.12") == (1, 12)


@pytest.mark.parametrize("bad", ["1", "v1.0", "1.0.0", "", None, 1.0,
                                  "a.b", "1.-2", "1. 2"])
def test_parse_protocol_version_rejects_malformed(bad):
    with pytest.raises(ProtocolError) as exc:
        parse_protocol_version(bad)
    assert exc.value.code == "protocol_error"
    assert exc.value.recoverable is False


def test_negotiate_absent_means_v1():
    assert negotiate_version(None) == PROTOCOL_VERSION


def test_negotiate_minor_versions_are_wire_compatible():
    assert negotiate_version("1.0") == "1.0"
    assert negotiate_version("1.99") == "1.0"


@pytest.mark.parametrize("bad", ["2.0", "0.9", "3.1"])
def test_negotiate_rejects_other_majors(bad):
    with pytest.raises(ProtocolError) as exc:
        negotiate_version(bad)
    assert "unsupported protocol_version" in exc.value.message


# --- envelope -----------------------------------------------------------------

def test_envelope_round_trip():
    env = Envelope(payload={"ok": True}, protocol_version="1.0",
                   server_version="0.1.0")
    data = env.to_dict()
    assert data["protocol_version"] == "1.0"
    assert data["payload"] == {"ok": True}
    assert data["service_version"] == "0.1.0"
    assert Envelope.from_dict(data) == env


def test_envelope_from_dict_malformed():
    with pytest.raises(ProtocolError):
        Envelope.from_dict({"nope": 1})


def test_build_envelope():
    data = build_envelope({"x": 1})
    assert data["protocol_version"] == PROTOCOL_VERSION
    assert data["payload"] == {"x": 1}


# --- service integration -------------------------------------------------------

@pytest.fixture()
def app_client():
    return TestClient(create_app())


def test_protocol_endpoint_advertises_versions(app_client):
    body = app_client.get("/protocol").json()
    assert body["protocol_version"] == PROTOCOL_VERSION
    assert PROTOCOL_VERSION in body["supported_versions"]
    assert body["service_version"]


def _decide(app_client, protocol_version):
    payload: dict = {"spec": _spec().to_dict(),
                     "state": {"f": 1.0}}
    if protocol_version is not None:
        payload["protocol_version"] = protocol_version
    return app_client.post("/decide", json=payload)


def test_decide_legacy_request_gets_version_stamp(app_client):
    resp = _decide(app_client, None)
    assert resp.status_code == 200
    assert resp.json()["metadata"]["protocol_version"] == "1.0"


def test_decide_v1_request_accepted(app_client):
    resp = _decide(app_client, "1.0")
    assert resp.status_code == 200
    assert "decision" in resp.json() or "value" in resp.json()


def test_decide_unsupported_version_rejected_with_taxonomy_code(app_client):
    resp = _decide(app_client, "2.0")
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "protocol_error"
    assert err["recoverable"] is False


def test_decide_malformed_version_rejected(app_client):
    resp = _decide(app_client, "banana")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "protocol_error"


def test_client_sends_protocol_version():
    """The Python client advertises its protocol version on /decide."""
    from hugrgate.client import HugrGateClient

    seen: dict = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            payload = seen["payload"]
            assert payload["protocol_version"] == PROTOCOL_VERSION
            return {"value": "a", "probability": 1.0,
                    "distribution": {"a": 1.0}, "metadata": {}}

    class FakeHTTP:
        def post(self, url, json):
            seen["payload"] = json
            return FakeResp()

        def close(self):
            pass

    client = HugrGateClient(url="http://127.0.0.1:9",  # unroutable
                            fallback_inprocess=False)
    client._http = FakeHTTP()  # type: ignore[assignment]
    result = client.decide({"f": 1.0}, _spec())
    assert result.value == "a"


def test_client_protocol_probe_inprocess():
    from hugrgate.client import HugrGateClient
    from hugrgate.server import build_gate
    client = HugrGateClient(gate=build_gate())
    info = client.protocol()
    assert info["protocol_version"] == PROTOCOL_VERSION
    assert info["mode"] == "inprocess"
