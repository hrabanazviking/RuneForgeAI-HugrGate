"""Slice 172 — model health probes.

Unit tests for ``hugrgate.runtimes.health_probes``.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import SpecError
from hugrgate.runtimes import FakeRuntime, ModelRef, RuntimeRegistry
from hugrgate.runtimes.health_probes import (
    HealthProbe,
    InferenceProbe,
    LatencyProbe,
    LivenessProbe,
    ModelLoadedProbe,
    ProbeResult,
    probe_all,
    probe_runtime,
)


def _rt(name: str = "fake", **kwargs) -> FakeRuntime:
    rt = FakeRuntime(**kwargs)
    rt.name = name
    return rt


def _loaded(name: str = "fake", **kwargs) -> FakeRuntime:
    rt = _rt(name, **kwargs)
    rt.load(ModelRef(runtime=name, path="/m.gguf", format="gguf"))
    return rt


# -- healthy runtime -------------------------------------------------------------------

def test_healthy_loaded_runtime_passes_all():
    report = probe_runtime(_loaded())
    assert report.ok is True
    assert {r.probe for r in report.results} == {
        "liveness", "model-loaded", "inference", "latency"}
    assert report.failed == []
    d = report.to_dict()
    assert d["runtime"] == "fake" and d["ok"] is True


def test_probe_result_to_dict():
    r = ProbeResult(probe="p", runtime="r", ok=True, latency_s=0.5)
    assert r.to_dict() == {"probe": "p", "runtime": "r", "ok": True,
                           "latency_s": 0.5, "detail": ""}


# -- individual probes -----------------------------------------------------------------

def test_model_loaded_probe_fails_without_model():
    result = ModelLoadedProbe().check(_rt())
    assert result.ok is False
    assert "no model" in result.detail


def test_liveness_probe_reads_status():
    rt = _rt()
    result = LivenessProbe().check(rt)
    assert result.ok is True

    class Sick(FakeRuntime):
        def health(self):
            return {"status": "degraded", "runtime": self.name}

    sick = Sick()
    sick.name = "sick"
    result = LivenessProbe().check(sick)
    assert result.ok is False
    assert "degraded" in result.detail


def test_inference_probe_catches_wedged_engine():
    class Wedged(FakeRuntime):
        def health(self):
            return {"status": "ok", "runtime": self.name}

        def generate(self, prompt, options=None):
            raise RuntimeError("engine wedged")

    rt = Wedged()
    rt.name = "wedged"
    # Liveness says ok, but the inference probe raises -> recorded.
    report = probe_runtime(rt, probes=(LivenessProbe(), InferenceProbe()))
    assert report.ok is False
    failed = {r.probe: r for r in report.failed}
    assert set(failed) == {"inference"}
    assert "RuntimeError" in failed["inference"].detail


def test_inference_probe_needs_a_capability():
    rt = _rt(supports=frozenset())
    result = InferenceProbe().check(rt)
    assert result.ok is False
    assert "no probed capabilities" in result.detail


def test_latency_probe_thresholds():
    slow = _rt(latency_s=0.05)
    result = LatencyProbe(warn_s=0.01, crit_s=10.0).check(slow)
    assert result.ok is True
    assert "warn" in result.detail  # over warn, under crit
    assert result.latency_s >= 0.05

    result = LatencyProbe(warn_s=0.01, crit_s=0.02).check(slow)
    assert result.ok is False
    assert "crit" in result.detail


def test_latency_probe_rejects_bad_thresholds():
    with pytest.raises(SpecError):
        LatencyProbe(warn_s=0.0, crit_s=1.0)
    with pytest.raises(SpecError):
        LatencyProbe(warn_s=5.0, crit_s=1.0)


def test_latency_probe_no_timed_capability():
    rt = _rt(supports=frozenset({"classify"}))
    result = LatencyProbe().check(rt)
    assert result.ok is False


# -- probe_all ---------------------------------------------------------------------------

def test_probe_all_fans_out():
    reg = RuntimeRegistry()
    reg.register(_loaded("a"))
    reg.register(_rt("b"))  # no model -> model-loaded fails
    reports = probe_all(reg)
    by_name = {r.runtime: r for r in reports}
    assert by_name["a"].ok is True
    assert by_name["b"].ok is False
    assert [r.probe for r in by_name["b"].failed] == ["model-loaded"]


def test_probe_all_rejects_bad_workers():
    with pytest.raises(SpecError):
        probe_all(RuntimeRegistry(), max_workers=0)


def test_probe_all_empty_registry():
    assert probe_all(RuntimeRegistry()) == []


def test_probe_crash_is_recorded_not_raised():
    class Crashy(HealthProbe):
        name = "crashy"

        def check(self, runtime):
            raise ValueError("probe bug")

    report = probe_runtime(_rt(), probes=(Crashy(),))
    assert report.ok is False
    assert "ValueError" in report.results[0].detail
