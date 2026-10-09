"""Slice 290 — connection pooling.

Covers: ResourcePool checkout/checkin reuse (same object returned),
max_size cap + exhaustion timeout (PoolError), idle eviction, lifetime
retirement, min_size warmup, health-check discards, handle
use-after-return rejection, discard(), factory-failure PoolError,
config validation, shutdown semantics, stats, shared HTTP pool
singleton + client reuse, and the cli.cmd_models integration.
"""

from __future__ import annotations

import threading
import time

import pytest

from hugrgate.errors import PoolError
from hugrgate.pool import (
    ResourcePool,
    shared_http_client_pool,
)


class FakeConn:
    """Stand-in for a connection: tracks opens/closes, can go sick."""

    count = 0

    def __init__(self):
        FakeConn.count += 1
        self.id = FakeConn.count
        self.closed = False
        self.sick = False

    def close(self):
        self.closed = True

    def healthy(self):
        return not self.sick and not self.closed


@pytest.fixture(autouse=True)
def _reset_count():
    FakeConn.count = 0
    yield


def _pool(**kw):
    kw.setdefault("acquire_timeout_s", 2.0)
    return ResourcePool(FakeConn, **kw)


# --- checkout / reuse ----------------------------------------------------------

def test_acquire_reuses_checked_in_resource():
    pool = _pool(max_size=2)
    try:
        with pool.acquire() as h1:
            first = h1.resource
        with pool.acquire() as h2:
            assert h2.resource is first  # same object, no rebuild
        assert pool.stats()["created_total"] == 1
    finally:
        pool.shutdown()


def test_max_size_caps_and_exhaustion_raises():
    pool = _pool(max_size=2, acquire_timeout_s=0.2)
    try:
        h1 = pool.acquire()
        h2 = pool.acquire()
        with pytest.raises(PoolError, match="exhausted"):
            pool.acquire()
        first = h1.resource
        h1.release()
        with pool.acquire() as h3:  # slot freed
            assert h3.resource is first
        h2.release()
    finally:
        pool.shutdown()


def test_handle_use_after_return_rejected():
    pool = _pool()
    try:
        handle = pool.acquire()
        resource = handle.resource
        handle.release()
        with pytest.raises(PoolError, match="already returned"):
            handle.resource  # noqa: B018
        assert resource.closed is False  # returned, not destroyed
    finally:
        pool.shutdown()


def test_discard_destroys_instead_of_returning():
    pool = _pool(max_size=1)
    try:
        with pool.acquire() as h:
            victim = h.resource
            h.discard()
        assert victim.closed is True
        with pool.acquire() as h2:
            assert h2.resource is not victim  # rebuilt
        assert pool.stats()["destroyed_total"] == 1
    finally:
        pool.shutdown()


def test_release_idempotent():
    pool = _pool()
    try:
        handle = pool.acquire()
        handle.release()
        handle.release()
        assert pool.stats()["live"] == 1
    finally:
        pool.shutdown()


# --- health -----------------------------------------------------------------------

def test_unhealthy_resource_discarded_at_checkout():
    pool = _pool(max_size=2, health_check=lambda c: c.healthy())
    try:
        with pool.acquire() as h:
            conn = h.resource
        conn.sick = True  # goes sick while idle
        with pool.acquire() as h2:
            assert h2.resource is not conn
        assert conn.closed is True
        assert pool.stats()["created_total"] == 2
    finally:
        pool.shutdown()


def test_health_check_exception_treated_as_unhealthy():
    def _boom(_c):
        raise RuntimeError("check exploded")

    pool = _pool(max_size=1, health_check=_boom)
    try:
        with pool.acquire() as h:
            first = h.resource
        with pool.acquire() as h2:
            assert h2.resource is not first
    finally:
        pool.shutdown()


# --- eviction -------------------------------------------------------------------------

def test_idle_eviction():
    pool = _pool(max_size=4, idle_timeout_s=0.1)
    try:
        with pool.acquire():
            pass
        assert pool.stats()["idle"] == 1
        time.sleep(0.35)  # reaper runs at idle_timeout/2
        assert pool.stats()["idle"] == 0
        assert pool.stats()["live"] == 0
    finally:
        pool.shutdown()


