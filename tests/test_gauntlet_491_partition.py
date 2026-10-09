"""Slice 491 — network partition gauntlet.

The chaos toolkit simulates partitions; this gauntlet proves the
decision path stays fail-closed under them, end to end through the
live ``HugrGate.decide``: partitioned remotes fail fast with
``BackendUnavailable``, the policy object is never silently
weakened, partial failure doesn't fell the reachable host, and
healing restores service with the policy intact.
"""

from __future__ import annotations

from typing import Any

import pytest

from hugrgate import DecisionPolicy, DecisionResult, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.chaos.network import NetworkGuard, NetworkSimulator
from hugrgate.errors import BackendUnavailable
from hugrgate.gauntlet.partition import (
    assert_policy_intact,
    run_partition_scenario,
    snapshot_policy,
)


class _Remote(Backend):
    name = "remote-1"
    is_remote = True

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical"]}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None) -> DecisionResult:
        return DecisionResult(value="a", probability=0.9,
                              distribution={"a": 0.9, "b": 0.1})


SPEC = DecisionSpec(type="categorical", options=["a", "b"])


def _wired():
    sim = NetworkSimulator()
    guarded = NetworkGuard(_Remote(), sim, host="remote-1")
    gate = HugrGate()
    gate.register(guarded)
    policy = DecisionPolicy(remote_inference=True, minimum_probability=0.5)
    return gate, sim, policy


def test_partition_fails_fast_and_closed():
    gate, sim, policy = _wired()
    before = snapshot_policy(policy)
    report = run_partition_scenario(
        gate,
        lambda: gate.decide({"x": 1}, SPEC, policy,
                            backend_name="remote-1"),
        sim,
        "remote-1",
        policy=policy,
    )
    outcomes = [p["outcome"] for p in report.phases]
    assert outcomes == ["ok", "unavailable", "ok"], outcomes
    assert report.fail_closed_ok
    assert report.policy_drift == {}
    # The policy object itself was never weakened to "get through".
    assert policy.minimum_probability == 0.5
    assert policy.remote_inference is True
    assert_policy_intact(policy, before)
    gate.close()


def test_partition_never_mutates_policy_fields():
    _, _, policy = _wired()
    before = snapshot_policy(policy)
    assert "minimum_probability" in before
    assert "remote_inference" in before
    # Even a hostile mutation attempt is caught by the assertion.
    policy.minimum_probability = 0.01
    with pytest.raises(AssertionError) as exc_info:
        assert_policy_intact(policy, before)
    assert "minimum_probability" in str(exc_info.value)


def test_partial_failure_keeps_reachable_host_up():
    sim = NetworkSimulator()
    gate = HugrGate()
    gate.register(NetworkGuard(_Remote(), sim, host="remote-1"))

    class _Remote2(_Remote):
        name = "remote-2"

    gate.register(NetworkGuard(_Remote2(), sim, host="remote-2"))
    policy = DecisionPolicy(remote_inference=True)

    sim.set_down("remote-1")
    try:
        # remote-2 is untouched by remote-1's partition.
        result = gate.decide({"x": 1}, SPEC, policy, backend_name="remote-2")
        assert result.value == "a"
        # ...while remote-1 fails fast.
        with pytest.raises(BackendUnavailable):
            gate.decide({"x": 1}, SPEC, policy, backend_name="remote-1")
    finally:
        sim.set_up("remote-1")
        gate.close()


def test_healed_host_serves_again_with_policy_intact():
    gate, sim, policy = _wired()
    before = snapshot_policy(policy)
    sim.set_down("remote-1")
    try:
        with pytest.raises(BackendUnavailable):
            gate.decide({"x": 1}, SPEC, policy, backend_name="remote-1")
    finally:
        sim.set_up("remote-1")
    result = gate.decide({"x": 1}, SPEC, policy, backend_name="remote-1")
    assert result.value == "a"
    assert_policy_intact(policy, before)
    gate.close()


def test_unexpected_errors_are_recorded_not_hidden():
    gate, sim, policy = _wired()

    def _bad():
        raise RuntimeError("not a network error")

    report = run_partition_scenario(gate, _bad, sim, "remote-1",
                                    policy=policy)
    assert report.phases[0]["outcome"] == "error:RuntimeError"
    assert not report.fail_closed_ok
    gate.close()
