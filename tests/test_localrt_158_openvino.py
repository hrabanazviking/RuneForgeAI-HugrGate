"""Slice 158 — OpenVINO adapter.

Unit tests for ``hugrgate.runtimes.openvino`` with an injected fake
compiled model — no openvino install, no IR files.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import ModelRef
from hugrgate.runtimes.openvino import OpenVINORuntime


class FakePort:
    def __init__(self, name: str):
        self._name = name

    def get_any_name(self) -> str:
        return self._name


class FakeCompiled:
    """Duck-types an OpenVINO compiled model."""

    def __init__(self, rows: list[list[float]],
                 input_name: str = "input_ids",
                 output_name: str = "logits"):
        self.rows = rows
        self.inputs = [FakePort(input_name)]
        self.outputs = [FakePort(output_name)]
        self.feeds: list[dict] = []

    def __call__(self, feed: dict) -> dict:
        self.feeds.append(feed)
        return {self.outputs[0].get_any_name(): self.rows}


def _runtime(**kwargs) -> OpenVINORuntime:
    compiled = kwargs.pop(
        "compiled", FakeCompiled([[3.0, 1.0], [0.5, 2.5]]))
    return OpenVINORuntime(
        model=ModelRef(runtime="openvino", path="m.xml",
                       format="openvino-ir"),
        encode_fn=lambda texts: {"input_ids": [[1]] * len(texts)},
        compiled=compiled,
        **kwargs)


# -- construction ----------------------------------------------------------------

def test_rejects_bad_device_and_streams():
    with pytest.raises(SpecError):
        OpenVINORuntime(device="  ")
    with pytest.raises(SpecError):
        OpenVINORuntime(num_streams=-1)


def test_available_reflects_install():
    assert OpenVINORuntime.available() is False


def test_info_advertises_embed_classify():
    info = _runtime().info()
    assert info.name == "openvino"
    assert "embed" in info.capabilities
    assert "classify" in info.capabilities
    assert "generate" not in info.capabilities
    assert info.formats == ("openvino-ir",)


def test_generate_is_honestly_out_of_scope():
    with pytest.raises(BackendError, match="generate-capable"):
        _runtime().generate("hello")


# -- embed / classify ----------------------------------------------------------------

def test_embed_returns_rows():
    out = _runtime().embed(["a", "b"])
    assert out.vectors == [[3.0, 1.0], [0.5, 2.5]]
    assert out.dim == 2


def test_embed_feeds_encoded_inputs():
    compiled = FakeCompiled([[1.0, 2.0]])
    rt = _runtime(compiled=compiled)
    rt.embed(["hello"])
    assert compiled.feeds[0] == {"input_ids": [[1]]}


def test_embed_needs_encode_fn():
    rt = OpenVINORuntime(
        model=ModelRef(runtime="openvino", path="m.xml",
                       format="openvino-ir"),
        compiled=FakeCompiled([[1.0]]))
    with pytest.raises(BackendError, match="encode_fn"):
        rt.embed(["x"])


def test_classify_softmaxes_over_labels():
    (first, second) = _runtime().classify(["a", "b"], ["p", "q"])
    assert first.label == "p"
    assert second.label == "q"
    assert abs(sum(first.scores.values()) - 1.0) < 1e-12


def test_classify_rejects_dim_mismatch():
    with pytest.raises(BackendError, match="logits dim"):
        _runtime().classify(["a"], ["only"])


def test_explicit_output_name_used():
    compiled = FakeCompiled([[9.0]], output_name="pooled")
    rt = _runtime(compiled=compiled, output_name="pooled")
    assert rt.embed(["a"]).vectors == [[9.0]]


def test_multi_output_without_name_refused():
    class MultiOut(FakeCompiled):
        def __init__(self):
            super().__init__([[1.0]])
            self.outputs = [FakePort("a"), FakePort("b")]

    rt = _runtime(compiled=MultiOut())
    with pytest.raises(BackendError, match="output_name"):
        rt.embed(["a"])


# -- lifecycle ---------------------------------------------------------------------------

def test_load_rejects_wrong_format():
    with pytest.raises(SpecError):
        _runtime().load(
            ModelRef(runtime="onnx", path="m.onnx", format="onnx"))


def test_load_unload_cycle():
    rt = OpenVINORuntime(compiled=FakeCompiled([[1.0]]))
    ref = ModelRef(runtime="openvino", path="n.xml", format="openvino-ir")
    rt.load(ref)
    assert rt.info().model is ref
    rt.unload()
    assert rt.info().model is None


def test_no_model_raises_unavailable():
    rt = OpenVINORuntime(encode_fn=lambda texts: {})
    with pytest.raises(BackendUnavailable):
        rt.embed(["a"])


def test_health_ok_with_compiled_and_model():
    health = _runtime().health()
    assert health["status"] == "ok"
    assert health["device"] == "CPU"


def test_health_unavailable_without_engine():
    rt = OpenVINORuntime(
        model=ModelRef(runtime="openvino", path="m.xml",
                       format="openvino-ir"))
    assert rt.health()["status"] == "unavailable"


def test_close_is_idempotent():
    rt = _runtime()
    rt.close()
    rt.close()


def test_privacy_is_local():
    assert _runtime().privacy()["remote"] is False
