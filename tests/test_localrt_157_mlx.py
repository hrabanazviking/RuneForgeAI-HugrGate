"""Slice 157 — MLX adapter boundary.

Unit tests for ``hugrgate.runtimes.mlx``. Platform is injected, so
both sides of the Apple-silicon boundary are exercised on any host.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import GenerationOptions, ModelRef
from hugrgate.runtimes.mlx import SUPPORTED_PLATFORM, MLXRuntime

DARWIN_ARM64 = ("darwin", "arm64")
LINUX_X86 = ("linux", "x86_64")


def _engine(text: str = "mlx says hi"):
    calls: list[dict] = []

    def generate_fn(model, tokenizer, prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return text

    engine = (object(), object(), generate_fn)
    return engine, calls


def _runtime(**kwargs) -> MLXRuntime:
    engine, calls = _engine(kwargs.pop("text", "mlx says hi"))
    rt = MLXRuntime(
        model=ModelRef(runtime="mlx", path="mlx-community/tiny",
                       format="mlx"),
        platform_info=kwargs.pop("platform_info", DARWIN_ARM64),
        engine=engine,
        **kwargs)
    rt._test_calls = calls  # type: ignore[attr-defined]
    return rt


# -- boundary ------------------------------------------------------------------

def test_supported_platform_constant():
    assert SUPPORTED_PLATFORM == ("darwin", "arm64")


def test_platform_supported_both_sides():
    assert MLXRuntime.platform_supported(DARWIN_ARM64) is True
    assert MLXRuntime.platform_supported(LINUX_X86) is False
    assert MLXRuntime.platform_supported(("darwin", "x86_64")) is False
    assert MLXRuntime.platform_supported(("DARWIN", "ARM64")) is True


def test_available_false_off_platform():
    assert MLXRuntime.available() is False  # linux CI host


def test_generate_off_platform_names_the_boundary():
    rt = _runtime(platform_info=LINUX_X86)
    with pytest.raises(BackendUnavailable, match="Apple silicon"):
        rt.generate("hello")


def test_info_reports_boundary():
    info = _runtime().info()
    assert info.name == "mlx"
    assert info.devices == ("apple-silicon",)
    assert "generate" in info.capabilities
    assert info.remote is False


# -- generate (on-platform, injected engine) -------------------------------------

def test_generate_returns_text():
    rt = _runtime()
    out = rt.generate("Hello", GenerationOptions(max_tokens=8))
    assert out.text == "mlx says hi"
    assert out.finish_reason == "stop"


def test_generate_forwards_mlx_kwargs():
    rt = _runtime()
    rt.generate("Hello", GenerationOptions(max_tokens=8, temperature=0.5,
                                          top_p=0.9, seed=42))
    call = rt._test_calls[0]  # type: ignore[attr-defined]
    assert call["max_tokens"] == 8
    assert call["temp"] == 0.5
    assert call["top_p"] == 0.9
    assert call["seed"] == 42


def test_generate_rejects_empty_prompt():
    with pytest.raises(SpecError):
        _runtime().generate(" ")


def test_generate_without_model_unavailable():
    rt = MLXRuntime(platform_info=DARWIN_ARM64)
    with pytest.raises(BackendUnavailable, match="no model loaded"):
        rt.generate("hello")


def test_generate_engine_failure_surfaces():
    def boom(model, tokenizer, prompt, **kwargs):
        raise RuntimeError("metal oom")

    rt = MLXRuntime(
        model=ModelRef(runtime="mlx", path="mlx-community/tiny",
                       format="mlx"),
        platform_info=DARWIN_ARM64,
        engine=(object(), object(), boom))
    with pytest.raises(BackendError, match="mlx generate failed"):
        rt.generate("hello")


# -- lifecycle ----------------------------------------------------------------------

def test_load_rejects_wrong_format():
    rt = _runtime()
    with pytest.raises(SpecError):
        rt.load(ModelRef(runtime="onnx", path="m.onnx", format="onnx"))


def test_load_unload_cycle():
    rt = MLXRuntime(platform_info=DARWIN_ARM64)
    ref = ModelRef(runtime="mlx", path="mlx-community/other", format="mlx")
    rt.load(ref)
    assert rt.info().model is ref
    rt.unload()
    assert rt.info().model is None


def test_health_names_platform_and_support():
    health = _runtime().health()
    assert health["platform"] == "darwin/arm64"
    assert health["platform_supported"] is True
    assert health["status"] == "ok"


def test_health_unavailable_off_platform():
    health = _runtime(platform_info=LINUX_X86).health()
    assert health["status"] == "unavailable"
    assert health["platform_supported"] is False


def test_health_degraded_without_model():
    rt = MLXRuntime(platform_info=DARWIN_ARM64)
    assert rt.health()["status"] == "degraded"


def test_warmup_noop_without_model():
    rt = MLXRuntime(platform_info=DARWIN_ARM64)
    rt.warmup()


def test_privacy_is_local():
    assert _runtime().privacy()["remote"] is False
