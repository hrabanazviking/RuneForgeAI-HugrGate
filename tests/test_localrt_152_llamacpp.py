"""Slice 152 — llama.cpp adapter.

Unit tests for ``hugrgate.runtimes.llama_cpp`` and the legacy-compat
``LlamaCppEngine`` rewire in ``hugrgate.backends.llm``. A fake engine
object stands in for ``llama_cpp.Llama`` — no model download.
"""

from __future__ import annotations

import pytest

from hugrgate.backends.llm import (
    LlamaCppEngine,
    LLMBackend,
    LLMChoice,
)
from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import (
    CAP_EMBED,
    CAP_GENERATE,
    CAP_GRAMMAR,
    GenerationOptions,
    ModelRef,
)
from hugrgate.runtimes.llama_cpp import LlamaCppRuntime
from hugrgate.spec import DecisionSpec


class FakeLlama:
    """Duck-types llama_cpp.Llama for the paths the runtime uses."""

    def __init__(self, text: str = "yes",
                 token_logprobs: list[float] | None = None):
        self.text = text
        self.token_logprobs = token_logprobs if token_logprobs is not None \
            else [-0.1, -0.2]
        self.calls: list[dict] = []
        self.closed = False

    def __call__(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return {
            "choices": [{
                "text": self.text,
                "logprobs": {"token_logprobs": self.token_logprobs},
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1},
        }

    def create_embedding(self, texts: list[str]):
        return {"data": [{"embedding": [0.1, 0.2, 0.3]} for _ in texts]}

    def tokenize(self, data: bytes):
        return list(range(len(data.split())))

    def close(self):
        self.closed = True


def _runtime(**kwargs) -> LlamaCppRuntime:
    ref = ModelRef(runtime="llama-cpp", path="tiny.gguf", format="gguf")
    return LlamaCppRuntime(model=ref, llama=FakeLlama(), **kwargs)


# -- availability / info --------------------------------------------------------

def test_available_reflects_install():
    assert LlamaCppRuntime.available() is False  # not installed in venv


def test_info_advertises_capabilities():
    info = _runtime().info()
    assert info.name == "llama-cpp"
    assert CAP_GENERATE in info.capabilities
    assert CAP_GRAMMAR in info.capabilities
    assert info.remote is False
    assert info.formats == ("gguf",)


def test_embedding_mode_advertises_embed_not_generate():
    rt = _runtime(embedding=True)
    assert CAP_EMBED in rt.info().capabilities
    assert CAP_GENERATE not in rt.info().capabilities


def test_constructor_validates_params():
    with pytest.raises(SpecError):
        LlamaCppRuntime(n_ctx=0)
    with pytest.raises(SpecError):
        LlamaCppRuntime(n_gpu_layers=-1)


# -- generate --------------------------------------------------------------------

def test_generate_returns_result_with_usage():
    rt = _runtime()
    out = rt.generate("Is it raining?",
                      GenerationOptions(max_tokens=8, temperature=0.0))
    assert out.text == "yes"
    assert out.finish_reason == "stop"
    assert out.prompt_tokens == 10
    assert out.completion_tokens == 1
    assert out.latency_s >= 0.0


def test_generate_passes_options_to_engine():
    fake = FakeLlama()
    rt = LlamaCppRuntime(
        model=ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf"),
        llama=fake)
    rt.generate("prompt",
                GenerationOptions(max_tokens=5, temperature=0.5,
                                  stop=["x"], seed=7,
                                  grammar="root ::= 'a'"))
    call = fake.calls[0]
    assert call["max_tokens"] == 5
    assert call["temperature"] == 0.5
    assert call["stop"] == ["x"]
    assert call["seed"] == 7
    assert call["grammar"] == "root ::= 'a'"


def test_generate_rejects_empty_prompt():
    with pytest.raises(SpecError):
        _runtime().generate("  ")


def test_generate_without_model_raises_unavailable():
    rt = LlamaCppRuntime(llama=None)
    with pytest.raises(BackendUnavailable):
        rt.generate("hello")


def test_generate_in_embedding_mode_refused():
    rt = _runtime(embedding=True)
    with pytest.raises(BackendError):
        rt.generate("hello")


def test_generate_timeout_enforced():
    import time as _time

    class SlowLlama(FakeLlama):
        def __call__(self, prompt: str, **kwargs):
            _time.sleep(0.2)
            return super().__call__(prompt, **kwargs)

    rt = LlamaCppRuntime(
        model=ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf"),
        llama=SlowLlama())
    from hugrgate.errors import TimeoutError
    with pytest.raises(TimeoutError):
        rt.generate("hello", GenerationOptions(timeout_s=0.05))


# -- embed / tokenize --------------------------------------------------------------

def test_embed_in_embedding_mode():
    rt = _runtime(embedding=True)
    out = rt.embed(["hello", "world"])
    assert out.dim == 3
    assert len(out.vectors) == 2


def test_embed_refused_in_generate_mode():
    with pytest.raises(BackendError):
        _runtime().embed(["hello"])


def test_tokenize_delegates_to_engine():
    rt = _runtime()
    assert rt.tokenize("hello world") == [0, 1]


def test_tokenize_rejects_empty():
    with pytest.raises(SpecError):
        _runtime().tokenize(" ")


# -- lifecycle ----------------------------------------------------------------------

def test_load_rejects_non_gguf():
    rt = _runtime()
    with pytest.raises(SpecError):
        rt.load(ModelRef(runtime="onnx", path="m.onnx", format="onnx"))


def test_load_unknown_format_accepted_with_idempotence():
    rt = LlamaCppRuntime(llama=FakeLlama())
    ref = ModelRef(runtime="llama-cpp", path="m.bin", format="unknown")
    rt.load(ref)
    assert rt.info().model is ref
    rt.load(ref)  # idempotent, no error
    rt.unload()
    assert rt.info().model is None


def test_close_is_idempotent_and_closes_engine():
    fake = FakeLlama()
    rt = LlamaCppRuntime(
        model=ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf"),
        llama=fake)
    rt.close()
    assert fake.closed is True
    rt.close()  # second close: engine already gone, no error


def test_health_reports_degraded_without_model():
    rt = LlamaCppRuntime(llama=FakeLlama())
    assert rt.health()["status"] == "degraded"


# -- legacy compat -------------------------------------------------------------------

def test_legacy_engine_requires_install_at_construction():
    with pytest.raises(BackendUnavailable):
        LlamaCppEngine("model.gguf")


def test_legacy_engine_delegates_to_runtime():
    engine = LlamaCppEngine.__new__(LlamaCppEngine)
    LlamaCppRuntime.__init__(
        engine,
        model=ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf"),
        llama=FakeLlama(text="no", token_logprobs=[-0.5]))
    choice = engine.generate("prompt", ["yes", "no"], 8, 5.0)
    assert isinstance(choice, LLMChoice)
    assert choice.value == "no"
    assert 0.0 < choice.confidence < 1.0


def test_legacy_engine_serves_llm_backend():
    engine = LlamaCppEngine.__new__(LlamaCppEngine)
    LlamaCppRuntime.__init__(
        engine,
        model=ModelRef(runtime="llama-cpp", path="m.gguf", format="gguf"),
        llama=FakeLlama(text="escalate"))
    backend = LLMBackend(engine=engine, max_tokens=8)
    spec = DecisionSpec(type="categorical",
                        options=["monitor", "escalate", "ignore"],
                        statement="pick one")
    result = backend.evaluate({"text": "alert"}, spec)
    assert result.value == "escalate"
    assert result.backend == "local-llm"
