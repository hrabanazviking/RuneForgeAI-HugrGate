"""Slice 154 — ONNX Runtime adapter.

Unit tests for ``hugrgate.runtimes.onnx`` with an injected fake
session — no onnxruntime install, no model file.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import ModelRef
from hugrgate.runtimes.onnx import OnnxRuntime, softmax


class FakeIONode:
    def __init__(self, name: str):
        self.name = name


class FakeSession:
    """Duck-types onnxruntime.InferenceSession."""

    def __init__(self, rows: list[list[float]],
                 input_name: str = "input_ids",
                 output_name: str = "logits"):
        self.rows = rows
        self._input_name = input_name
        self._output_name = output_name
        self.feeds: list[dict] = []

    def get_inputs(self):
        return [FakeIONode(self._input_name)]

    def get_outputs(self):
        return [FakeIONode(self._output_name)]

    def run(self, output_names: list[str], feed: dict):
        assert output_names == [self._output_name]
        self.feeds.append(feed)
        return [self.rows]


def _runtime(**kwargs) -> OnnxRuntime:
    session = kwargs.pop(
        "session", FakeSession([[2.0, 1.0, 0.5], [0.1, 0.2, 3.0]]))
    return OnnxRuntime(
        model=ModelRef(runtime="onnx", path="m.onnx", format="onnx"),
        encode_fn=lambda texts: {"input_ids": [[1, 2]] * len(texts)},
        session=session,
        **kwargs)


# -- softmax ------------------------------------------------------------------

def test_softmax_sums_to_one_and_prefers_max():
    probs = softmax([2.0, 1.0, 0.5])
    assert abs(sum(probs) - 1.0) < 1e-12
    assert probs[0] > probs[1] > probs[2]


def test_softmax_stable_for_large_logits():
    probs = softmax([1000.0, 999.0])
    assert abs(sum(probs) - 1.0) < 1e-12
    assert probs[0] > 0.7


def test_softmax_rejects_empty():
    with pytest.raises(SpecError):
        softmax([])


# -- availability / info -----------------------------------------------------------

def test_available_reflects_install():
    assert OnnxRuntime.available() is False


def test_info_advertises_embed_and_classify():
    info = _runtime().info()
    assert info.name == "onnx"
    assert "embed" in info.capabilities
    assert "classify" in info.capabilities
    assert "generate" not in info.capabilities
    assert info.remote is False


def test_constructor_validates_threads():
    with pytest.raises(SpecError):
        OnnxRuntime(intra_op_num_threads=-1)


# -- generate scope ------------------------------------------------------------------

def test_generate_is_honestly_out_of_scope():
    rt = _runtime()
    with pytest.raises(BackendError, match="generate-capable"):
        rt.generate("hello")


# -- embed ------------------------------------------------------------------------------

def test_embed_runs_session_and_returns_rows():
    rt = _runtime()
    out = rt.embed(["a", "b"])
    assert out.vectors == [[2.0, 1.0, 0.5], [0.1, 0.2, 3.0]]
    assert out.dim == 3
    assert out.model == "m.onnx"


def test_embed_feeds_encoded_inputs():
    session = FakeSession([[1.0]])
    rt = _runtime(session=session)
    rt.embed(["hello"])
    assert session.feeds[0] == {"input_ids": [[1, 2]]}


def test_embed_needs_encode_fn():
    rt = OnnxRuntime(
        model=ModelRef(runtime="onnx", path="m.onnx", format="onnx"),
        session=FakeSession([[1.0]]))
    with pytest.raises(BackendError, match="encode_fn"):
        rt.embed(["hello"])


def test_embed_rejects_empty():
    with pytest.raises(SpecError):
        _runtime().embed([])


def test_embed_row_count_must_match():
    rt = _runtime(session=FakeSession([[1.0, 2.0]]))
    with pytest.raises(BackendError):
        rt.embed(["a", "b"])


# -- classify ------------------------------------------------------------------------------

def test_classify_softmaxes_logits_over_labels():
    rt = _runtime()
    (first, second) = rt.classify(["a", "b"], ["x", "y", "z"])
    assert first.label == "x"
    assert second.label == "z"
    assert abs(sum(first.scores.values()) - 1.0) < 1e-12


def test_classify_rejects_dim_mismatch():
    rt = _runtime()
    with pytest.raises(BackendError, match="logits dim"):
        rt.classify(["a"], ["only-one"])


def test_classify_rejects_empty_labels():
    with pytest.raises(SpecError):
        _runtime().classify(["a"], [])


# -- explicit IO names ------------------------------------------------------------------------

def test_explicit_output_name_used():
    session = FakeSession([[0.5]], output_name="pooled")
    rt = _runtime(session=session, output_name="pooled")
    out = rt.embed(["a"])
    assert out.vectors == [[0.5]]


def test_multi_output_without_name_refused():
    class MultiOut(FakeSession):
        def get_outputs(self):
            return [FakeIONode("a"), FakeIONode("b")]

    rt = _runtime(session=MultiOut([[0.5]]))
    with pytest.raises(BackendError, match="output_name"):
        rt.embed(["a"])


# -- lifecycle -----------------------------------------------------------------------------------

def test_load_rejects_non_onnx():
    rt = _runtime()
    with pytest.raises(SpecError):
        rt.load(ModelRef(runtime="gguf", path="m.gguf", format="gguf"))


def test_load_is_idempotent_and_unload_clears():
    session = FakeSession([[1.0]])
    rt = OnnxRuntime(session=session)
    ref = ModelRef(runtime="onnx", path="m.onnx", format="onnx")
    rt.load(ref)
    rt.load(ref)
    assert rt.info().model is ref
    rt.unload()
    assert rt.info().model is None


def test_no_model_raises_unavailable():
    rt = OnnxRuntime(encode_fn=lambda texts: {})
    with pytest.raises(BackendUnavailable):
        rt.embed(["a"])


def test_health_ok_with_session_and_model():
    assert _runtime().health()["status"] == "ok"


def test_health_unavailable_without_engine_or_session():
    rt = OnnxRuntime(
        model=ModelRef(runtime="onnx", path="m.onnx", format="onnx"))
    assert rt.health()["status"] == "unavailable"


def test_close_drops_session():
    rt = _runtime()
    rt.close()
    rt.close()  # idempotent


def test_privacy_is_local():
    assert _runtime().privacy()["remote"] is False
