"""Slice 428 — Python SDK v2.

``HugrGateSDK`` is a strict superset of the v1 client: context-manager
use, exponential-backoff retry on recoverable faults only, HTTP error
envelopes mapped back onto the HugrGate taxonomy, batch decisions,
and a versioned User-Agent.
"""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import (
    BackendUnavailable,
    SDKError,
    SpecError,
)
from hugrgate.sdk import SDK_VERSION, HugrGateSDK
from hugrgate.server import build_gate


def _spec() -> DecisionSpec:
    return DecisionSpec.from_dict({"type": "categorical",
                                   "options": ["a", "b"]})


def _ok_body():
    return {"value": "a", "probability": 1.0,
            "distribution": {"a": 1.0}, "metadata": {}}


class _ScriptedHTTP:
    """Fake httpx client playing a script of outcomes per POST."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.headers = {}

    def post(self, url, json):
        self.calls += 1
        outcome = self.script.pop(0) if self.script else self.script[-1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


def _resp(status: int, body: dict) -> httpx.Response:
    request = httpx.Request("POST", "http://x/decide")
    return httpx.Response(status, json=body, request=request)


def _sdk(script, **kw):
    kw.setdefault("fallback_inprocess", False)
    kw.setdefault("retry_backoff_s", 0.0)
    sdk = HugrGateSDK(url="http://127.0.0.1:9", **kw)
    fake = _ScriptedHTTP(script)
    fake.headers = sdk._http.headers
    sdk._http = fake  # type: ignore[assignment]
    return sdk, fake


def test_user_agent_is_versioned():
    sdk = HugrGateSDK(url="http://127.0.0.1:9")
    try:
        assert sdk._http.headers["user-agent"] == (
            f"hugrgate-sdk-py/{SDK_VERSION}")
    finally:
        sdk.close()


def test_context_manager_closes():
    with HugrGateSDK(url="http://127.0.0.1:9") as sdk:
        assert not sdk._closed
    assert sdk._closed
    assert sdk._http.is_closed


def test_close_is_idempotent():
    sdk = HugrGateSDK(url="http://127.0.0.1:9")
    sdk.close()
    sdk.close()  # must not raise


def test_retries_transport_errors_then_succeeds():
    sdk, fake = _sdk([httpx.ConnectError("down"),
                      httpx.ConnectError("down"),
                      _resp(200, _ok_body())],
                     max_retries=3)
    result = sdk.decide({"f": 1.0}, _spec())
    assert result.value == "a"
    assert fake.calls == 3
    assert result.metadata["sdk_version"] == SDK_VERSION


def test_gives_up_as_sdk_error_after_retries():
    sdk, fake = _sdk([httpx.ConnectError("down")] * 5, max_retries=2)
    with pytest.raises(SDKError) as exc:
        sdk.decide({"f": 1.0}, _spec())
    assert exc.value.recoverable is True
    assert fake.calls == 3  # 1 initial + 2 retries


def test_no_retry_on_caller_bug():
    err_body = {"error": {"code": "spec_error",
                          "message": "bad spec",
                          "recoverable": False, "details": {}}}
    sdk, fake = _sdk([_resp(422, err_body)], max_retries=3)
    with pytest.raises(SpecError):
        sdk.decide({"f": 1.0}, _spec())
    assert fake.calls == 1  # caller bugs are never retried


def test_retries_503_then_succeeds():
    err_body = {"error": {"code": "backend_unavailable",
                          "message": "shedding load",
                          "recoverable": True, "details": {}}}
    sdk, fake = _sdk([_resp(503, err_body), _resp(200, _ok_body())],
                     max_retries=2)
    result = sdk.decide({"f": 1.0}, _spec())
    assert result.value == "a"
    assert fake.calls == 2


def test_503_maps_to_taxonomy_error():
    err_body = {"error": {"code": "backend_unavailable",
                          "message": "shedding load",
                          "recoverable": True, "details": {}}}
    sdk, _fake = _sdk([_resp(503, err_body)], max_retries=0)
    with pytest.raises(BackendUnavailable) as exc:
        sdk.decide({"f": 1.0}, _spec())
    assert exc.value.code == "backend_unavailable"


def test_unparseable_error_body_maps_to_generic():
    sdk, _fake = _sdk([_resp(500, {"weird": True})], max_retries=0)
    with pytest.raises(Exception) as exc:
        sdk.decide({"f": 1.0}, _spec())
    assert "500" in str(exc.value)


def test_decide_batch_reports_per_item_errors():
    err_body = {"error": {"code": "spec_error", "message": "bad",
                          "recoverable": False, "details": {}}}
    sdk, _fake = _sdk([_resp(200, _ok_body()), _resp(422, err_body)])
    outcomes = sdk.decide_batch([{"f": 1.0}, {"f": 2.0}], _spec())
    assert outcomes[0].value == "a"
    assert isinstance(outcomes[1], SpecError)


def test_decide_value_convenience():
    sdk, _fake = _sdk([_resp(200, _ok_body())])
    assert sdk.decide_value({"f": 1.0}, _spec()) == "a"


def test_invalid_retry_config_rejected():
    with pytest.raises(ValueError):
        HugrGateSDK(max_retries=-1)
    with pytest.raises(ValueError):
        HugrGateSDK(retry_backoff_s=-0.5)


def test_inprocess_gate_still_works():
    sdk = HugrGateSDK(gate=build_gate())
    try:
        result = sdk.decide({"f": 1.0}, _spec())
        assert result.value in ("a", "b")
    finally:
        sdk.close()
