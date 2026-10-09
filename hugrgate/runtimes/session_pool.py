"""Model-session pooling — warm loaded runtimes, keyed by model. Slice 291.

Loading a model (mmap weights, build the context, warm kernels) is the
most expensive operation in the local-model fabric; doing it per
decision is the throughput killer.  This module pools *loaded*
sessions:

- :class:`ModelSessionPool` keeps one :class:`ResourcePool
  <hugrgate.pool.ResourcePool>` per :class:`ModelRef` (slice 290,
  reused — not duplicated).  The per-model factory builds a runtime
  via the caller's ``runtime_factory`` and calls ``load(model)`` once;
  every later :meth:`acquire` for the same model reuses the warm
  session.
- Cross-model eviction is LRU: when ``max_models`` distinct models are
  pooled and a new one arrives, the least-recently-used model's pool is
  shut down (its sessions unloaded via ``close()``).
- Health: checkout runs ``runtime.health()``; a non-``"ok"`` status
  discards the session and builds a fresh one.
- Thread-safe; handles are :class:`PooledHandle
  <hugrgate.pool.PooledHandle>` — ``handle.resource`` is the loaded
  :class:`LocalRuntime`, ``handle.discard()`` drops a session that
  proved sick mid-use.

Contract for pooled runtimes: ``close()`` must release model resources
(unload the model); the pool calls ``close()`` — never ``unload()``
directly — on eviction.  Exhaustion raises :class:`PoolError`
(``code="pool_error"``, recoverable), the slice-290 taxonomy error.

Relationship to :mod:`hugrgate.runtimes.eviction`: that module decides
which *resident models* leave under VRAM pressure (the residency
layer); this module pools *loaded sessions* above it (the session
layer).  They compose: a session pool miss may trigger a residency
load, and residency eviction should discard the model's pooled
sessions — wire that via :meth:`drop_model`.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from hugrgate.errors import PoolError
from hugrgate.log import get_logger
from hugrgate.pool import PooledHandle, ResourcePool
from hugrgate.runtimes import LocalRuntime, ModelRef

logger = get_logger(__name__)

__all__ = [
    "ModelSessionPool",
]


def _model_key(model: ModelRef) -> ModelRef:
    if not isinstance(model, ModelRef):
        raise PoolError(
            f"model must be a ModelRef, got {type(model).__name__}")
    return model


def _session_health(runtime: Any) -> bool:
    """Checkout health check: the runtime must report status ok."""
    try:
        return runtime.health().get("status") == "ok"
    except Exception as e:  # noqa: BLE001 - health must never raise
        logger.warning("session health check raised: %s", e)
        return False


class ModelSessionPool:
    """Pool of warm, model-loaded runtime sessions (slice 291).

    Parameters
    ----------
    max_sessions_per_model: cap on concurrent sessions of one model.
    max_models: cap on distinct pooled models (LRU eviction past it).
    idle_timeout_s: per-model-pool idle eviction (see
        :class:`ResourcePool`).
    acquire_timeout_s: how long :meth:`acquire` waits for a session.
    """

    def __init__(self, *, max_sessions_per_model: int = 2,
                 max_models: int = 8, idle_timeout_s: float = 300.0,
                 acquire_timeout_s: float = 30.0) -> None:
        if not isinstance(max_sessions_per_model, int) or \
                max_sessions_per_model < 1:
            raise PoolError(
                f"max_sessions_per_model must be a positive int, got "
                f"{max_sessions_per_model!r}")
        if not isinstance(max_models, int) or max_models < 1:
            raise PoolError(
                f"max_models must be a positive int, got {max_models!r}")
        if not isinstance(idle_timeout_s, (int, float)) or \
                idle_timeout_s <= 0:
            raise PoolError(
                f"idle_timeout_s must be > 0, got {idle_timeout_s!r}")
        if not isinstance(acquire_timeout_s, (int, float)) or \
                acquire_timeout_s <= 0:
            raise PoolError(
                f"acquire_timeout_s must be > 0, got {acquire_timeout_s!r}")
        self._max_per_model = max_sessions_per_model
        self._max_models = max_models
        self._idle_timeout_s = float(idle_timeout_s)
        self._acquire_timeout_s = float(acquire_timeout_s)
        self._lock = threading.RLock()
        # ModelRef -> ResourcePool, MRU last (LRU eviction from the front).
        self._pools: OrderedDict[ModelRef, ResourcePool] = OrderedDict()
        self._shutdown = False

    # -- acquisition ----------------------------------------------------------

    def acquire(self, model: ModelRef,
                runtime_factory: Callable[[], LocalRuntime]) -> PooledHandle:
        """Check out a session with ``model`` loaded.

        ``runtime_factory`` builds an *unloaded* runtime; the pool loads
        the model exactly once per session.  The handle's ``resource``
        is the :class:`LocalRuntime`.
        """
        key = _model_key(model)
        if not callable(runtime_factory):
            raise PoolError(
                f"runtime_factory must be callable, got "
                f"{type(runtime_factory).__name__}")
        pool = self._pool_for(key, model, runtime_factory)
        return pool.acquire(timeout=self._acquire_timeout_s)

    def _pool_for(self, key: ModelRef, model: ModelRef,
                  runtime_factory: Callable[[], LocalRuntime]
                  ) -> ResourcePool:
        with self._lock:
            if self._shutdown:
                raise PoolError("session pool is shut down")
            pool = self._pools.get(key)
            if pool is not None:
                self._pools.move_to_end(key)
                return pool
            while len(self._pools) >= self._max_models:
                evicted_key, evicted = self._pools.popitem(last=False)
                logger.info("session pool evicting model %s (LRU)",
                            evicted_key.display)
                evicted.shutdown()
            pool = ResourcePool(
                self._session_factory(model, runtime_factory),
                min_size=0, max_size=self._max_per_model,
                idle_timeout_s=self._idle_timeout_s,
                max_lifetime_s=86400.0,
                acquire_timeout_s=self._acquire_timeout_s,
                health_check=_session_health,
                name=f"sessions-{key.runtime}-{key.path[:24]}")
            self._pools[key] = pool
            return pool

    @staticmethod
    def _session_factory(model: ModelRef,
                         runtime_factory: Callable[[], LocalRuntime]
                         ) -> Callable[[], LocalRuntime]:
        def _build() -> LocalRuntime:
            runtime = runtime_factory()
            if not isinstance(runtime, LocalRuntime):
                raise PoolError(
                    f"runtime_factory must build a LocalRuntime, got "
                    f"{type(runtime).__name__}")
            runtime.load(model)  # the expensive step, done once per session
            return runtime
        return _build

    # -- management ---------------------------------------------------------------

    def drop_model(self, model: ModelRef) -> bool:
        """Discard every session of ``model`` (residency evicted it).

        Returns True when the model was pooled.  This is the seam where
        :mod:`hugrgate.runtimes.eviction` hooks in: evicting a resident
        model must also drop its pooled sessions, or decisions would
        run against a model the residency layer believes is gone.
        """
        key = _model_key(model)
        with self._lock:
            pool = self._pools.pop(key, None)
        if pool is None:
            return False
        pool.shutdown()
        logger.info("session pool dropped model %s", key.display)
        return True

    def models(self) -> list[ModelRef]:
        """Currently pooled models, MRU last."""
        with self._lock:
            return list(self._pools.keys())

    def shutdown(self) -> None:
        """Shut down every per-model pool."""
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            pools = list(self._pools.values())
            self._pools.clear()
        for pool in pools:
            pool.shutdown()

    def stats(self) -> dict[str, Any]:
        """Pool statistics snapshot."""
        with self._lock:
            per_model = {key.display: pool.stats()
                         for key, pool in self._pools.items()}
            return {
                "models": len(self._pools),
                "max_models": self._max_models,
                "max_sessions_per_model": self._max_per_model,
                "total_live": sum(s["live"] for s in per_model.values()),
                "total_checkouts": sum(s["checkouts_total"]
                                       for s in per_model.values()),
                "per_model": per_model,
                "shutdown": self._shutdown,
            }
