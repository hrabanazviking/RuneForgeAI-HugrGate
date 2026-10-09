"""Slice 063 — quality-of-service classes."""

from __future__ import annotations

import pytest

from hugrgate import Backend, BackendRegistry, DecisionSpec
from hugrgate.routing import (
    QOS_DEPTH_CAPS,
    QOS_PROFILES,
    QOS_WEIGHTS,
    LadderSynthesizer,
    QoSClass,
    QoSProfile,
    RouterContext,
    RoutingOptions,
    qos_profile,
)


class QosBackend(Backend):
    def __init__(self, name):
        self.name = name

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):  # pragma: no cover
        raise NotImplementedError


def test_parse_and_invalid():
    assert QoSClass.parse("critical") is QoSClass.CRITICAL
    assert QoSClass.parse("best_effort") is QoSClass.BEST_EFFORT
    with pytest.raises(ValueError):
        QoSClass.parse("ultra")


def test_profiles_sane_and_ordered():
    widths = []
    for cls in QoSClass:
        p = qos_profile(cls.value)
        assert isinstance(p, QoSProfile)
        assert p.name is cls
        assert abs(sum(p.weights) - 1.0) < 1e-9
        widths.append(p.parallel_width)
    # posture strengthens monotonically with class
    caps = [qos_profile(c.value).depth_cap for c in QoSClass]
    assert caps == sorted(caps)
    assert widths == sorted(widths)
    assert qos_profile("best_effort").hedge_allowed is False
    assert qos_profile("critical").hedge_allowed is True
    assert (qos_profile("critical").weights[0]
            > qos_profile("best_effort").weights[0])


def test_profile_validation():
    with pytest.raises(ValueError):
        QoSProfile(name=QoSClass.STANDARD, depth_cap=0, weights=(1.0, 0, 0),
                   parallel_width=1, hedge_allowed=False, hedge_delay_ms=1,
                   fast_path_probability=0.9, early_exit_delta=0.1)
    with pytest.raises(ValueError):
        QoSProfile(name=QoSClass.STANDARD, depth_cap=2, weights=(0.5, 0.5, 0.5),
                   parallel_width=1, hedge_allowed=False, hedge_delay_ms=1,
                   fast_path_probability=0.9, early_exit_delta=0.1)


def test_synthesis_dicts_agree_with_profiles():
    for cls in QoSClass:
        assert QOS_DEPTH_CAPS[cls.value] == QOS_PROFILES[cls].depth_cap
        assert QOS_WEIGHTS[cls.value] == QOS_PROFILES[cls].weights


def test_synthesizer_honors_profile_depth():
    reg = BackendRegistry()
    for i in range(10):
        reg.register(QosBackend(f"b{i}"))
    for cls in QoSClass:
        plan = LadderSynthesizer(reg).plan(
            RouterContext.from_request(
                {}, DecisionSpec(type="categorical", options=["a", "b"]),
                options=RoutingOptions(qos=cls.value)))
        assert len(plan.nodes) <= QOS_PROFILES[cls].depth_cap


def test_options_qos_still_validated():
    with pytest.raises(Exception):
        RoutingOptions(qos="ultra")
    assert RoutingOptions(qos="priority").qos == "priority"
