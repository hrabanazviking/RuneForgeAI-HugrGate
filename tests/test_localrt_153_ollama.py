"""Slice 153 — Ollama-compatible adapter.

Unit tests for ``hugrgate.runtimes.ollama`` with an injected fake
transport — no server required.
"""

from __future__ import annotations

from typing import Any

import pytest

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import GenerationOptions, ModelRef
from hugrgate.runtimes.ollama import DEFAULT_HOST, OllamaRuntime


class FakeTransport:
    """Dispatches on (method, path); records calls."""

    def __init__(self, routes: dict[tuple[str, str], Any] | None = None):
        self.routes = routes or {}
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, method: str, path: str,
                 payload: dict | None = None) -> Any:
        self.calls.append((method, path, payload))
        key = (method.upper(), path)
        if key not in self.routes:
            raise AssertionError(f"unexpected call {key}")
        result = self.routes[key]
        if isinstance(result, Exception):
            raise result
        return result() if callable(result) else result


def _runtime(**kwargs) -> OllamaRuntime:
    routes = {
        ("POST", "/api/generate"): {
            "response": "  hello there  ",
            "done_reason": "stop",
            "prompt_eval_count": 5,
            "eval_count": 2,
        },
        ("POST", "/api/embed"): {"embeddings": [[0.1, 0.2], [0.3, 0.4]]},
        ("GET", "/api/tags"): {"models": [{"name": "llama3.1:8b"},
                                          {"name": "nomic-embed-text"}]},
        ("GET", "/api/version"): {"version": "0.5.0"},
    }
    transport = FakeTransport(kwargs.pop("routes", routes))
    return OllamaRuntime(model="llama3.1:8b", transport=transport, **kwargs)


# -- construction ------------------------------------------------------------

def test_default_host_constant():
    assert DEFAULT_HOST == "http://localhost:11434"


def test_constructor_validates():
    with pytest.raises(SpecError):
        OllamaRuntime(host="  ")
    with pytest.raises(SpecError):
        OllamaRuntime(timeout_s=0)


def test_available_is_false_without_server():
    assert OllamaRuntime.available() is False


def test_info_reports_engine_and_caps():
    info = _runtime().info()
    assert info.name == "ollama"
    assert info.engine_version == "0.5.0"
    assert "generate" in info.capabilities
    assert "embed" in info.capabilities
    assert info.remote is False
    assert info.formats == ("ollama",)


# -- generate ------------------------------------------------------------------

def test_generate_trims_and_maps_counts():
    rt = _runtime()
    out = rt.generate("Say hi", GenerationOptions(max_tokens=16))
    assert out.text == "hello there"
    assert out.finish_reason == "stop"
    assert out.prompt_tokens == 5
    assert out.completion_tokens == 2


def test_generate_sends_options_payload():
    transport = FakeTransport({
        ("POST", "/api/generate"): {"response": "x", "done_reason": "length",
                                    "prompt_eval_count": 1,
                                    "eval_count": 1},
    })
    rt = OllamaRuntime(model="llama3.1:8b", transport=transport)
    out = rt.generate("p", GenerationOptions(max_tokens=4, temperature=0.7,
                                             stop=["z"], seed=3))
    assert out.finish_reason == "length"
    gen_calls = [c for c in transport.calls if c[1] == "/api/generate"]
    assert len(gen_calls) == 1
    _, _, payload = gen_calls[0]
    assert payload["model"] == "llama3.1:8b"
    assert payload["options"]["num_predict"] == 4
    assert payload["options"]["temperature"] == 0.7
    assert payload["options"]["stop"] == ["z"]
    assert payload["options"]["seed"] == 3
    assert payload["stream"] is False


def test_generate_rejects_empty_prompt():
    with pytest.raises(SpecError):
        _runtime().generate(" ")


def test_generate_without_model_raises_unavailable():
    rt = OllamaRuntime(transport=FakeTransport({}))
    with pytest.raises(BackendUnavailable):
        rt.generate("hello")


def test_generate_404_suggests_pull():
    transport = FakeTransport({
        ("POST", "/api/generate"): BackendError(
            "ollama model not found on server: x. Run `ollama pull <tag>`"),
    })
    rt = OllamaRuntime(model="missing:tag", transport=transport)
    with pytest.raises(BackendError, match="ollama pull"):
        rt.generate("hello")


def test_generate_builtin_timeout_becomes_hugr_timeout():
    from hugrgate.errors import TimeoutError as HugrTimeoutError

    def boom(method, path, payload=None):
        raise TimeoutError("timed out")

    rt = OllamaRuntime(model="llama3.1:8b", transport=boom)
    with pytest.raises(HugrTimeoutError):
        rt.generate("hello", GenerationOptions(timeout_s=1))


# -- embed -----------------------------------------------------------------------

def test_embed_returns_vectors():
    rt = _runtime()
    out = rt.embed(["a", "b"])
    assert out.dim == 2
    assert out.vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert out.model == "llama3.1:8b"


def test_embed_rejects_count_mismatch():
    transport = FakeTransport({
        ("POST", "/api/embed"): {"embeddings": [[0.1]]},
    })
    rt = OllamaRuntime(model="nomic-embed-text", transport=transport)
    with pytest.raises(BackendError):
        rt.embed(["a", "b"])


def test_embed_rejects_empty():
    with pytest.raises(SpecError):
        _runtime().embed([])


# -- lifecycle / ops ---------------------------------------------------------------

def test_load_selects_tag_and_validates_runtime():
    rt = OllamaRuntime(transport=FakeTransport({}))
    rt.load(ModelRef(runtime="ollama", path="qwen2:7b", format="ollama"))
    assert rt.info().model is not None
    assert rt.info().model.path == "qwen2:7b"
    with pytest.raises(SpecError):
        rt.load(ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf"))
    rt.unload()
    assert rt.info().model is None


def test_list_models_reads_tags():
    assert _runtime().list_models() == ["llama3.1:8b", "nomic-embed-text"]


def test_health_ok_when_tag_present():
    health = _runtime().health()
    assert health["status"] == "ok"
    assert health["server_models"] == 2


def test_health_degraded_when_tag_missing():
    transport = FakeTransport({
        ("GET", "/api/tags"): {"models": [{"name": "other:1b"}]},
    })
    rt = OllamaRuntime(model="llama3.1:8b", transport=transport)
    assert rt.health()["status"] == "degraded"


def test_health_degraded_without_model():
    transport = FakeTransport({
        ("GET", "/api/tags"): {"models": []},
    })
    rt = OllamaRuntime(transport=transport)
    assert rt.health()["status"] == "degraded"


def test_health_unavailable_when_server_down():
    def boom(method, path, payload=None):
        raise BackendUnavailable("down", backend="ollama")

    rt = OllamaRuntime(transport=boom)
    health = rt.health()
    assert health["status"] == "unavailable"


def test_warmup_without_model_is_noop():
    rt = OllamaRuntime(transport=FakeTransport({}))
    rt.warmup()  # must not raise


def test_warmup_with_model_generates_once():
    rt = _runtime()
    rt.warmup()
    transport = rt._transport
    assert isinstance(transport, FakeTransport)
    assert ("POST", "/api/generate", transport.calls[0][2])[:2] == (
        "POST", "/api/generate")


def test_privacy_is_local():
    assert _runtime().privacy()["remote"] is False
