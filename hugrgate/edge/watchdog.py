"""Edge watchdog — heartbeat supervision for the edge runtime. Slice 194.

:class:`EdgeWatchdog` watches one supervised loop (inference, telemetry,
bootstrap): the loop calls :meth:`heartbeat` each iteration, and
:meth:`check` verifies the deadline. On a miss the configured
:class:`MissPolicy` fires — ``LOG`` records, ``RESTART`` invokes the
restart callback, or a custom callable decides. An optional background
thread performs the checks on an interval; every decision is also
available synchronously via :meth:`check` so tests (and tight loops)
stay deterministic with an injected clock.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from hugrgate.errors import WatchdogError

__all__ = [
    "EdgeWatchdog",
    "MissPolicy",
    "WatchdogError",
]


class MissPolicy(str, Enum):
    """What happens when a heartbeat deadline is missed."""

    LOG = "log"          # record the miss, keep watching
    RESTART = "restart"  # invoke the restart callback, then keep watching


class EdgeWatchdog:
    """Heartbeat supervision with pluggable miss policy."""

    def __init__(self, timeout_s: float, *,
                 clock: Callable[[], float] | None = None,
                 policy: MissPolicy = MissPolicy.LOG,
                 on_miss: Callable[[int], None] | None = None,
                 on_restart: Callable[[], None] | None = None,
                 max_misses: int | None = None,
                 check_interval_s: float = 1.0):
        if timeout_s <= 0:
            raise WatchdogError("timeout_s must be > 0")
        if check_interval_s <= 0:
            raise WatchdogError("check_interval_s must be > 0")
        if max_misses is not None and max_misses < 1:
            raise WatchdogError("max_misses must be >= 1 when set")
        self._timeout = float(timeout_s)
        self._clock = clock or time.monotonic
        self._policy = policy
        self._on_miss = on_miss
        self._on_restart = on_restart
        self._max_misses = max_misses
        self._interval = float(check_interval_s)
        self._lock = threading.RLock()
        self._deadline = self._clock() + self._timeout
        self._misses = 0
        self._restarts = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._exhausted = False

    # -- supervised-loop API ----------------------------------------------------

    def heartbeat(self) -> None:
        """Reset the deadline to now + timeout."""
        with self._lock:
            self._deadline = self._clock() + self._timeout

    def check(self) -> str:
        """Evaluate the deadline once. Returns ``"ok"`` or ``"missed"``.

        A miss increments the counter and fires the policy. When
        ``max_misses`` is reached the watchdog latches ``exhausted``
        and stops firing the policy (a flapping restart loop is worse
        than a recorded death).
        """
        with self._lock:
            if self._clock() < self._deadline:
                return "ok"
            self._misses += 1
            misses = self._misses
            if self._exhausted:
                return "missed"
            if self._max_misses is not None and misses >= self._max_misses:
                self._exhausted = True
        # Policy callbacks run outside the lock: they may call back in.
        if self._on_miss is not None:
            self._on_miss(misses)
        if self._policy is MissPolicy.RESTART and self._on_restart is not None:
            with self._lock:
                self._restarts += 1
            self._on_restart()
        # A restart is a fresh start: the restarted loop is expected to
        # heartbeat promptly; re-arm the deadline from the restart.
        if self._policy is MissPolicy.RESTART:
            with self._lock:
                self._deadline = self._clock() + self._timeout
        return "missed"

    # -- background supervision ----------------------------------------------------

    def start(self) -> None:
        """Begin background checking. Idempotent."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._supervise, name="edge-watchdog", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop background checking. Idempotent."""
        with self._lock:
            thread = self._thread
            self._thread = None
        self._stop.set()
        if thread is not None:
            thread.join(timeout=self._interval * 2 + 1.0)

    def _supervise(self) -> None:
        while not self._stop.wait(self._interval):
            self.check()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    # -- introspection -------------------------------------------------------------------

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    @property
    def restarts(self) -> int:
        with self._lock:
            return self._restarts

    @property
    def exhausted(self) -> bool:
        with self._lock:
            return self._exhausted

    def status(self) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            return {
                "timeout_s": self._timeout,
                "policy": self._policy.value,
                "misses": self._misses,
                "restarts": self._restarts,
                "exhausted": self._exhausted,
                "seconds_to_deadline": self._deadline - now,
                "running": self.running,
            }
