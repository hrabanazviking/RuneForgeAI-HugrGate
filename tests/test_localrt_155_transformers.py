"""Slice 155 — Transformers adapter.

Unit tests for ``hugrgate.runtimes.transformers_rt`` with an injected
fake pipeline — no transformers install, no downloads.
"""

from __future__ import annotations

from typing import Any

import pytest

from hugrgate.backends.nli import NLIBackend
from hugrgate.errors import BackendError, SpecError
from hugrgate.runtimes import GenerationOptions, ModelRef
from hugrgate.runtimes.transformers_rt import TransformersRuntime
from hugrgate.spec import DecisionSpec


class FakePipe:
    """Duck-types a transformers pipeline for one task."""

    def __init__(self, task: str):
        self.task = task
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.task == "text-generation":
            prompt = args[0]
            return [{"generated_text": prompt + " and they lived happily"}]
        if self.task == "feature-extraction":
            texts = args[0]
            return [[[0.5, 1.5], [1.5, 0.5]] for _ in texts]
        if self.task == "zero-shot-classification":
            text = args[0]
            labels = kwargs["candidate_labels"]
            scores = [0.9 if text.split()[0] in label else 0.1 / len(labels)
                      for label in labels]
            total = sum(scores)
            scores = [s / total for s in scores]
            order = sorted(range(len(labels)), key=lambda i: -scores[i])
            return {"labels": [labels[i] for i in order],
                    "scores": [scores[i] for i in order]}
        if self.task == "text-classification":
            return [{"label": "POSITIVE", "score": 0.98}]
        raise AssertionError(f"unexpected task {self.task}")


def _runtime(task: str, **kwargs) -> TransformersRuntime:
    return TransformersRuntime(
        model=ModelRef(runtime="transformers", path="org/tiny",
                       format="hf"),
        task=task, pipe=FakePipe(task), **kwargs)


# -- construction ----------------------------------------------------------------

def test_rejects_unknown_task():
    with pytest.raises(SpecError):
        TransformersRuntime(task="translate")


def test_rejects_bad_device():
    with pytest.raises(SpecError):
        TransformersRuntime(task="text-generation", device=-2)


def test_available_reflects_install():
    assert TransformersRuntime.available() is False


def test_info_capabilities_follow_task():
    assert "generate" in _runtime("text-generation").info().capabilities
    assert "embed" in _runtime("feature-extraction").info().capabilities
    assert "classify" in _runtime(
        "zero-shot-classification").info().capabilities
    assert "generate" not in _runtime(
        "feature-extraction").info().capabilities


# -- generate ----------------------------------------------------------------------

def test_generate_strips_prompt_prefix():
    rt = _runtime("text-generation")
    out = rt.generate("Once upon a time",
                      GenerationOptions(max_tokens=10))
    assert out.text == "and they lived happily"
    assert out.finish_reason == "stop"


def test_generate_passes_sampling_knobs():
    rt = _runtime("text-generation")
    rt.generate("hi", GenerationOptions(max_tokens=5, temperature=0.8,
                                        top_p=0.9))
    _, kwargs = rt._pipe.calls[0]
    assert kwargs["max_new_tokens"] == 5
    assert kwargs["temperature"] == 0.8
    assert kwargs["top_p"] == 0.9
    assert kwargs["do_sample"] is True


def test_generate_greedy_when_temperature_zero():
    rt = _runtime("text-generation")
    rt.generate("hi", GenerationOptions(temperature=0.0))
    _, kwargs = rt._pipe.calls[0]
    assert kwargs["do_sample"] is False


def test_generate_wrong_task_refused():
    rt = _runtime("feature-extraction")
    with pytest.raises(BackendError, match="does not implement"):
        rt.generate("hi")


def test_generate_rejects_empty_prompt():
    with pytest.raises(SpecError):
        _runtime("text-generation").generate("  ")


# -- embed ---------------------------------------------------------------------------

def test_embed_mean_pools_and_normalizes():
    import math
    rt = _runtime("feature-extraction")
    out = rt.embed(["hello", "world"])
    assert len(out.vectors) == 2
    assert out.dim == 2
    for vec in out.vectors:
        assert math.isclose(sum(v * v for v in vec), 1.0, rel_tol=1e-9)
    # mean of [0.5,1.5] and [1.5,0.5] is [1.0,1.0], normalized
    assert out.vectors[0] == pytest.approx([0.70710678, 0.70710678])


def test_embed_wrong_task_refused():
    with pytest.raises(BackendError):
        _runtime("text-generation").embed(["hi"])


# -- classify ---------------------------------------------------------------------------

def test_zero_shot_classify_scores_labels():
    rt = _runtime("zero-shot-classification")
    (res,) = rt.classify(["cats are great"], ["cats", "dogs"])
    assert res.label == "cats"
    assert abs(sum(res.scores.values()) - 1.0) < 1e-9


def test_text_classification_uses_model_labels():
    rt = _runtime("text-classification")
    (res,) = rt.classify(["I love this"], ["POSITIVE", "NEGATIVE"])
    assert res.label == "POSITIVE"
    assert res.scores == {"POSITIVE": 0.98}


def test_classify_wrong_task_refused():
    with pytest.raises(BackendError):
        _runtime("text-generation").classify(["x"], ["y"])


# -- NLI bridge ---------------------------------------------------------------------------

def test_as_nli_fn_feeds_nli_backend():
    rt = _runtime("zero-shot-classification")
    backend = NLIBackend(nli_fn=rt.as_nli_fn())
    spec = DecisionSpec(type="binary", statement="cats are great")
    result = backend.evaluate({"premise": "cats are great"}, spec)
    assert result.value == "true"
    assert result.backend == "nli"


def test_as_nli_fn_rejects_wrong_task():
    rt = _runtime("text-generation")
    with pytest.raises(BackendError):
        rt.as_nli_fn()


# -- lifecycle ------------------------------------------------------------------------------

def test_load_rejects_wrong_format():
    rt = _runtime("text-generation")
    with pytest.raises(SpecError):
        rt.load(ModelRef(runtime="onnx", path="m.onnx", format="onnx"))


def test_load_unload_cycle():
    rt = TransformersRuntime(pipe=FakePipe("text-generation"))
    ref = ModelRef(runtime="transformers", path="org/other", format="hf")
    rt.load(ref)
    assert rt.info().model is ref
    rt.unload()
    assert rt.info().model is None


def test_warmup_dispatches_by_task():
    for task in ("text-generation", "feature-extraction",
                 "zero-shot-classification"):
        rt = _runtime(task)
        rt.warmup()  # must not raise
        assert rt._pipe.calls, task


def test_health_ok_with_pipe_and_model():
    health = _runtime("text-generation").health()
    assert health["status"] == "ok"
    assert health["task"] == "text-generation"


def test_privacy_is_local():
    assert _runtime("text-generation").privacy()["remote"] is False
