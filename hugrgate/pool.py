"""Connection pooling — generic resource pool + shared HTTP pool. Slice 290.

Expensive resources (TCP/TLS connections, model sessions, ...) must be
reused, not rebuilt per use.  This module provides:

- :class:`ResourcePool` — a generic, thread-safe pool:
  ``factory`` builds resources; ``acquire()`` hands out a context
  manager; a background reaper evicts idle-expired and
  lifetime-expired resources while keeping ``min_size`` warm;
  checkout-time health checks discard sick resources; exhaustion waits
  up to ``acquire_timeout_s`` then raises :class:`PoolError`.
- :func:`shared_http_client_pool` — process-wide pool of
  ``httpx.Client`` instances.  ``hugrgate.cli.cmd_models`` used to
  build a throwaway client per invocation (new TCP+TLS handshake every
  time); it now acquires from the shared pool so the client's internal
  per-host connection pool survives across commands.

Resource contract: the factory's product needs no particular type —
``close()`` is called on eviction when present, and health is decided
by the optional ``health_check`` callable (default: always healthy).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from hugrgate.errors import PoolError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "PooledHandle",
    "ResourcePool",
    "shared_http_client_pool",
]


class PooledHandle:
    """Checked-out resource; returning it to the pool on context exit."""

    __slots__ = ("_pool", "_resource", "_returned")

    def __init__(self, pool: ResourcePool, resource: Any) -> None:
        self._pool = pool
        self._resource = resource
        self._returned = False

    @property
    def resource(self) -> Any:
        if self._returned:
            raise PoolError("pooled handle already returned to the pool")
        return self._resource

    def release(self) -> None:
        """Return the resource; idempotent."""
        if not self._returned:
            self._returned = True
            self._pool._checkin(self._resource)

    def discard(self) -> None:
        """Drop the resource instead of returning it (it proved sick)."""
        if not self._returned:
            self._returned = True
            self._pool._discard(self._resource)

    def __enter__(self) -> PooledHandle:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


class ResourcePool:
    """Generic pool of reusable resources (slice 290).

    Parameters
    ----------
    factory: zero-arg callable building a fresh resource.
    min_size: warm resources kept ready (built eagerly).
    max_size: hard cap on live resources (idle + checked out).
    idle_timeout_s: idle resources older than this are reaped (above
        ``min_size``).
    max_lifetime_s: resources older than this are retired on checkin
        (and reaped when idle).
    acquire_timeout_s: how long :meth:`acquire` waits for a free slot
        before raising :class:`PoolError`.
    health_check: optional ``(resource) -> bool``; unhealthy resources
        are discarded at checkout and a replacement is attempted.
    name: pool name for logs/stats.
    """

    def __init__(self, factory: Callable[[], Any], *,
                 min_size: int = 0, max_size: int = 8,
                 idle_timeout_s: float = 60.0,
                 max_lifetime_s: float = 3600.0,
                 acquire_timeout_s: float = 10.0,
                 health_check: Callable[[Any], bool] | None = None,
                 name: str = "pool") -> None:
        if not callable(factory):
            raise PoolError(
                f"pool factory must be callable, got {type(factory).__name__}")
        for label, value, minimum in (
                ("min_size", min_size, 0), ("max_size", max_size, 1)):
            if not isinstance(value, int) or value < minimum:
                raise PoolError(
                    f"{label} must be an int >= {minimum}, got {value!r}")
        if min_size > max_size:
            raise PoolError(
                f"min_size ({min_size}) must be <= max_size ({max_size})")
        for label, timeout_v in (("idle_timeout_s", idle_timeout_s),
                                 ("max_lifetime_s", max_lifetime_s),
                                 ("acquire_timeout_s", acquire_timeout_s)):
            if not isinstance(timeout_v, (int, float)) or timeout_v <= 0:
                raise PoolError(f"{label} must be > 0, got {timeout_v!r}")
        if health_check is not None and not callable(health_check):
            raise PoolError("health_check must be callable or None")
        self._factory = factory
        self._min_size = min_size
        self._max_size = max_size
        self._idle_timeout_s = float(idle_timeout_s)
        self._max_lifetime_s = float(max_lifetime_s)
        self._acquire_timeout_s = float(acquire_timeout_s)
        self._health_check = health_check
        self._name = name
        # idle entries: [resource, last_used_monotonic, born_monotonic]
        self._idle: deque[list] = deque()
        self._live = 0  # idle + checked out
        self._cond = threading.Condition()
        self._shutdown = False
        self._created = 0
        self._destroyed = 0
        self._checkouts = 0
        self._born: dict[int, float] = {}  # id(resource) -> build time
        self._reaper = threading.Thread(
            target=self._reap_loop, name=f"pool-reaper-{name}", daemon=True)
        for _ in range(min_size):
            resource = self._build()
            self._idle.append([resource, time.monotonic()])
        self._reaper.start()

    # -- construction / destruction --------------------------------------------

    def _build(self) -> Any:
        try:
            resource = self._factory()
        except Exception as e:
            raise PoolError(
                f"pool {self._name!r} factory failed: {e}") from e
        self._live += 1
        self._created += 1
        self._born[id(resource)] = time.monotonic()
        return resource

    def _close(self, resource: Any) -> None:
        close = getattr(resource, "close", None)
        if callable(close):
            try:
                close()
            except Exception as e:  # noqa: BLE001 - best effort
                logger.warning("pool %r resource close() failed: %s",
                               self._name, e)
        self._born.pop(id(resource), None)
        self._live -= 1
        self._destroyed += 1

    def _discard(self, resource: Any) -> None:
        with self._cond:
            self._close(resource)
            self._cond.notify_all()

    # -- checkout / checkin -------------------------------------------------------

    def acquire(self, timeout: float | None = None) -> PooledHandle:
        """Check out a resource; raises :class:`PoolError` on exhaustion.

        The returned handle is a context manager; exiting returns the
        resource.  ``timeout`` overrides ``acquire_timeout_s``.
        """
        deadline = time.monotonic() + (timeout if timeout is not None
                                       else self._acquire_timeout_s)
        with self._cond:
            while True:
                if self._shutdown:
                    raise PoolError(f"pool {self._name!r} is shut down")
                resource = self._take_idle()
                if resource is not None:
                    self._checkouts += 1
                    return PooledHandle(self, resource)
                if self._live < self._max_size:
                    resource = self._build()
                    self._checkouts += 1
                    return PooledHandle(self, resource)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolError(
                        f"pool {self._name!r} exhausted "
                        f"({self._max_size} live); try again later")
                self._cond.wait(timeout=remaining)

    def _take_idle(self) -> Any | None:
        """Pop the freshest healthy idle resource (lock held)."""
        while self._idle:
            resource, _last_used = self._idle.pop()
            born = self._born.get(id(resource), time.monotonic())
            if time.monotonic() - born > self._max_lifetime_s:
                self._close(resource)  # retired: too old to reissue
                continue
            if self._health_check is not None:
                try:
                    healthy = self._health_check(resource)
                except Exception as e:  # noqa: BLE001 - check must not kill
                    logger.warning("pool %r health check raised: %s",
                                   self._name, e)
                    healthy = False
                if not healthy:
                    self._close(resource)
                    continue
            return resource
        return None

    def _checkin(self, resource: Any) -> None:
        with self._cond:
            if self._shutdown:
                self._close(resource)
            else:
                self._idle.append([resource, time.monotonic()])
            self._cond.notify_all()

    # -- reaping -----------------------------------------------------------------------

    def _reap_loop(self) -> None:
        while True:
            with self._cond:
                if self._shutdown:
                    return
                now = time.monotonic()
                keep: deque[list] = deque()
                for resource, last_used in list(self._idle):
                    born = self._born.get(id(resource), now)
                    too_old = now - born > self._max_lifetime_s
                    idle_long = now - last_used > self._idle_timeout_s
                    # Always keep min_size warm (unless lifetime-retired).
                    if too_old or (idle_long and len(keep) >= self._min_size):
                        self._close(resource)
                    else:
                        keep.append([resource, last_used])
                self._idle = keep
                # Wait (wakeable) instead of sleeping: shutdown() notifies.
                self._cond.wait(timeout=min(self._idle_timeout_s / 2.0, 5.0))

    # -- lifecycle -----------------------------------------------------------------------

    def shutdown(self) -> None:
        """Close all idle resources; checked-out ones close on return."""
        with self._cond:
            self._shutdown = True
            while self._idle:
                self._close(self._idle.pop()[0])
            self._cond.notify_all()
        self._reaper.join(timeout=5.0)

    def stats(self) -> dict[str, Any]:
        """Pool statistics snapshot."""
        with self._cond:
            return {
                "name": self._name,
                "idle": len(self._idle),
                "live": self._live,
                "max_size": self._max_size,
                "created_total": self._created,
                "destroyed_total": self._destroyed,
                "checkouts_total": self._checkouts,
                "shutdown": self._shutdown,
            }


_shared_http_pool: ResourcePool | None = None
_shared_http_lock = threading.Lock()


def shared_http_client_pool() -> ResourcePool:
    """Process-wide pool of ``httpx.Client`` (slice 290).

    One client per checkout, reused across checkouts: the client's own
    per-host connection pool survives, so repeated CLI/SDK calls stop
    paying a fresh TCP+TLS handshake per command.  ``httpx`` is imported
    lazily — the pool module stays importable without it.
    """
    global _shared_http_pool
    with _shared_http_lock:
        if _shared_http_pool is None:
            import httpx  # lazy: pool.py has no hard httpx dependency

            def _factory():
                return httpx.Client(trust_env=False)

            def _healthy(client) -> bool:
                return not client.is_closed

            _shared_http_pool = ResourcePool(
                _factory, min_size=0, max_size=8, idle_timeout_s=120.0,
                max_lifetime_s=1800.0, acquire_timeout_s=10.0,
                health_check=_healthy, name="shared-http")
        return _shared_http_pool
