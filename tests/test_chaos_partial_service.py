"""Slice 266 — partial-service failure experiment tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.chaos import (
    ServiceUnderTest,
    partial_service_failure_experiment,
    run_experiment_on_lab,
)
from hugrgate.chaos.framework import ExperimentRunner
from hugrgate.errors import ChaosError, SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _service(names=("b1", "b2", "b3"), breakable=("b1", "b2")):
    backends = [StubBackend(name=n, value="b") for n in names]
    return ServiceUnderTest(backends, breakable=breakable)


# --- service harness ------------------------------------------------------------------------------------

def test_service_harness_validation():
    with pytest.raises(SpecError, match="at least one backend"):
        ServiceUnderTest([], breakable=())
    with pytest.raises(SpecError, match="unique"):
        ServiceUnderTest([StubBackend(name="x"), StubBackend(name="x")],
                         breakable=())
    with pytest.raises(SpecError, match="not in backends"):
        ServiceUnderTest([StubBackend(name="x")], breakable=("ghost",))
    service = _service()
    assert service.names == ["b1", "b2", "b3"]
    assert service.breakable == ["b1", "b2"]
    assert service.is_healthy() is True
    with pytest.raises(SpecError, match="not breakable"):
        service.inject_crash("b3")
    service.inject_crash("b1")
    assert service.is_healthy() is False
    service.recover("b1")
    assert service.is_healthy() is True


def test_experiment_builder_validation():
    service = _service()
    with pytest.raises(SpecError, match="non-empty"):
        partial_service_failure_experiment(service, [], {}, _spec())
    with pytest.raises(SpecError, match="unbreakable"):
        partial_service_failure_experiment(service, ["b3"], {}, _spec())


# --- the experiment ------------------------------------------------------------------------------------------

def test_partial_failure_passes_with_survivors():
    service = _service()
    experiment = partial_service_failure_experiment(
        service, ["b1"], {}, _spec())
    report = run_experiment_on_lab(experiment)
    assert report["all_passed"] is True, report
    assert report["steady_state_held"] is True
    assert [f["name"] for f in report["faults"]] == ["crash-b1"]
    assert all(f["passed"] for f in report["faults"])
    json.dumps(report)
    # Rollback healed the victim: the service is whole again.
    assert service.is_healthy() is True


def test_two_failures_still_served():
    service = _service()
    experiment = partial_service_failure_experiment(
        service, ["b1", "b2"], {}, _spec())
    report = run_experiment_on_lab(experiment)
    assert report["all_passed"] is True, report
    assert len(report["faults"]) == 2


def test_simultaneous_total_failure_abstains_cleanly():
    service = _service(names=("b1", "b2"), breakable=("b1", "b2"))
    experiment = partial_service_failure_experiment(
        service, ["b1", "b2"], {}, _spec(), simultaneous=True)
    report = run_experiment_on_lab(experiment)
    # Every backend crashed at once: the service abstained instead of
    # serving garbage — the clean-failure hypothesis holds.
    assert report["all_passed"] is True, report
    assert report["faults"][0]["name"] == "crash-all"
    assert service.is_healthy() is True  # rollback healed everything


def test_simultaneous_with_safe_default_falsifies_clean_abstention():
    # With a safe_default policy, total failure *serves the default*
    # by design — so the "fails cleanly by abstaining" hypothesis is
    # honestly falsified and the report says so.
    policy = DecisionPolicy(fallback_behavior="safe_default")
    service = ServiceUnderTest(
        [StubBackend(name="b1", value="b"), StubBackend(name="b2")],
        breakable=("b1", "b2"), policy=policy, safe_default="a")
    experiment = partial_service_failure_experiment(
        service, ["b1", "b2"], {}, _spec(), simultaneous=True)
    report = run_experiment_on_lab(experiment)
    assert report["all_passed"] is False
    assert "expected a clean abstention" in \
        report["faults"][0]["detail"]
    assert service.is_healthy() is True


def test_unhealthy_baseline_fails_steady_state():
    # Nothing can serve even before any fault: the steady-state probe
    # must fail the experiment regardless of fault outcomes.
    policy = DecisionPolicy(minimum_probability=0.9)
    service = ServiceUnderTest(
        [StubBackend(name="b1", value="b", probability=0.5),
         StubBackend(name="b2", value="b", probability=0.5)],
        breakable=("b1",), policy=policy)
    experiment = partial_service_failure_experiment(
        service, ["b1"], {}, _spec())
    report = run_experiment_on_lab(experiment)
    assert report["steady_before"]["service-serves"]["ok"] is False
    assert report["steady_state_held"] is False
    assert report["all_passed"] is False


def test_blast_radius_guards_the_experiment():
    service = _service()
    experiment = partial_service_failure_experiment(
        service, ["b1"], {}, _spec())
    with pytest.raises(ChaosError, match="outside the experiment"):
        ExperimentRunner().run(experiment, "production")
    assert service.is_healthy() is True  # nothing was touched


def test_policy_mutation_is_caught_by_probe():
    policy = DecisionPolicy(minimum_probability=0.5)
    service = ServiceUnderTest(
        [StubBackend(name="b1", value="b"), StubBackend(name="b2")],
        breakable=("b1",), policy=policy)
    experiment = partial_service_failure_experiment(
        service, ["b1"], {}, _spec())
    # Sabotage the policy mid-experiment via a fault wrapper.
    original_inject = service.inject_crash
    def sabotage(name):
        original_inject(name)
        policy.minimum_probability = 0.99
    service.inject_crash = sabotage  # type: ignore[method-assign]
    report = run_experiment_on_lab(experiment)
    assert report["steady_state_held"] is False
    assert report["all_passed"] is False
    policy.minimum_probability = 0.5  # restore for other tests