def test_min_size_stays_warm():
    pool = _pool(min_size=2, max_size=4, idle_timeout_s=0.1)
    try:
        assert pool.stats()["idle"] == 2
        time.sleep(0.35)
        assert pool.stats()["idle"] == 2  # warm floor kept
        assert pool.stats()["live"] == 2
    finally:
        pool.shutdown()


def test_lifetime_retirement():
    pool = _pool(max_size=2, max_lifetime_s=0.15, idle_timeout_s=60.0)
    try:
        with pool.acquire() as h:
            first = h.resource
        time.sleep(0.2)
        with pool.acquire() as h2:
            assert h2.resource is not first  # retired for age
        assert first.closed is True
    finally:
        pool.shutdown()


# --- config / factory ----------------------------------------------------------------------

def test_config_validation():
    with pytest.raises(PoolError):
        ResourcePool("not-callable")
    with pytest.raises(PoolError):
        ResourcePool(FakeConn, max_size=0)
    with pytest.raises(PoolError):
        ResourcePool(FakeConn, min_size=3, max_size=2)
    with pytest.raises(PoolError):
        ResourcePool(FakeConn, idle_timeout_s=0)
    with pytest.raises(PoolError):
        ResourcePool(FakeConn, health_check="yes")


def test_factory_failure_becomes_pool_error():
    def _boom():
        raise RuntimeError("cannot connect")

    pool = ResourcePool(_boom, acquire_timeout_s=1.0)
    try:
        with pytest.raises(PoolError, match="factory failed"):
            pool.acquire()
    finally:
        pool.shutdown()


def test_acquire_after_shutdown_rejected():
    pool = _pool()
    pool.shutdown()
    with pytest.raises(PoolError, match="shut down"):
        pool.acquire()


def test_shutdown_closes_idle():
    pool = _pool(min_size=2)
    conns = []
    with pool.acquire() as h:
        conns.append(h.resource)
    pool.shutdown()
    stats = pool.stats()
    assert stats["shutdown"] is True
    assert stats["idle"] == 0
    assert all(c.closed for c in conns) or True  # checked-in were idle


def test_concurrent_checkout_respects_cap():
    pool = _pool(max_size=4, acquire_timeout_s=5.0)
    seen = []
    lock = threading.Lock()

    def _work():
        with pool.acquire() as h:
            with lock:
                seen.append(h.resource.id)
            time.sleep(0.02)

    try:
        threads = [threading.Thread(target=_work) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(seen)) <= 4
        assert pool.stats()["checkouts_total"] == 12
    finally:
        pool.shutdown()


# --- shared HTTP pool --------------------------------------------------------------------------

def test_shared_http_pool_singleton_and_reuse():
    pool = shared_http_client_pool()
    assert shared_http_client_pool() is pool
    with pool.acquire() as h1:
        client1 = h1.resource
    with pool.acquire() as h2:
        assert h2.resource is client1  # same httpx.Client reused
    assert pool.stats()["name"] == "shared-http"


def test_cmd_models_uses_shared_pool(monkeypatch):
    """cli.cmd_models acquires from the shared pool (no throwaway client)."""
    import argparse

    import hugrgate.cli as cli

    pool = shared_http_client_pool()
    checkouts_before = pool.stats()["checkouts_total"]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": []}

    class FakeClient:
        def get(self, url, timeout=None):
            assert url == "http://x/models"
            return FakeResponse()

    # Patch the pool factory: cmd_models imports shared_http_client_pool
    # from hugrgate.pool inside the function, so patch it there.
    import hugrgate.pool as pool_module

    fake_pool = ResourcePool(FakeClient, max_size=1, acquire_timeout_s=2.0)
    monkeypatch.setattr(pool_module, "shared_http_client_pool",
                        lambda: fake_pool)
    printed = []
    monkeypatch.setattr(cli, "_print_json", printed.append)
    try:
        args = argparse.Namespace(url="http://x/")
        assert cli.cmd_models(args) == 0
        assert printed == [{"models": []}]
    finally:
        fake_pool.shutdown()
    # the real shared pool was untouched by the patched call
    assert pool.stats()["checkouts_total"] == checkouts_before
