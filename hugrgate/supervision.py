"""Worker supervision — heartbeats, restarts, escalation. Slice 295.

Long-running gate workers (schedulers, reapers, pool maintainers) must
not die silently.  :class:`Supervisor` keeps a set of named worker
threads alive:

- Each worker runs ``target(ctx)`` where ``ctx`` is a
  :class:`WorkerContext` offering ``heartbeat()`` and ``should_stop``.
- A watchdog thread checks every ``check_interval_s``: a worker whose
  last heartbeat is older than ``heartbeat_timeout_s`` — or whose
  thread died (exception or silent return) — is restarted via its
  factory ``target``.
- Restart budget: ``max_restarts`` restarts per ``restart_window_s``.
  Exhausting the budget *escalates*: the ``on_escalation`` callback
  fires with an escalation payload carrying ``restart_times``
  (the supervisor's restart-timestamp history) and ``last_error``
  (the last failure's traceback), and the worker is marked
  failed — no more silent restarts.
- :meth:`Supervisor.stop` halts the watchdog and joins workers.

Worker *failures* are handled by restart/escalation, never by
exceptions; :class:`SupervisionError` is reserved for supervisor
misuse (unknown worker, double start, operating while stopped).
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SupervisionError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "Supervisor",
    "WorkerContext",
    "WorkerRecord",
]


class WorkerContext:
    """Handle handed to a supervised worker's target function."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_heartbeat = time.monotonic()

    @property
    def name(self) -> str:
        return self._name

    def heartbeat(self) -> None:
        """Record liveness. Call at least every ``heartbeat_timeout_s``."""
        with self._lock:
            self._last_heartbeat = time.monotonic()

    @property
    def should_stop(self) -> bool:
        return self._stop.is_set()

    def last_heartbeat_age_s(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_heartbeat

    # -- supervisor-side ----------------------------------------------------------

    def _request_stop(self) -> None:
        self._stop.set()


@dataclass
class WorkerRecord:
    """Supervisor-side bookkeeping for one named worker."""
    name: str
    target: Callable[[WorkerContext], None]
    heartbeat_timeout_s: float
    max_restarts: int
    restart_window_s: float
    restarts: int = 0
    restart_times: list[float] = field(default_factory=list)
    failures: int = 0
    escalated: bool = False
    last_error: str | None = None
    thread: threading.Thread | None = None
    ctx: WorkerContext | None = None


class Supervisor:
    """Keep named worker threads alive (slice 295).

    Parameters
    ----------
    check_interval_s: watchdog period.
    on_escalation: ``(name, reason, payload) -> None`` called when a
        worker exhausts its restart budget.  ``payload`` is a dict with
        the worker ``name``, the ``reason``, ``restart_times`` (list of
        restart timestamps in :func:`time.monotonic` seconds, pruned to
        the restart window), ``restarts`` (restart count), and
        ``last_error`` (the last failure's traceback, or None).
    """

    def __init__(self, *, check_interval_s: float = 1.0,
                 on_escalation: Callable[[str, str, dict[str, Any]], None]
                 | None = None) -> None:
        if check_interval_s <= 0:
            raise SupervisionError(
                f"check_interval_s must be > 0, got {check_interval_s!r}")
        self._check_interval_s = check_interval_s
        self._on_escalation = on_escalation
        self._lock = threading.Lock()
        self._workers: dict[str, WorkerRecord] = {}
        self._watchdog: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False

    # -- registration ---------------------------------------------------------------

    def add_worker(self, name: str,
                   target: Callable[[WorkerContext], None], *,
                   heartbeat_timeout_s: float = 5.0,
                   max_restarts: int = 3,
                   restart_window_s: float = 60.0) -> None:
        """Register a worker. Starts it if the supervisor is running."""
        if not name:
            raise SupervisionError("worker name must be non-empty")
        if not callable(target):
            raise SupervisionError(
                f"target must be callable, got {type(target).__name__}")
        if heartbeat_timeout_s <= 0:
            raise SupervisionError(
                f"heartbeat_timeout_s must be > 0, got "
                f"{heartbeat_timeout_s!r}")
        if max_restarts < 0:
            raise SupervisionError(
                f"max_restarts must be >= 0, got {max_restarts!r}")
        with self._lock:
            if name in self._workers:
                raise SupervisionError(
                    f"worker {name!r} already registered")
            record = WorkerRecord(
                name=name, target=target,
                heartbeat_timeout_s=heartbeat_timeout_s,
                max_restarts=max_restarts,
                restart_window_s=restart_window_s)
            self._workers[name] = record
            running = self._running
        if running:
            self._start_worker(record)

    def remove_worker(self, name: str) -> None:
        """Stop and deregister a worker."""
        with self._lock:
            record = self._workers.pop(name, None)
        if record is None:
            raise SupervisionError(f"unknown worker {name!r}")
        self._stop_worker(record)

    # -- lifecycle ----------------------------------------------------------------------

    def start(self) -> None:
        """Start the watchdog and all registered workers."""
        with self._lock:
            if self._running:
                raise SupervisionError("supervisor already started")
            self._running = True
            self._stop.clear()
            records = list(self._workers.values())
        for record in records:
            self._start_worker(record)
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, name="supervisor-watchdog",
            daemon=True)
        self._watchdog.start()
        logger.info("supervisor started (%d workers)", len(records))

    def stop(self) -> None:
        """Stop the watchdog and join all workers."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop.set()
            records = list(self._workers.values())
            watchdog = self._watchdog
            self._watchdog = None
        for record in records:
            self._stop_worker(record)
        if watchdog is not None and watchdog is not threading.current_thread():
            watchdog.join(timeout=5.0)
        logger.info("supervisor stopped")

    # -- worker management ------------------------------------------------------------------

    def _start_worker(self, record: WorkerRecord) -> None:
        ctx = WorkerContext(record.name)
        record.ctx = ctx
        ctx.heartbeat()  # birth counts as liveness
        thread = threading.Thread(
            target=self._run_guarded, args=(record, ctx),
            name=f"supervised-{record.name}", daemon=True)
        record.thread = thread
        thread.start()

    def _stop_worker(self, record: WorkerRecord) -> None:
        ctx, thread = record.ctx, record.thread
        record.ctx, record.thread = None, None
        if ctx is not None:
            ctx._request_stop()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)

    def _run_guarded(self, record: WorkerRecord, ctx: WorkerContext) -> None:
        try:
            record.target(ctx)
        except Exception:  # noqa: BLE001 - a worker's exception IS the signal
            record.last_error = traceback.format_exc(limit=3)
            logger.warning("supervised worker %s raised:\n%s",
                           record.name, record.last_error)
        # Falling off the end (or raising) without a stop request is a
        # failure the watchdog will notice via the dead thread.

    # -- watchdog -----------------------------------------------------------------------------

    def _watchdog_loop(self) -> None:
        while not self._stop.wait(timeout=self._check_interval_s):
            with self._lock:
                records = list(self._workers.values())
            for record in records:
                self._check_worker(record)

    def _check_worker(self, record: WorkerRecord) -> None:
        with self._lock:
            if not self._running or record.escalated:
                return
            thread, ctx = record.thread, record.ctx
        if thread is None or ctx is None:
            return
        dead = not thread.is_alive()
        stale = ctx.last_heartbeat_age_s() > record.heartbeat_timeout_s
        if not dead and not stale:
            return
        reason = "thread died" if dead else "heartbeat stale"
        if record.last_error and dead:
            reason += f": {record.last_error.splitlines()[-1]}"
        logger.warning("supervisor: worker %s unhealthy (%s)", record.name,
                       reason)
        self._restart_or_escalate(record, reason)

    def _restart_or_escalate(self, record: WorkerRecord, reason: str) -> None:
        now = time.monotonic()
        with self._lock:
            # Prune restarts outside the window.
            record.restart_times = [
                t for t in record.restart_times
                if now - t <= record.restart_window_s]
            escalate = len(record.restart_times) >= record.max_restarts
            if not escalate:
                record.restart_times.append(now)
                record.restarts += 1
                record.last_error = None
        self._stop_worker(record)
        if escalate:
            logger.error("supervisor: worker %s escalated (%s)",
                         record.name, reason)
            # Enriched escalation payload: restart history plus the last
            # failure, not just the worker name. Built after the worker
            # is stopped so the snapshot is final.
            payload = {
                "name": record.name,
                "reason": reason,
                "restart_times": list(record.restart_times),
                "restarts": record.restarts,
                "last_error": record.last_error,
            }
            if self._on_escalation is not None:
                try:
                    self._on_escalation(record.name, reason, payload)
                except Exception:
                    logger.exception("on_escalation handler raised")
            # Publish the flag only after the handler ran: `escalated`
            # in stats() implies the notification was delivered.
            with self._lock:
                record.escalated = True
                record.failures += 1
            return
        logger.info("supervisor: restarting worker %s (%s)", record.name,
                    reason)
        self._start_worker(record)

    # -- observability ----------------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Supervisor statistics snapshot."""
        with self._lock:
            return {
                "running": self._running,
                "workers": {
                    name: {
                        "alive": r.thread.is_alive()
                        if r.thread else False,
                        "restarts": r.restarts,
                        "failures": r.failures,
                        "escalated": r.escalated,
                        "last_error": r.last_error,
                        "heartbeat_age_s": r.ctx.last_heartbeat_age_s()
                        if r.ctx else None,
                    }
                    for name, r in self._workers.items()
                },
            }
