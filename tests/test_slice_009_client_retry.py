"""Slice 9 — client retry.

:class:`HugrGateClient` gains opt-in retry on transient HTTP faults
with decorrelated jitter. ``max_attempts`` defaults to 1, preserving
pre-slice-9 behavior exactly: the first transient failure raises as
before (in-process fallback / BackendError per ``fallback_inprocess``).
"""

from __future__ import annotations

import httpx
import pytest

from hugrgate import DecisionSpec
from hugrgate.client import HugrGateClient


def _spec() -> DecisionSpec:
    return DecisionSpec.from_dict({"type": "categorical",
                                   "options": ["a", "b"]})


def _ok_body() -> dict:
    return {"value": "a", "probability": 1.0,
            "distribution": {"a": 1.0}, "metadata": {}}


class _ScriptedTransport(httpx.MockTransport):
    """MockTransport serving a scripted sequence of statuses."""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls = 0
        super().__init__(self._handler)

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        outcome = self._script.pop(0) if self._script else 200
        if isinstance(outcome, Exception):
            raise outcome
        if outcome == 200:
            return httpx.Response(200, json=_ok_body(), request=request)
        return httpx.Response(outcome, json={}, request=request)


def _client(script, **kw) -> tuple[HugrGateClient, _ScriptedTransport,
                                  list[float]]:
    kw.setdefault("fallback_inprocess", False)
    kw.setdefault("retry_base_delay", 0.01)
    sleeps: list[float] = []
    client = HugrGateClient(url="http://127.0.0.1:9",
                            retry_sleep=sleeps.append, **kw)
    transport = _ScriptedTransport(script)
    client._http = httpx.Client(transport=transport, trust_env=False)
    return client, transport, sleeps


def test_retry_survives_two_503s_then_200():
    client, transport, sleeps = _client(
        [503, 503, 200], max_attempts=3, retry_seed=7)
    result = client.decide({"f": 1.0}, _spec())
    assert result.value == "a"
    assert transport.calls == 3
    assert len(sleeps) == 2
    # decorrelated jitter stays inside [base, cap]
    for d in sleeps:
        assert 0.01 <= d <= client.retry_max_delay
    client.close()


def test_default_max_attempts_raises_on_first_503():
    client, transport, _sleeps = _client([503, 200])
    assert client.max_attempts == 1
    with pytest.raises(httpx.HTTPStatusError):
        client.decide({"f": 1.0}, _spec())
    assert transport.calls == 1  # no retry: today's behavior
    client.close()


def test_retry_timeout_then_success():
    client, transport, _sleeps = _client(
        [httpx.ConnectError("down"), 200], max_attempts=3)
    result = client.decide({"f": 1.0}, _spec())
    assert result.value == "a"
    assert transport.calls == 2
    client.close()


def test_retry_429_then_success():
    client, transport, _sleeps = _client([429, 200], max_attempts=2)
    result = client.decide({"f": 1.0}, _spec())
    assert result.value == "a"
    assert transport.calls == 2
    client.close()


def test_non_transient_4xx_not_retried():
    client, transport, _sleeps = _client([400], max_attempts=3)
    with pytest.raises(httpx.HTTPStatusError):
        client.decide({"f": 1.0}, _spec())
    assert transport.calls == 1  # caller bugs are never retried
    client.close()


def test_exhausted_retries_raise_last_error():
    client, transport, sleeps = _client(
        [503, 503, 503, 503], max_attempts=3)
    with pytest.raises(httpx.HTTPStatusError):
        client.decide({"f": 1.0}, _spec())
    assert transport.calls == 3
    assert len(sleeps) == 2
    client.close()


def test_seed_makes_jitter_deterministic():
    client, _, sleeps_a = _client([503, 503, 200], max_attempts=3,
                                  retry_seed=42)
    client.decide({"f": 1.0}, _spec())
    client, _, sleeps_b = _client([503, 503, 200], max_attempts=3,
                                  retry_seed=42)
    client.decide({"f": 1.0}, _spec())
    assert sleeps_a == sleeps_b
    assert len(sleeps_a) == 2
    client.close()


def test_jitter_is_decorrelated_not_pure_uniform():
    # Decorrelated: delay_{n+1} drawn from uniform(base, 3*delay_n), so
    # with distinct seeds the sequences differ (not a fixed schedule),
    # yet each stays within [base, cap].
    seqs = set()
    for seed in range(5):
        client, _, sleeps = _client([503, 503, 200], max_attempts=3,
                                    retry_seed=seed)
        client.decide({"f": 1.0}, _spec())
        assert all(0.01 <= d <= 2.0 for d in sleeps)
        seqs.add(tuple(round(d, 9) for d in sleeps))
        client.close()
    assert len(seqs) > 1


def test_invalid_retry_config_rejected():
    with pytest.raises(ValueError):
        HugrGateClient(max_attempts=0)
    with pytest.raises(ValueError):
        HugrGateClient(retry_base_delay=-0.1)
    with pytest.raises(ValueError):
        HugrGateClient(retry_base_delay=5.0, retry_max_delay=1.0)
