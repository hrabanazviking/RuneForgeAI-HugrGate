"""Slice 061 — hardware-aware routing."""

from __future__ import annotations

import sys

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    DynamicRungPlanner,
    HardwareAwarePlanner,
    HostProfile,
    LadderRouterV2,
    RouterContext,
    hardware_compatible,
)


class HwBackend(Backend):
    def __init__(self, name, prob=0.95, requirements=None):
        self.name = name
        self._prob = prob
        self._reqs = requirements or {}

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

    def hardware_requirements(self):
        return dict(self._reqs)


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


HOST = HostProfile(cpu_count=4, memory_mb=8192.0, has_gpu=False,
                   platform="linux")


def test_detect_returns_sane_profile():
    host = HostProfile.detect()
    assert host.cpu_count >= 1
    assert host.memory_mb > 0
    assert host.platform == sys.platform
    assert isinstance(host.has_gpu, bool)
    d = host.to_dict()
    assert set(d) == {"cpu_count", "memory_mb", "has_gpu", "platform",
                      "accelerators"}


def test_compatibility_checks():
    assert hardware_compatible(HwBackend("plain"), HOST) is None
    gpu = hardware_compatible(
        HwBackend("g", requirements={"requires_gpu": True}), HOST)
    assert gpu is not None and "GPU" in gpu
    mem = hardware_compatible(
        HwBackend("m", requirements={"min_memory_mb": 16384}), HOST)
    assert mem is not None and "8192" in mem
    cpu = hardware_compatible(
        HwBackend("c", requirements={"min_cpu_count": 64}), HOST)
    assert cpu is not None and "64" in cpu
    plat = hardware_compatible(
        HwBackend("p", requirements={"platforms": ["win32"]}), HOST)
    assert plat is not None and "win32" in plat
    # boundaries: equal fits
    assert hardware_compatible(
        HwBackend("e", requirements={"min_memory_mb": 8192.0,
                                     "min_cpu_count": 4,
                                     "platforms": ["linux"]}),
        HOST) is None
    # unknown requirement keys never break the check
    assert hardware_compatible(
        HwBackend("u", requirements={"quantum_coherence": True}),
        HOST) is None
    # gpu host passes gpu requirement
    gpu_host = HostProfile(cpu_count=4, memory_mb=8192.0, has_gpu=True,
                           platform="linux")
    assert hardware_compatible(
        HwBackend("g", requirements={"requires_gpu": True}),
        gpu_host) is None


def test_planner_prunes_incompatible():
    reg = reg_of(HwBackend("cpu-only"),
                 HwBackend("gpu-hog",
                           requirements={"requires_gpu": True}))
    planner = HardwareAwarePlanner(DynamicRungPlanner(reg), reg, host=HOST)
    plan = planner.plan(RouterContext.from_request({}, spec()))
    assert [n.backend_name for n in plan.nodes] == ["cpu-only"]
    assert plan.nodes[0].params["host_compatible"] is True
    assert any("pruned 1" in r for r in plan.rationale)
    assert "+hardware" in plan.created_by


def test_all_incompatible_abstains():
    reg = reg_of(HwBackend("gpu-hog", prob=0.99,
                           requirements={"requires_gpu": True}))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("gpu-hog")]},
        planner=HardwareAwarePlanner(DynamicRungPlanner(reg), reg,
                                     host=HOST))
    with pytest.raises(Abstention):
        router.decide({}, spec())


def test_compatible_wins_end_to_end():
    reg = reg_of(HwBackend("gpu-hog", prob=0.99,
                           requirements={"requires_gpu": True}),
                 HwBackend("cpu-only", prob=0.95))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("gpu-hog")]},
        planner=HardwareAwarePlanner(DynamicRungPlanner(reg), reg,
                                     host=HOST))
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "cpu-only"
