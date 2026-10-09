"""Slice 159 — TensorRT adapter boundary.

Unit tests for ``hugrgate.runtimes.tensorrt``. CUDA availability is
injected, so both sides of the NVIDIA boundary are exercised on any
host; execution goes through an injected executor (the real
``default_trt_executor`` needs a GPU and is *not* run here).
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, BackendUnavailable, SpecError
from hugrgate.runtimes import ModelRef
from hugrgate.runtimes.tensorrt import (
    TensorRTRuntime,
    _flatten,
    _unflatten,
)


def _executor(rows: list[list[float]]):
    def execute(engine, feed, input_names, output_name):
        assert set(feed) == set(input_names)
        return {output_name: rows}

    return execute


def _runtime(**kwargs) -> TensorRTRuntime:
    rows = kwargs.pop("rows", [[4.0, 1.0], [0.5, 3.5]])
    executor = kwargs.pop("executor", None) or _executor(rows)
    return TensorRTRuntime(
        model=ModelRef(runtime="tensorrt", path="m.engine",
                       format="tensorrt-engine"),
        cuda_override=kwargs.pop("cuda_override", True),
        input_names=["input_ids"],
        output_name="logits",
        encode_fn=lambda texts: {"input_ids": [[1]] * len(texts)},
        executor=executor,
        engine=kwargs.pop("engine", object()),
        **kwargs)


# -- boundary ------------------------------------------------------------------

def test_cuda_override_both_sides():
    assert TensorRTRuntime.cuda_available(True) is True
    assert TensorRTRuntime.cuda_available(False) is False


def test_available_false_without_cuda_or_package():
    assert TensorRTRuntime.available() is False  # no GPU here


def test_run_without_cuda_names_the_boundary():
    rt = _runtime(cuda_override=False)
    with pytest.raises(BackendUnavailable, match="NVIDIA CUDA GPU"):
        rt.embed(["hello"])


def test_info_reports_cuda_devices():
    info = _runtime().info()
    assert info.name == "tensorrt"
    assert info.devices == ("cuda",)
    assert info.formats == ("tensorrt-engine",)
    assert "embed" in info.capabilities


def test_generate_is_honestly_out_of_scope():
    with pytest.raises(BackendError, match="generate-capable"):
        _runtime().generate("hello")


# -- embed / classify (injected executor) ------------------------------------------

def test_embed_returns_rows():
    out = _runtime().embed(["a", "b"])
    assert out.vectors == [[4.0, 1.0], [0.5, 3.5]]
    assert out.dim == 2


def test_embed_needs_encode_fn():
    rt = _runtime()
    rt.encode_fn = None
    with pytest.raises(BackendError, match="encode_fn"):
        rt.embed(["a"])


def test_embed_needs_explicit_io_names():
    rt = TensorRTRuntime(
        model=ModelRef(runtime="tensorrt", path="m.engine",
                       format="tensorrt-engine"),
        cuda_override=True, engine=object(), output_name="y",
        encode_fn=lambda texts: {"x": [[1]]},
        executor=_executor([[1.0]]))
    with pytest.raises(BackendError, match="input_names"):
        rt.embed(["a"])
    rt2 = TensorRTRuntime(
        model=ModelRef(runtime="tensorrt", path="m.engine",
                       format="tensorrt-engine"),
        cuda_override=True, engine=object(), input_names=["x"],
        encode_fn=lambda texts: {"x": [[1]]},
        executor=_executor([[1.0]]))
    with pytest.raises(BackendError, match="output_name"):
        rt2.embed(["a"])


def test_classify_softmaxes_over_labels():
    (first, second) = _runtime().classify(["a", "b"], ["p", "q"])
    assert first.label == "p"
    assert second.label == "q"
    assert abs(sum(first.scores.values()) - 1.0) < 1e-12


def test_classify_rejects_dim_mismatch():
    with pytest.raises(BackendError, match="logits dim"):
        _runtime().classify(["a"], ["only"])


def test_executor_failure_surfaces():
    def boom(engine, feed, input_names, output_name):
        raise RuntimeError("cuda error")

    rt = _runtime(executor=boom)
    with pytest.raises(BackendError, match="tensorrt execution failed"):
        rt.embed(["a"])


# -- pure-python buffer helpers ------------------------------------------------------

def test_flatten_nested():
    out: list[float] = []
    _flatten([[1, 2], [3]], out)
    assert out == [1.0, 2.0, 3.0]


def test_unflatten_2d():
    assert _unflatten([1.0, 2.0, 3.0, 4.0], (2, 2)) == [
        [1.0, 2.0], [3.0, 4.0]]


def test_unflatten_1d():
    assert _unflatten([1.0, 2.0], (2,)) == [[1.0, 2.0]]


def test_unflatten_rejects_3d():
    with pytest.raises(BackendError):
        _unflatten([1.0] * 8, (2, 2, 2))


# -- lifecycle ---------------------------------------------------------------------------

def test_load_rejects_wrong_format():
    with pytest.raises(SpecError):
        _runtime().load(
            ModelRef(runtime="onnx", path="m.onnx", format="onnx"))


def test_load_unload_cycle():
    rt = TensorRTRuntime(cuda_override=True, engine=object())
    ref = ModelRef(runtime="tensorrt", path="n.plan",
                   format="tensorrt-engine")
    rt.load(ref)
    assert rt.info().model is ref
    rt.unload()
    assert rt.info().model is None


def test_no_model_raises_unavailable():
    rt = TensorRTRuntime(
        cuda_override=True, input_names=["x"], output_name="y",
        encode_fn=lambda texts: {"x": [[1]]},
        executor=_executor([[1.0]]))
    with pytest.raises(BackendUnavailable, match="no model loaded"):
        rt.embed(["a"])


def test_health_reports_cuda_and_status():
    health = _runtime().health()
    assert health["cuda"] is True
    assert health["status"] == "ok"


def test_health_unavailable_without_cuda():
    health = _runtime(cuda_override=False).health()
    assert health["status"] == "unavailable"
    assert health["cuda"] is False


def test_health_degraded_without_model():
    rt = TensorRTRuntime(cuda_override=True)
    assert rt.health()["status"] == "degraded"


def test_close_is_idempotent():
    rt = _runtime()
    rt.close()
    rt.close()


def test_privacy_is_local():
    assert _runtime().privacy()["remote"] is False
