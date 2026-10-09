"""Slice 156 — vLLM local adapter.

Unit tests for ``hugrgate.runtimes.vllm``: server mode via an injected
transport and in-process mode via an injected fake ``vllm.LLM``.
"""

from __future__ import annotations

from typing import Any

import pytest

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import GenerationOptions, ModelRef
from hugrgate.runtimes.vllm import DEFAULT_VLLM_HOST, VLLMRuntime


class FakeTransport:
    def __init__(self, routes: dict[str, Any]):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, path: str, payload: dict) -> Any:
        self.calls.append((path, payload))
        if path not in self.routes:
            raise AssertionError(f"unexpected call {path}")
        result = self.routes[path]
        if isinstance(result, Exception):
            raise result
        return result


class FakeOutput:
    def __init__(self, text: str, finish_reason: str):
        self.text = text
        self.finish_reason = finish_reason


class FakeRequestOutput:
    def __init__(self, text: str, finish_reason: str):
        self.outputs = [FakeOutput(text, finish_reason)]


class FakeLLM:
    def __init__(self, text: str = "in-process answer",
                 finish_reason: str = "stop"):
        self.text = text
        self.finish_reason = finish_reason
        self.params: list[tuple] = []

    def generate(self, prompts: list[str], params: Any):
        self.params.append((prompts, params))
        return [FakeRequestOutput(self.text, self.finish_reason)
                for _ in prompts]


