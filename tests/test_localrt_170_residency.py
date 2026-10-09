"""Slice 170 — model residency manager.

Unit tests for ``hugrgate.runtimes.residency``.
"""

from __future__ import annotations

import threading

from hugrgate.runtimes import FakeRuntime, ModelRef
from hugrgate.runtimes.residency import (
    ResidencyLease,
    ResidencyManager,
)


def _rt(name: str = "fake") -> FakeRuntime:
    rt = FakeRuntime()
    rt.name = name
    return rt


def _model(path: str = "/m.gguf") -> ModelRef:
    return ModelRef(runtime="fake", path=path, format="gguf")


def test_acquire_loads_and_tracks():
    mgr = ResidencyManager()
    rt = _rt()
    lease = mgr.acquire(rt, _model())
    assert isinstance(lease, ResidencyLease)
    entry = mgr.resident("fake")
    assert entry is not None
    assert entry.refcount == 1
    assert rt.info().model is not None
    assert mgr.is_resident("fake")
    assert mgr.is_resident("fake", _model())
    assert not mgr.is_resident("fake", _model("/other.gguf"))


def test_acquire_same_model_bumps_refcount():
    mgr = ResidencyManager()
    rt = _rt()
    loads = [0]
    orig_load = rt.load

    def counting_load(model):
        loads[0] += 1
        orig_load(model)

    rt.load = counting_load  # type: ignore[method-assign]
    a = mgr.acquire(rt, _model())
    b = mgr.acquire(rt, _model())
    assert loads[0] == 1  # loaded once
    assert mgr.resident("fake").refcount == 2
    a.release()
    assert mgr.resident("fake").refcount == 1
    assert rt.info().model is not None  # still loaded
    b.release()
    # Warm cache: refcount zero, but the model stays loaded until evict.
    entry = mgr.resident("fake")
    assert entry is not None and entry.refcount == 0
    assert rt.info().model is not None
    mgr.evict("fake")
    assert mgr.resident("fake") is None
    assert rt.info().model is None


def test_lease_context_manager_releases():
    mgr = ResidencyManager()
    rt = _rt()
    with mgr.acquire(rt, _model()):
        assert mgr.resident("fake").refcount == 1
    # Lease returned; the model stays warm (refcount zero).
    entry = mgr.resident("fake")
    assert entry is not None and entry.refcount == 0
    assert rt.info().model is not None


def test_lease_double_release_is_noop():
    mgr = ResidencyManager()
    rt = _rt()
    lease = mgr.acquire(rt, _model())
    lease.release()
    lease.release()
    assert mgr.resident("fake").refcount == 0  # never negative


def test_acquire_different_model_replaces():
    mgr = ResidencyManager()
    rt = _rt()
    lease = mgr.acquire(rt, _model("/a.gguf"))
    lease2 = mgr.acquire(rt, _model("/b.gguf"))
    entry = mgr.resident("fake")
    assert entry.model.path == "/b.gguf"
    assert entry.refcount == 1
    assert rt.info().model.path == "/b.gguf"
    lease.release()  # stale lease for /a.gguf: no-op
    assert mgr.resident("fake").refcount == 1
    lease2.release()
    # Warm cache: still resident at refcount zero.
    assert mgr.resident("fake").refcount == 0
    assert rt.info().model.path == "/b.gguf"


def test_evict_force_unloads():
    mgr = ResidencyManager()
    rt = _rt()
    mgr.acquire(rt, _model())
    mgr.acquire(rt, _model())
    evicted = mgr.evict("fake")
    assert evicted is not None
    assert evicted.refcount == 2
    assert not mgr.is_resident("fake")
    assert rt.info().model is None
    assert mgr.evict("fake") is None  # nothing resident: None
    assert mgr.evict("never-seen") is None


def test_touch_refreshes_last_used():
    mgr = ResidencyManager()
    rt = _rt()
    mgr.acquire(rt, _model())
    before = mgr.resident("fake").last_used_at
    mgr.touch("fake")
    after = mgr.resident("fake")
    assert after.last_used_at >= before
    assert after.touches >= 2
    mgr.touch("missing")  # no-op


def test_snapshot_is_a_copy():
    mgr = ResidencyManager()
    mgr.acquire(_rt("a"), _model())
    snap = mgr.snapshot()
    assert set(snap) == {"a"}
    snap.clear()
    assert mgr.is_resident("a")


def test_concurrent_acquire_release_is_safe():
    mgr = ResidencyManager()
    rt = _rt()
    errors: list[BaseException] = []

    def worker():
        try:
            for _ in range(50):
                with mgr.acquire(rt, _model()):
                    pass
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    # All leases returned; the model stays warm until evicted.
    entry = mgr.resident("fake")
    assert entry is not None and entry.refcount == 0
    assert rt.info().model is not None
    mgr.evict("fake")
    assert rt.info().model is None


def test_entry_to_dict():
    mgr = ResidencyManager()
    mgr.acquire(_rt(), _model())
    d = mgr.resident("fake").to_dict()
    assert d["runtime_name"] == "fake"
    assert d["refcount"] == 1
    assert "/m.gguf" in d["model"]
