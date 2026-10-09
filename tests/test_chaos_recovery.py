"""Slice 271 — recovery verification tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.chaos import (
    RecoveryProbe,
    RecoveryReport,
    RecoveryVerifier,
    backend_health_probe,
    circuit_closed_probe,
    decision_smoke_probe,
)
from hugrgate.chaos.backend_faults import FaultSpec, FaultyBackend
from hugrgate.circuit import CircuitRegistry
from hugrgate.core import HugrGate
from hugrgate.errors import SpecError
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _probe(name="p", check=None):
    return RecoveryProbe(name=name, description=f"probe {name}",
                         check=check or (lambda: f"{name} ok"))


# --- verifier mechanics ----------------------------------------------------------------------------------------

def test_all_passing_probes_report_recovered():
    v = RecoveryVerifier("svc", [_probe("a"), _probe("b")])
    report = v.verify()
    assert isinstance(report, RecoveryReport)
    assert report.recovered is True
    assert report.attempts == 1
    assert [p.status for p in report.probes] == ["passed", "passed"]
    assert v.probe_names() == ["a", "b"]
    json.dumps(report.to_dict())


def test_failing_probe_does_not_stop_others():
    order = []
    v = RecoveryVerifier("svc", [
        _probe("a", lambda: order.append("a") or "ok"),
        _probe("b", lambda: (_ for _ in ()).throw(RuntimeError("bad"))),
        _probe("c", lambda: order.append("c") or "ok"),
    ])
    report = v.verify()
    assert order == ["a", "c"]
    assert [p.status for p in report.probes] == ["passed", "failed",
                                                "passed"]
    assert "bad" in report.probes[1].note
    assert report.recovered is False
    json.dumps(report.to_dict())


def test_retry_until_recovered_with_injected_sleep():
    sleeps = []
    calls = {"n": 0}

    def warming_up():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("still warming")
        return "warm"

    v = RecoveryVerifier("svc", [_probe("warm", warming_up)],
                         sleep=lambda s: sleeps.append(s))
    report = v.verify(max_attempts=5, wait_s=0.5)
    assert report.recovered is True
    assert report.attempts == 3
    assert report.probes[0].attempts == 3
    assert sleeps == [0.5, 0.5]  # slept between attempts, not after success


def test_attempts_exhausted_reports_not_recovered():
    sleeps = []
    v = RecoveryVerifier(
        "svc", [_probe("never", lambda: (_ for _ in ()).throw(
            RuntimeError("down")))],
        sleep=lambda s: sleeps.append(s))
    report = v.verify(max_attempts=3, wait_s=0.1)
    assert report.recovered is False
    assert report.attempts == 3
    assert len(sleeps) == 2  # no sleep after the final attempt


def test_verifier_validation():
    with pytest.raises(SpecError, match="non-empty"):
        RecoveryVerifier("", [_probe()])
    with pytest.raises(SpecError, match="at least one"):
        RecoveryVerifier("v", [])
    with pytest.raises(SpecError, match="duplicate"):
        RecoveryVerifier("v", [_probe("a"), _probe("a")])
    with pytest.raises(SpecError, match="non-empty"):
        RecoveryProbe("", "d", lambda: "x")
    with pytest.raises(SpecError, match="callable"):
        RecoveryProbe("p", "d", "nope")  # type: ignore[arg-type]
    v = RecoveryVerifier("v", [_probe()])
    with pytest.raises(SpecError):
        v.verify(max_attempts=0)
    with pytest.raises(SpecError):
        v.verify(wait_s=-1)


# --- builtin probes: the full fault -> disarm -> verify story ------------------------------------------------------

def test_decision_smoke_probe_across_fault_and_recovery():
    gate = HugrGate()
    flaky = FaultyBackend(StubBackend(name="flaky", value="a"))
    gate.register(flaky)
    probe = decision_smoke_probe(gate, {}, _spec(), backend_name="flaky")
    verifier = RecoveryVerifier("flaky-svc", [probe])

    assert verifier.verify().recovered is True  # healthy baseline

    flaky.arm(FaultSpec(mode="error_rate", rate=1.0))
    report = verifier.verify()
    assert report.recovered is False  # fault present: not recovered

    flaky.disarm("error_rate")
    report = verifier.verify()
    assert report.recovered is True  # disarmed AND verified
    assert "accepted" in report.probes[0].note


def test_backend_health_probe():
    backend = StubBackend(name="b", value="a")
    probe = backend_health_probe(backend)
    v = RecoveryVerifier("v", [probe])
    assert v.verify().recovered is True
    assert "healthy" in v.verify().probes[0].note

    class SickBackend(StubBackend):
        def health(self):
            return {"status": "degraded", "backend": self.name}
    v2 = RecoveryVerifier("v2", [backend_health_probe(SickBackend(
        name="sick", value="a"))])
    report = v2.verify()
    assert report.recovered is False
    assert "degraded" in report.probes[0].note


def test_circuit_closed_probe_with_real_breaker():
    registry = CircuitRegistry()
    breaker = registry.get("b")
    probe = circuit_closed_probe(lambda: breaker.state, "b")
    v = RecoveryVerifier("v", [probe])
    assert v.verify().recovered is True

    breaker.record_failure()
    for _ in range(10):
        breaker.record_failure()
    assert breaker.state != "closed"
    report = v.verify()
    assert report.recovered is False
    assert "not closed" in report.probes[0].note