def _server_routes(**overrides) -> dict[str, Any]:
    routes: dict[str, Any] = {
        "/v1/completions": {
            "choices": [{"text": "  server answer  ",
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        },
        "/v1/embeddings": {"data": [{"embedding": [0.2, 0.4]},
                                    {"embedding": [0.6, 0.8]}]},
        "/v1/models": {"data": [{"id": "meta-llama/Llama-3.1-8B"},
                                {"id": "other"}]},
    }
    routes.update(overrides)
    return routes


def _server(**kwargs) -> VLLMRuntime:
    transport = FakeTransport(
        kwargs.pop("routes", _server_routes()))
    return VLLMRuntime(model="meta-llama/Llama-3.1-8B",
                       transport=transport, **kwargs)


def _inprocess(**kwargs) -> VLLMRuntime:
    llm = kwargs.pop("llm", FakeLLM())
    return VLLMRuntime(model="meta-llama/Llama-3.1-8B", llm=llm, **kwargs)


# -- construction ----------------------------------------------------------------

def test_default_host_constant():
    assert DEFAULT_VLLM_HOST == "http://localhost:8000"


def test_rejects_bad_timeout():
    with pytest.raises(SpecError):
        VLLMRuntime(timeout_s=0)


def test_available_false_without_engine_or_server():
    assert VLLMRuntime.available() is False


def test_info_server_mode():
    info = _server().info()
    assert info.name == "vllm"
    assert "generate" in info.capabilities
    assert "embed" not in info.capabilities
    assert info.devices == ("cuda",)


def test_info_embedding_mode():
    info = _server(embedding=True).info()
    assert "embed" in info.capabilities
    assert "generate" not in info.capabilities


# -- server-mode generate --------------------------------------------------------------

def test_server_generate_maps_response():
    rt = _server()
    out = rt.generate("Hello", GenerationOptions(max_tokens=16))
    assert out.text == "server answer"
    assert out.finish_reason == "stop"
    assert out.prompt_tokens == 7
    assert out.completion_tokens == 3


def test_server_generate_sends_openai_payload():
    transport = FakeTransport(_server_routes())
    rt = VLLMRuntime(model="meta-llama/Llama-3.1-8B", transport=transport)
    rt.generate("Hi", GenerationOptions(max_tokens=5, temperature=0.3,
                                        stop=["!"], seed=11))
    path, payload = transport.calls[0]
    assert path == "/v1/completions"
    assert payload["model"] == "meta-llama/Llama-3.1-8B"
    assert payload["max_tokens"] == 5
    assert payload["temperature"] == 0.3
    assert payload["stop"] == ["!"]
    assert payload["seed"] == 11
    assert payload["stream"] is False


def test_server_generate_length_finish_reason():
    routes = _server_routes(**{
        "/v1/completions": {"choices": [{"text": "x",
                                         "finish_reason": "length"}]}})
    rt = _server(routes=routes)
    assert rt.generate("Hi").finish_reason == "length"


def test_server_generate_without_model_unavailable():
    rt = VLLMRuntime(transport=FakeTransport(_server_routes()))
    with pytest.raises(BackendUnavailable):
        rt.generate("Hi")


def test_server_generate_rejects_empty_prompt():
    with pytest.raises(SpecError):
        _server().generate("   ")


# -- in-process generate ---------------------------------------------------------------

def test_inprocess_generate_uses_llm():
    rt = _inprocess()
    out = rt.generate("Hello")
    assert out.text == "in-process answer"
    assert out.finish_reason == "stop"


def test_inprocess_generate_length_reason():
    rt = _inprocess(llm=FakeLLM(finish_reason="length"))
    assert rt.generate("Hello").finish_reason == "length"


def test_inprocess_generate_failure_surfaces():
    class BoomLLM(FakeLLM):
        def generate(self, prompts, params):
            raise RuntimeError("cuda oom")

    rt = _inprocess(llm=BoomLLM())
    with pytest.raises(BackendError, match="vllm in-process"):
        rt.generate("Hello")


def test_inprocess_builder_needs_install():
    with pytest.raises(BackendUnavailable):
        VLLMRuntime.in_process("meta-llama/Llama-3.1-8B")


# -- embed ---------------------------------------------------------------------------------

def test_server_embed_in_embedding_mode():
    rt = _server(embedding=True)
    out = rt.embed(["a", "b"])
    assert out.vectors == [[0.2, 0.4], [0.6, 0.8]]
    assert out.dim == 2


def test_embed_refused_in_generate_mode():
    with pytest.raises(BackendError):
        _server().embed(["a"])


def test_generate_refused_in_embedding_mode():
    with pytest.raises(BackendError):
        _server(embedding=True).generate("hi")


def test_inprocess_embed_refused_honestly():
    rt = _inprocess(embedding=True)
    with pytest.raises(BackendError, match="--task embed"):
        rt.embed(["a"])


def test_embed_count_mismatch_refused():
    routes = _server_routes(**{
        "/v1/embeddings": {"data": [{"embedding": [0.1]}]}})
    rt = _server(routes=routes, embedding=True)
    with pytest.raises(BackendError):
        rt.embed(["a", "b"])


# -- lifecycle / health ----------------------------------------------------------------------

def test_load_rejects_wrong_format():
    rt = _server()
    with pytest.raises(SpecError):
        rt.load(ModelRef(runtime="gguf", path="m.gguf", format="gguf"))


def test_load_unload_cycle():
    rt = VLLMRuntime(transport=FakeTransport(_server_routes()))
    ref = ModelRef(runtime="vllm", path="other", format="hf")
    rt.load(ref)
    assert rt.info().model is ref
    rt.unload()
    assert rt.info().model is None


def test_health_ok_when_model_served():
    health = _server().health()
    assert health["status"] == "ok"


def test_health_degraded_when_model_not_served():
    rt = VLLMRuntime(model="not-served",
                     transport=FakeTransport(_server_routes()))
    assert rt.health()["status"] == "degraded"


def test_health_unavailable_when_server_down():
    def boom(path, payload):
        raise BackendUnavailable("down", backend="vllm")

    rt = VLLMRuntime(transport=boom)
    assert rt.health()["status"] == "unavailable"


def test_health_inprocess_ok():
    rt = _inprocess()
    assert rt.health()["status"] == "ok"


def test_warmup_noop_without_model():
    rt = VLLMRuntime(transport=FakeTransport(_server_routes()))
    rt.warmup()


def test_privacy_is_local():
    assert _server().privacy()["remote"] is False
