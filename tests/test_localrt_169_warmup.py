"""Slice 169 — model warmup manager.

Unit tests for ``hugrgate.runtimes.warmup``.
"""

from __future__ import annotations

import pytest

from hugrgate.backend import Backend
from hugrgate.errors import SpecError
from hugrgate.runtimes import (
    FakeRuntime,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
    RuntimeRegistry,
)
from hugrgate.runtimes.warmup import WarmupManager, WarmupResult


def _fake(name: str = "fake", caps: tuple[str, ...] = ("generate",)) -> FakeRuntime:
    rt = FakeRuntime(supports=frozenset(caps))
    rt.name = name
    return rt


class _FailGenerate(FakeRuntime):
    """Fake whose generate always raises (failure recording)."""

    def generate(self, prompt: str, options=None):
        raise RuntimeError("inference blew up")


# -- constructor ---------------------------------------------------------------------

def test_rejects_bad_params():
    with pytest.raises(SpecError):
        WarmupManager(repeat=-1)
    with pytest.raises(SpecError):
        WarmupManager(max_workers=0)


# -- warmup_runtime ------------------------------------------------------------------

def test_warms_runtime_and_records_baselines():
    mgr = WarmupManager(repeat=4)
    result = mgr.warmup_runtime(_fake())
    assert result.success is True
    assert result.error is None
    assert result.calls == 1 + 4  # warmup hook + 4 probes
    assert len(result.latencies_s) == 4
    assert result.latency_p50_s is not None
    assert result.latency_p95_s is not None
    assert result.latency_p95_s >= result.latency_p50_s
    assert "fake" in mgr.warmed


def test_warmup_loads_model_first():
    rt = _fake()
    mgr = WarmupManager(repeat=1)
    result = mgr.warmup_runtime(
        rt, ModelRef(runtime="fake", path="/m.gguf", format="gguf"))
    assert result.success is True
    assert result.model is not None and "/m.gguf" in result.model
    assert rt.info().model is not None


def test_warmup_is_idempotent():
    rt = _fake()
    mgr = WarmupManager(repeat=2)
    first = mgr.warmup_runtime(rt)
    second = mgr.warmup_runtime(rt)
    assert second is first  # cached, no new probes
    assert rt.generate_calls == 2  # probes only; the warmup hook is silent


def test_rewarm_runs_again():
    rt = _fake()
    mgr = WarmupManager(repeat=2)
    mgr.warmup_runtime(rt)
    mgr.warmup_runtime(rt, rewarm=True)
    assert rt.generate_calls == 2 * 2


def test_reset_forgets_warm_state():
    rt = _fake()
    mgr = WarmupManager(repeat=1)
    mgr.warmup_runtime(rt)
    mgr.reset("fake")
    assert mgr.warmed == set()
    assert mgr.last_result("fake") is None
    mgr.warmup_runtime(rt)
    mgr.reset()
    assert mgr.warmed == set()


def test_failure_is_recorded_not_raised():
    class Boom(LocalRuntime):
        @classmethod
        def available(cls): return True

        @property
        def name(self): return "boom"

        def info(self):
            return RuntimeInfo(
                name="boom", engine="boom", engine_version="0",
                available=True, devices=("cpu",), formats=("gguf",),
                capabilities=frozenset({"generate"}))

        def load(self, model): raise RuntimeError("no disk")

        def warmup(self): ...

        def generate(self, prompt, options): raise AssertionError("unreachable")

        def embed(self, texts): raise AssertionError("unreachable")

        def classify(self, texts, labels): raise AssertionError("unreachable")

    mgr = WarmupManager()
    result = mgr.warmup_runtime(
        Boom(), ModelRef(runtime="boom", path="/x.gguf"))
    assert result.success is False
    assert "RuntimeError" in result.error
    assert "boom" not in mgr.warmed
    assert mgr.last_result("boom") is result


def test_multi_capability_probes_each_capability():
    rt = _fake(caps=("generate", "embed", "classify"))
    mgr = WarmupManager(repeat=2)
    result = mgr.warmup_runtime(rt)
    assert result.success is True
    assert result.calls == 1 + 2 * 3
    assert len(result.latencies_s) == 2 * 3


def test_repeat_zero_means_hook_only():
    rt = _fake()
    mgr = WarmupManager(repeat=0)
    result = mgr.warmup_runtime(rt)
    assert result.success is True
    assert result.calls == 1
    assert result.latencies_s == []
    assert result.latency_p50_s is None


# -- warmup_all ----------------------------------------------------------------------

def test_warmup_all_warms_everything_parallel():
    reg = RuntimeRegistry()
    reg.register(_fake(name="a"))
    reg.register(_fake(name="b"))
    mgr = WarmupManager(repeat=1)
    results = mgr.warmup_all(reg)
    assert {r.name for r in results} == {"a", "b"}
    assert all(r.success for r in results)
    assert mgr.warmed == {"a", "b"}


def test_warmup_all_sequential_when_max_workers_1():
    reg = RuntimeRegistry()
    reg.register(_fake(name="a"))
    mgr = WarmupManager(repeat=1, max_workers=1)
    results = mgr.warmup_all(reg)
    assert [r.name for r in results] == ["a"]


def test_warmup_all_loads_models_by_name():
    reg = RuntimeRegistry()
    rt = _fake(name="a")
    reg.register(rt)
    mgr = WarmupManager(repeat=0)
    results = mgr.warmup_all(
        reg, models={"a": ModelRef(runtime="a", path="/a.gguf")})
    assert results[0].success is True
    assert rt.info().model.path == "/a.gguf"


def test_warmup_all_records_failures():
    reg = RuntimeRegistry()
    reg.register(_fake(name="good"))
    bad = _FailGenerate(supports=frozenset({"generate"}))
    bad.name = "bad"
    reg.register(bad)
    mgr = WarmupManager(repeat=1)
    results = mgr.warmup_all(reg)
    by_name = {r.name: r for r in results}
    assert by_name["good"].success is True
    assert by_name["bad"].success is False
    assert mgr.warmed == {"good"}


# -- legacy backend ------------------------------------------------------------------

class _OldBackend(Backend):
    name = "old"

    def __init__(self):
        self.warmed = 0

    def warmup(self):
        self.warmed += 1

    def capabilities(self):
        return {}

    def supports(self, spec):
        return False

    def evaluate(self, state, spec, context=None):
        raise NotImplementedError


def test_warmup_backend_uses_legacy_hook():
    b = _OldBackend()
    mgr = WarmupManager()
    result = mgr.warmup_backend(b)
    assert result.success is True
    assert b.warmed == 1
    assert "old" in mgr.warmed
    mgr.warmup_backend(b)
    assert b.warmed == 1  # idempotent


# -- result --------------------------------------------------------------------------

def test_result_to_dict():
    r = WarmupResult(name="x", model="m", success=True, calls=2,
                     latencies_s=[0.1, 0.3])
    d = r.to_dict()
    assert d == {"name": "x", "model": "m", "success": True, "calls": 2,
                 "latency_p50_s": 0.2, "latency_p95_s": 0.3,
                 "error": None}
