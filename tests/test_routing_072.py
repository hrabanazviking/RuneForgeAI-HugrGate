"""Slice 072 — route policy DSL."""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, PolicyError, SpecError
from hugrgate.routing import RoutePolicy, RoutingOptions, parse_route_policy


FULL = """
route {
  qos = priority;
  strategy = hedged;
  privacy_tier = confidential;
  max_cost = 0.05;
  max_energy_j = 10;
  max_memory_mb = 2048;
  max_latency_ms = 500;
  min_probability = 0.8;
  hedge_delay_ms = 50;
  parallel_width = 3;
  fast_path = 0.97;
  early_exit_delta = 0.02;
  prefer "local-llm", "rules";
  allow "local-llm", "rules", "cloud";
  forbid "cloud";
  skip remote when privacy = strict;
}
"""


def test_parse_full_example():
    rp = parse_route_policy(FULL)
    assert isinstance(rp, RoutePolicy)
    assert rp.options.qos == "priority"
    assert rp.options.strategy == "hedged"
    assert rp.options.privacy_tier == "confidential"
    assert rp.options.max_cost == pytest.approx(0.05)
    assert rp.options.max_energy_j == pytest.approx(10.0)
    assert rp.options.max_memory_mb == pytest.approx(2048.0)
    assert rp.options.parallel_width == 3
    assert rp.options.fast_path_probability == pytest.approx(0.97)
    assert rp.options.early_exit_delta == pytest.approx(0.02)
    assert rp.policy_values["minimum_probability"] == pytest.approx(0.8)
    assert rp.policy_values["maximum_latency_ms"] == pytest.approx(500.0)
    assert rp.prefer == ["local-llm", "rules"]
    assert rp.allow == ["local-llm", "rules", "cloud"]
    assert rp.forbid == ["cloud"]
    assert rp.skip_remote_when_strict is True


def test_apply_merges_onto_base():
    rp = parse_route_policy(FULL)
    policy, options = rp.apply(
        DecisionPolicy(remote_inference=True),
        RoutingOptions(qos="standard"))
    assert options.qos == "priority"  # DSL wins
    assert options.strategy == "hedged"
    assert policy.minimum_probability == pytest.approx(0.8)
    assert policy.maximum_latency_ms == pytest.approx(500.0)
    assert policy.max_cost is None  # DSL max_cost is options-level
    assert options.max_cost == pytest.approx(0.05)
    assert policy.preferred_backends == ["local-llm", "rules"]
    # forbid removes "cloud" from the allowlist
    assert policy.allowed_backends == ["local-llm", "rules"]


def test_skip_remote_when_strict_conditional():
    rp = parse_route_policy(
        "route { privacy = strict; skip remote when privacy = strict; }")
    policy, _ = rp.apply(DecisionPolicy(remote_inference=True))
    assert policy.privacy_class == "strict"
    assert policy.remote_inference is False
    # without strict privacy the rule does not fire
    rp2 = parse_route_policy("route { skip remote when privacy = strict; }")
    policy2, _ = rp2.apply(DecisionPolicy(remote_inference=True))
    assert policy2.remote_inference is True


def test_minimal_and_comments():
    rp = parse_route_policy("""
    # a quiet little policy
    route { qos = critical; }  # trailing comment
    """)
    assert rp.options.qos == "critical"
    policy, options = rp.apply()
    assert options.qos == "critical"
    assert policy.minimum_probability == 0.0  # untouched default


def test_errors():
    with pytest.raises(PolicyError):
        parse_route_policy("route { frobnicate = 1; }")
    with pytest.raises(PolicyError):
        parse_route_policy("route { qos = ultra; }")  # invalid value
    with pytest.raises(PolicyError):
        parse_route_policy("route { max_cost = 1; max_cost = 2; }")
    with pytest.raises(SpecError):
        parse_route_policy("route { qos = priority; ")  # unterminated
    with pytest.raises(SpecError):
        parse_route_policy('route { prefer oops; }')  # unquoted
    with pytest.raises(SpecError):
        parse_route_policy("route { qos = priority; } extra")
    with pytest.raises(PolicyError):
        parse_route_policy("route { max_cost = nope; }")


def test_dumps_round_trip():
    rp = parse_route_policy(FULL)
    text = rp.dumps()
    rp2 = parse_route_policy(text)
    assert rp2.options == rp.options
    assert rp2.policy_values == rp.policy_values
    assert rp2.prefer == rp.prefer
    assert rp2.allow == rp.allow
    assert rp2.forbid == rp.forbid
    assert rp2.skip_remote_when_strict == rp.skip_remote_when_strict


def test_dsl_drives_router_end_to_end():
    from hugrgate import (Backend, BackendRegistry, DecisionResult,
                          DecisionSpec)
    from hugrgate.ladder import LadderRung
    from hugrgate.routing import LadderRouterV2

    class B(Backend):
        def __init__(self, name, prob):
            self.name = name
            self._prob = prob

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            n = len(spec.options)
            rest = (1.0 - self._prob) / max(n - 1, 1)
            return DecisionResult(
                value="a", probability=self._prob,
                distribution={o: (self._prob if o == "a" else rest)
                              for o in spec.options},
                backend=self.name)

    reg = BackendRegistry()
    reg.register(B("cheap", 0.99))
    policy, options = parse_route_policy(
        'route { qos = best_effort; min_probability = 0.9; '
        'prefer "cheap"; }').apply()
    router = LadderRouterV2(reg, rungs=[LadderRung("cheap", 0.9)])
    won = router.decide({}, DecisionSpec(type="categorical",
                                         options=["a", "b"]),
                        policy, options=options)
    assert won.backend == "cheap"
