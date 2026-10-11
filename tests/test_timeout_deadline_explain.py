"""Slice D1 — explain_deadline (timeout-deadline-explain).

Covers: the explanation dict carries the same arithmetic as
deadline_ms_for in both branches — capped (policy cap binds, strictly
below the estimate) and uncapped (no policy / cap at or above the
estimate) — and deadline_ms exactly matches deadline_ms_for.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from hugrgate.backend import Backend
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.timeout import deadline_ms_for, explain_deadline


class _StubBackend(Backend):
    name = "stub"

    def __init__(self, latency_ms: float):
        self._latency_ms = latency_ms

    def capabilities(self) -> dict[str, Any]:
        return {}

    def supports(self, spec: DecisionSpec) -> bool:
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:  # pragma: no cover - never called
        raise AssertionError("stub evaluate must not run")

    def estimated_latency(self) -> float:
        return self._latency_ms


@pytest.mark.parametrize("latency,headroom", [
    (40.0, 1.5),   # estimate 60.0
    (0.0, 1.5),    # floors at 0.1 -> estimate 0.15
])
def test_explain_uncapped_no_policy(latency, headroom):
    backend = _StubBackend(latency)
    info = explain_deadline(backend, None, headroom)
    estimate = max(latency, 0.1) * headroom
    assert info["estimate_ms"] == pytest.approx(estimate)
    assert info["cap_ms"] is None
    assert info["headroom"] == headroom
    assert info["deadline_ms"] == deadline_ms_for(backend, None, headroom)
    assert info["deadline_ms"] == pytest.approx(estimate)
    assert info["capped"] is False


def test_explain_uncapped_cap_above_estimate():
    backend = _StubBackend(40.0)  # estimate 60.0 at headroom 1.5
    policy = DecisionPolicy(maximum_latency_ms=120.0)
    info = explain_deadline(backend, policy, 1.5)
    assert info["estimate_ms"] == pytest.approx(60.0)
    assert info["cap_ms"] == 120.0
    assert info["deadline_ms"] == deadline_ms_for(backend, policy, 1.5)
    assert info["deadline_ms"] == pytest.approx(60.0)
    assert info["capped"] is False


def test_explain_capped():
    backend = _StubBackend(40.0)  # estimate 60.0 at headroom 1.5
    policy = DecisionPolicy(maximum_latency_ms=25.0)
    info = explain_deadline(backend, policy, 1.5)
    assert info["estimate_ms"] == pytest.approx(60.0)
    assert info["cap_ms"] == 25.0
    assert info["headroom"] == 1.5
    assert info["deadline_ms"] == deadline_ms_for(backend, policy, 1.5)
    assert info["deadline_ms"] == pytest.approx(25.0)
    assert info["capped"] is True
