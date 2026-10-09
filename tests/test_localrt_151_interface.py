"""Slice 151 — Local runtime interface v2.

Unit tests for ``hugrgate.runtimes``: the v2 contract, registries,
value objects, and the deterministic FakeRuntime.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import (
    CAP_CLASSIFY,
    CAP_EMBED,
    CAP_GENERATE,
    EmbeddingResult,
    FakeRuntime,
    GenerationOptions,
    GenerationResult,
    LocalRuntime,
    ModelRef,
    RuntimeInfo,
    RuntimeRegistry,
    format_from_path,
)


class MinimalRuntime(LocalRuntime):
    name = "minimal"

    @classmethod
    def available(cls) -> bool:
        return False

    def info(self) -> RuntimeInfo:
        return RuntimeInfo(
            name=self.name, engine="minimal", engine_version="1",
            available=False, devices=("cpu",), formats=(),
            capabilities=frozenset({CAP_GENERATE}), remote=False)

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        self._check_prompt(prompt)
        return GenerationResult(text="x", finish_reason="stop")


# -- ModelRef ------------------------------------------------------------

def test_model_ref_requires_runtime_and_path():
    with pytest.raises(SpecError):
        ModelRef(runtime="", path="m.gguf")
    with pytest.raises(SpecError):
        ModelRef(runtime="llama-cpp", path="  ")


def test_model_ref_display():
    ref = ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf",
                   alias="tiny")
    assert "tiny" in ref.display and "llama-cpp" in ref.display


# -- format_from_path -----------------------------------------------------

def test_format_from_path_known_suffixes(tmp_path):
    f = tmp_path / "model.gguf"
    f.write_bytes(b"x")
    assert format_from_path(f) == "gguf"
    assert format_from_path("w.onnx") == "onnx"
    assert format_from_path("w.safetensors") == "safetensors"
    assert format_from_path("plan.engine") == "tensorrt-engine"


def test_format_from_path_directory_is_hf(tmp_path):
    assert format_from_path(tmp_path) == "hf"


def test_format_from_path_unknown_suffix():
    assert format_from_path("model.xyz") == "unknown"


# -- GenerationOptions validation ------------------------------------------

def test_generation_options_rejects_bad_values():
    with pytest.raises(SpecError):
        GenerationOptions(max_tokens=0)
    with pytest.raises(SpecError):
        GenerationOptions(temperature=2.5)
    with pytest.raises(SpecError):
        GenerationOptions(top_p=0.0)
    with pytest.raises(SpecError):
        GenerationOptions(timeout_s=0.0)
    with pytest.raises(SpecError):
        GenerationOptions(grammar="root ::= .", json_schema={"type": "x"})


def test_generation_result_rejects_bad_finish_reason():
    with pytest.raises(SpecError):
        GenerationResult(text="x", finish_reason="maybe")


def test_embedding_result_validates_dims():
    with pytest.raises(SpecError):
        EmbeddingResult(vectors=[[1.0, 2.0]], dim=3)


# -- LocalRuntime contract ---------------------------------------------------

def test_generate_rejects_empty_prompt():
    rt = MinimalRuntime()
    with pytest.raises(SpecError):
        rt.generate("   ")


def test_default_embed_and_classify_are_unsupported():
    rt = MinimalRuntime()
    with pytest.raises(BackendError):
        rt.embed(["hello"])
    with pytest.raises(BackendError):
        rt.classify(["hello"], ["a"])
    with pytest.raises(BackendError):
        rt.tokenize("hello")


def test_health_never_raises_and_reports_unavailable():
    assert MinimalRuntime().health()["status"] == "unavailable"


def test_privacy_is_always_local():
    props = MinimalRuntime().privacy()
    assert props["remote"] is False


def test_close_and_warmup_defaults_are_safe():
    rt = MinimalRuntime()
    rt.warmup()
    rt.close()
    rt.close()  # idempotent


# -- RuntimeRegistry ----------------------------------------------------------

def test_registry_register_get_list():
    reg = RuntimeRegistry()
    rt = MinimalRuntime()
    reg.register(rt)
    assert reg.get("minimal") is rt
    assert reg.list() == ["minimal"]
    assert "minimal" in reg
    assert len(reg) == 1


def test_registry_rejects_duplicates_and_non_runtimes():
    reg = RuntimeRegistry()
    reg.register(MinimalRuntime())
    with pytest.raises(SpecError):
        reg.register(MinimalRuntime())
    with pytest.raises(TypeError):
        reg.register(object())  # type: ignore[arg-type]


def test_registry_replace_and_unregister():
    reg = RuntimeRegistry()
    first, second = MinimalRuntime(), MinimalRuntime()
    reg.register(first)
    reg.register(second, replace=True)
    assert reg.get("minimal") is second
    assert reg.unregister("minimal") is True
    assert reg.unregister("minimal") is False


def test_registry_get_or_raise_unknown():
    with pytest.raises(BackendUnavailable):
        RuntimeRegistry().get_or_raise("nope")


def test_registry_available_and_supporting():
    reg = RuntimeRegistry()
    reg.register(MinimalRuntime())
    reg.register(FakeRuntime())
    assert [r.name for r in reg.available_runtimes()] == ["fake"]
    assert {r.name for r in reg.supporting(CAP_EMBED)} == {"fake"}
    assert {r.name for r in reg.supporting(CAP_GENERATE)} == {
        "minimal", "fake"}


# -- FakeRuntime ---------------------------------------------------------------

def test_fake_runtime_is_deterministic():
    rt = FakeRuntime()
    a = rt.generate("hello world")
    b = rt.generate("hello world")
    assert a.text == b.text
    assert a.finish_reason == "stop"
    assert rt.generate("other prompt").text != a.text


def test_fake_runtime_temperature_zero_echoes_prompt():
    rt = FakeRuntime()
    out = rt.generate("the quick brown fox",
                      GenerationOptions(temperature=0.0, max_tokens=3))
    assert "the quick brown" in out.text


def test_fake_runtime_stop_sequences_apply():
    rt = FakeRuntime()
    out = rt.generate("hello world",
                      GenerationOptions(temperature=0.0, stop=("brown",)))
    assert "brown" not in out.text


def test_fake_runtime_constrained_finish_reasons():
    rt = FakeRuntime()
    assert rt.generate("p", GenerationOptions(
        json_schema={"type": "object"})).finish_reason == "constrained"
    assert rt.generate("p", GenerationOptions(
        grammar="root ::= 'a'")).finish_reason == "constrained"


def test_fake_runtime_embed_is_deterministic_and_normalized():
    rt = FakeRuntime(dim=32)
    first = rt.embed(["hello", "world"])
    second = rt.embed(["hello", "world"])
    assert first.vectors == second.vectors
    assert first.dim == 32
    assert len(first.vectors) == 2
    import math
    for vec in first.vectors:
        assert math.isclose(sum(v * v for v in vec), 1.0, rel_tol=1e-6)


def test_fake_runtime_embed_rejects_empty():
    with pytest.raises(SpecError):
        FakeRuntime().embed([])


def test_fake_runtime_classify_scores_sum_to_one():
    rt = FakeRuntime()
    (res,) = rt.classify(["the cat sat on the mat"], ["cat", "dog"])
    assert res.label == "cat"
    assert abs(sum(res.scores.values()) - 1.0) < 1e-9


def test_fake_runtime_tokenize_is_stable():
    rt = FakeRuntime()
    assert rt.tokenize("hello world") == rt.tokenize("hello world")
    assert len(rt.tokenize("a b c")) == 3


def test_fake_runtime_load_unload_lifecycle():
    rt = FakeRuntime()
    ref = ModelRef(runtime="fake", path="synthetic", format="unknown")
    assert rt.info().model is None
    rt.load(ref)
    assert rt.info().model is ref
    rt.unload()
    assert rt.info().model is None
    assert rt.health()["status"] == "ok"


def test_fake_runtime_limited_capabilities():
    rt = FakeRuntime(supports=frozenset({CAP_GENERATE}))
    assert not rt.info().supports(CAP_CLASSIFY)
    with pytest.raises(BackendError):
        rt.embed(["x"])
    with pytest.raises(BackendError):
        rt.classify(["x"], ["y"])


def test_fake_runtime_counts_calls():
    rt = FakeRuntime()
    rt.generate("a")
    rt.embed(["a"])
    assert rt.generate_calls == 1
    assert rt.embed_calls == 1
