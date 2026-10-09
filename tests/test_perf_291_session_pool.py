"""Slice 291 — model-session pooling.

Covers: warm session reuse (load called once per session), per-model
isolation, max_models LRU eviction, health-check discards, sick-session
discard(), drop_model seam, factory/load failure mapping, validation,
stats, and shutdown.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import PoolError
from hugrgate.runtimes import LocalRuntime, ModelRef, RuntimeInfo
from hugrgate.runtimes.session_pool import ModelSessionPool


class FakeSessionRuntime(LocalRuntime):
    """Counting runtime: load/unload/close observable; health flappable."""

    loads = 0
    unloads = 0
    closes = 0

    def __init__(self):
        self.loaded_model = None
        self.sick = False
        self.closed = False
        self.name = "fake-session"

    @classmethod
    def available(cls):
        return True

    def info(self):
        return RuntimeInfo(name="fake-session", version="0",
                           capabilities=("generate",), formats=("gguf",))

    def load(self, model):
        if model.path == "explode.gguf":
            raise RuntimeError("load failed")
        FakeSessionRuntime.loads += 1
        self.loaded_model = model

    def unload(self):
        FakeSessionRuntime.unloads += 1
        self.loaded_model = None

    def close(self):
        FakeSessionRuntime.closes += 1
        self.closed = True
        self.unload()

    def health(self):
        base = super().health()
        base["status"] = "degraded" if self.sick else "ok"
        return base

    def generate(self, prompt, options=None):
        from hugrgate.runtimes import GenerationResult
        return GenerationResult(text="x", finish_reason="stop")


@pytest.fixture(autouse=True)
def _reset():
    FakeSessionRuntime.loads = 0
    FakeSessionRuntime.unloads = 0
    FakeSessionRuntime.closes = 0
    yield


def _model(path="a.gguf", runtime="llama-cpp"):
    return ModelRef(runtime=runtime, path=path, format="gguf")


def _pool(**kw):
    kw.setdefault("acquire_timeout_s", 3.0)
    kw.setdefault("idle_timeout_s", 60.0)
    return ModelSessionPool(**kw)


# --- reuse --------------------------------------------------------------------------

def test_warm_session_reused_load_called_once():
    pool = _pool()
    try:
        model = _model()
        with pool.acquire(model, FakeSessionRuntime) as h1:
            first = h1.resource
            assert first.loaded_model == model
        with pool.acquire(model, FakeSessionRuntime) as h2:
            assert h2.resource is first  # warm reuse
        assert FakeSessionRuntime.loads == 1
    finally:
        pool.shutdown()


def test_distinct_models_get_distinct_sessions():
    pool = _pool()
    try:
        with pool.acquire(_model("a.gguf"), FakeSessionRuntime) as ha:
            with pool.acquire(_model("b.gguf"), FakeSessionRuntime) as hb:
                assert ha.resource is not hb.resource
                assert ha.resource.loaded_model.path == "a.gguf"
                assert hb.resource.loaded_model.path == "b.gguf"
        assert FakeSessionRuntime.loads == 2
        assert [m.path for m in pool.models()] == ["a.gguf", "b.gguf"]
    finally:
        pool.shutdown()


def test_max_sessions_per_model():
    pool = _pool(max_sessions_per_model=1, acquire_timeout_s=0.3)
    try:
        model = _model()
        h1 = pool.acquire(model, FakeSessionRuntime)
        with pytest.raises(PoolError, match="exhausted"):
            pool.acquire(model, FakeSessionRuntime)
        h1.release()
        with pool.acquire(model, FakeSessionRuntime):
            pass  # slot freed
    finally:
        pool.shutdown()


# --- eviction -----------------------------------------------------------------------------

def test_lru_eviction_across_models():
    pool = _pool(max_models=2)
    try:
        pool.acquire(_model("a.gguf"), FakeSessionRuntime).release()
        pool.acquire(_model("b.gguf"), FakeSessionRuntime).release()
        # touch a so b becomes LRU
        pool.acquire(_model("a.gguf"), FakeSessionRuntime).release()
        pool.acquire(_model("c.gguf"), FakeSessionRuntime).release()
        paths = [m.path for m in pool.models()]
        assert paths == ["a.gguf", "c.gguf"], paths  # b evicted
        assert FakeSessionRuntime.closes >= 1  # evicted session closed
    finally:
        pool.shutdown()


def test_drop_model_seam():
    pool = _pool()
    try:
        with pool.acquire(_model("a.gguf"), FakeSessionRuntime):
            pass
        assert pool.drop_model(_model("a.gguf")) is True
        assert pool.models() == []
        assert pool.drop_model(_model("a.gguf")) is False  # idempotent-ish
        # re-acquire rebuilds
        with pool.acquire(_model("a.gguf"), FakeSessionRuntime):
            pass
        assert FakeSessionRuntime.loads == 2
    finally:
        pool.shutdown()


# --- health -------------------------------------------------------------------------------

def test_sick_session_discarded_on_checkout():
    pool = _pool()
    try:
        model = _model()
        with pool.acquire(model, FakeSessionRuntime) as h:
            sick = h.resource
        sick.sick = True  # goes sick while idle
        with pool.acquire(model, FakeSessionRuntime) as h2:
            assert h2.resource is not sick
        assert sick.closed is True
        assert FakeSessionRuntime.loads == 2
    finally:
        pool.shutdown()


def test_discard_mid_use():
    pool = _pool()
    try:
        model = _model()
        with pool.acquire(model, FakeSessionRuntime) as h:
            victim = h.resource
            h.discard()  # proved sick mid-generation
        assert victim.closed is True
        with pool.acquire(model, FakeSessionRuntime) as h2:
            assert h2.resource is not victim
    finally:
        pool.shutdown()


# --- failures -------------------------------------------------------------------------------

def test_load_failure_becomes_pool_error():
    pool = _pool()
    try:
        with pytest.raises(PoolError, match="factory failed"):
            pool.acquire(_model("explode.gguf"), FakeSessionRuntime)
    finally:
        pool.shutdown()


def test_bad_factory_rejected():
    pool = _pool()
    try:
        with pytest.raises(PoolError, match="must build a LocalRuntime"):
            pool.acquire(_model(), lambda: object())
        with pytest.raises(PoolError, match="must be callable"):
            pool.acquire(_model(), "not-callable")
    finally:
        pool.shutdown()


def test_bad_model_rejected():
    pool = _pool()
    try:
        with pytest.raises(PoolError, match="must be a ModelRef"):
            pool.acquire("a.gguf", FakeSessionRuntime)
    finally:
        pool.shutdown()


def test_config_validation():
    with pytest.raises(PoolError):
        ModelSessionPool(max_sessions_per_model=0)
    with pytest.raises(PoolError):
        ModelSessionPool(max_models=0)
    with pytest.raises(PoolError):
        ModelSessionPool(idle_timeout_s=0)
    with pytest.raises(PoolError):
        ModelSessionPool(acquire_timeout_s=-1)


def test_acquire_after_shutdown_rejected():
    pool = _pool()
    pool.shutdown()
    with pytest.raises(PoolError, match="shut down"):
        pool.acquire(_model(), FakeSessionRuntime)


# --- observability -------------------------------------------------------------------------------

def test_stats_shape():
    pool = _pool(max_models=4)
    try:
        with pool.acquire(_model("a.gguf"), FakeSessionRuntime):
            pass
        with pool.acquire(_model("b.gguf"), FakeSessionRuntime):
            pass
        stats = pool.stats()
        assert stats["models"] == 2
        assert stats["max_models"] == 4
        assert stats["total_live"] == 2
        assert stats["total_checkouts"] == 2
        assert len(stats["per_model"]) == 2
    finally:
        pool.shutdown()


def test_shutdown_closes_all_sessions():
    pool = _pool()
    with pool.acquire(_model("a.gguf"), FakeSessionRuntime):
        pass
    with pool.acquire(_model("b.gguf"), FakeSessionRuntime):
        pass
    pool.shutdown()
    assert FakeSessionRuntime.closes == 2
    assert pool.stats()["shutdown"] is True
    pool.shutdown()  # idempotent
