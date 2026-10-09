"""HugrGate service daemon — long-running process mode. Slice 42.

Beyond the plain HTTP app (:mod:`hugrgate.server`), the daemon adds:

- **Unix-socket + localhost HTTP** listeners served from one process.
- **Model warm pool**: every registered backend's ``warmup()`` runs at
  startup so the first real decision is already fast.
- **Request batching**: ``POST /decide`` calls are coalesced over a short
  window and executed concurrently (:class:`BatchingQueue`).
- **Per-client policies**: an ``X-Client-Id`` header selects a server-side
  :class:`DecisionPolicy` from a JSON policy file, overriding the policy
  (if any) in the request body.
- **Back-pressure**: a bounded queue; overload returns HTTP 429 instead of
  unbounded memory growth.
- **Graceful shutdown**: SIGINT/SIGINT drains the queue before exiting.

Entry point: ``hugrgate-server`` (see ``pyproject.toml``).
"""

from __future__ import annotations

import asyncio
import json
import signal
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, QueueFull
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.serde import policy_from_dict
from hugrgate.server import build_gate, create_app

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "BatchingQueue",
    "Daemon",
    "DaemonConfig",
    "QueueFull",
    "create_daemon_app",
    "load_client_policies",
    "main",
    "serve_forever",
]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8377


@dataclass
class DaemonConfig:
    """Operator configuration for the daemon."""
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    unix_socket: str | None = None
    batch_window_ms: float = 5.0
    max_batch: int = 32
    max_queue: int = 1024
    client_policies_path: str | None = None
    client_id_header: str = "x-client-id"
    drain_timeout_s: float = 10.0

    def __post_init__(self):
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError(f"port must be an int in 1..65535, "
                             f"got {self.port!r}")
        if self.batch_window_ms <= 0:
            raise ValueError("batch_window_ms must be > 0")
        if self.max_batch < 1:
            raise ValueError("max_batch must be >= 1")
        if self.max_queue < 1:
            raise ValueError("max_queue must be >= 1")
        if self.drain_timeout_s < 0:
            raise ValueError("drain_timeout_s must be >= 0")
        if not self.client_id_header or not self.client_id_header.strip():
            raise ValueError("client_id_header must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        """Plain dict round-trip for operator config files."""
        return {
            "host": self.host,
            "port": self.port,
            "unix_socket": self.unix_socket,
            "batch_window_ms": self.batch_window_ms,
            "max_batch": self.max_batch,
            "max_queue": self.max_queue,
            "client_policies_path": self.client_policies_path,
            "client_id_header": self.client_id_header,
            "drain_timeout_s": self.drain_timeout_s,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DaemonConfig:
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(
                f"unknown daemon config key(s): {sorted(unknown)}; "
                f"expected keys: {sorted(known)}")
        return cls(**{k: d[k] for k in d})


@dataclass
class _QueuedDecision:
    state: dict[str, Any]
    spec_dict: dict[str, Any]
    policy_dict: dict[str, Any] | None
    backend_name: str | None
    context: dict[str, Any] | None
    future: asyncio.Future[DecisionResult]
    enqueued_at: float = field(default_factory=time.perf_counter)


class BatchingQueue:
    """Windowed request coalescing in front of a :class:`HugrGate`.

    Submitters await their own future; a background worker drains the
    queue in batches (up to ``max_batch`` items or ``window`` expiry,
    whichever comes first) and executes each decision in a worker thread
    so the event loop never blocks on backend inference.
    """

    def __init__(self, gate: HugrGate, window_ms: float = 5.0,
                 max_batch: int = 32, max_queue: int = 1024) -> None:
        self.gate = gate
        self.window_s = window_ms / 1000.0
        self.max_batch = max_batch
        self.max_queue = max_queue
        self._queue: asyncio.Queue[_QueuedDecision] = asyncio.Queue(
            maxsize=max_queue)
        self._task: asyncio.Task | None = None
        self._accepting = True
        self._batches = 0
        self._decisions = 0
        self._max_batch_seen = 0
        self._in_flight = 0  # batches pulled from the queue, not yet done

    async def start(self) -> None:
        self._task = asyncio.create_task(self._worker())

    async def __aenter__(self) -> BatchingQueue:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()
        return None

    async def stop(self, drain_timeout: float = 10.0) -> None:
        """Stop accepting; drain what is queued, then halt the worker.

        On a drain timeout the queued futures fail fast with
        ``QueueFull`` instead of hanging forever.
        """
        self._accepting = False
        if self._task is None:
            return
        try:
            await asyncio.wait_for(self._drain(), timeout=drain_timeout)
        except asyncio.TimeoutError:
            self._fail_pending("daemon stopped before the queue drained")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    def _fail_pending(self, reason: str) -> None:
        """Fail every still-queued future with QueueFull (no hangs)."""
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if not item.future.done():
                item.future.set_exception(QueueFull(reason))

    async def _drain(self) -> None:
        # Wait until the queue is empty AND every pulled batch has
        # resolved its submitters' futures. Without the in-flight
        # check, stop() could cancel the worker mid-batch and leave
        # submitters hanging on never-resolved futures (slice 018).
        while not (self._queue.empty() and self._in_flight == 0):
            await asyncio.sleep(0.01)

    async def submit(self, state: Mapping[str, Any],
                     spec_dict: dict[str, Any],
                     policy_dict: dict[str, Any] | None,
                     backend_name: str | None,
                     context: Mapping[str, Any] | None) -> DecisionResult:
        if not self._accepting:
            raise QueueFull("daemon is shutting down")
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        item = _QueuedDecision(dict(state), spec_dict, policy_dict,
                               backend_name,
                               dict(context) if context else None, future)
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            raise QueueFull(
                f"decision queue full ({self.max_queue}); try again later"
            ) from None
        return await future

    async def _worker(self) -> None:
        while True:
            try:
                first = await self._queue.get()
            except asyncio.CancelledError:
                break
            # Counted in-flight from the moment an item leaves the
            # queue, so _drain() cannot observe "empty and idle"
            # while a batch is being assembled (slice 018).
            self._in_flight += 1
            try:
                batch = [first]
                deadline = time.perf_counter() + self.window_s
                while len(batch) < self.max_batch:
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(
                            self._queue.get(), timeout=remaining))
                    except asyncio.TimeoutError:
                        break
                await self._execute_batch(batch)
            finally:
                self._in_flight -= 1

    async def _execute_batch(self, batch: list[_QueuedDecision]) -> None:
        await self._run_batch(batch)

    async def _run_batch(self, batch: list[_QueuedDecision]) -> None:
        from hugrgate.spec import DecisionSpec

        async def _one(item: _QueuedDecision) -> None:
            try:
                spec = DecisionSpec.from_dict(item.spec_dict)
                policy = (policy_from_dict(item.policy_dict)
                          if item.policy_dict else None)
                result = await asyncio.to_thread(
                    self.gate.decide, item.state, spec, policy,
                    item.context, item.backend_name)
                if not item.future.done():
                    item.future.set_result(result)
            except asyncio.CancelledError:
                # Worker cancelled mid-batch (drain timeout): fail the
                # submitter instead of leaving the future hanging.
                if not item.future.done():
                    item.future.set_exception(
                        QueueFull("daemon is shutting down"))
                raise
            except Exception as e:  # noqa: BLE001 - fan out to submitter
                if not item.future.done():
                    item.future.set_exception(e)

        await asyncio.gather(*(_one(item) for item in batch))
        self._batches += 1
        self._decisions += len(batch)
        self._max_batch_seen = max(self._max_batch_seen, len(batch))

    def stats(self) -> dict[str, Any]:
        return {"batches": self._batches,
                "decisions": self._decisions,
                "max_batch_seen": self._max_batch_seen,
                "avg_batch_size": (self._decisions / self._batches
                                   if self._batches else 0.0),
                "queued": self._queue.qsize()}


def load_client_policies(path: str) -> dict[str, DecisionPolicy]:
    """Load per-client policies from a JSON file.

    Format: ``{"client-id": {<policy dict>}, ...}`` where each policy dict
    matches :func:`hugrgate.client.policy_to_dict` output.
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("client policies file must be a JSON object")
    return {cid: policy_from_dict(p) for cid, p in raw.items()}


def create_daemon_app(config: DaemonConfig,
                      gate: HugrGate | None = None):
    """Build the daemon FastAPI app: batching + per-client policies."""
    from hugrgate.errors import (
        BackendError,
        BackendUnavailable,
        HugrGateError,
        PolicyError,
        SpecError,
    )
    from hugrgate.server import _error_response

    gate = gate or build_gate()
    client_policies: dict[str, DecisionPolicy] = {}
    if config.client_policies_path:
        client_policies = load_client_policies(config.client_policies_path)

    queue = BatchingQueue(gate, window_ms=config.batch_window_ms,
                          max_batch=config.max_batch,
                          max_queue=config.max_queue)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(app):
        # Model warm pool: pay load cost once, up front.
        for name in gate.registry.list():
            backend = gate.registry.get(name)
            if backend is None:  # defensive: list/get disagree
                continue
            backend.warmup()
        await queue.start()
        try:
            yield
        finally:
            await queue.stop(drain_timeout=config.drain_timeout_s)

    app = create_app(gate)
    app.router.lifespan_context = _lifespan

    # Replace the direct /decide route with the batching variant.
    app.routes[:] = [
        r for r in app.routes
        if not (getattr(r, "path", "") == "/decide"
                and "POST" in getattr(r, "methods", set()))
    ]

    @app.post("/decide")
    async def decide_batched(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - any parse failure is bad_request
            return JSONResponse(status_code=400, content={
                "error": {"code": "bad_request",
                          "message": "request body must be JSON",
                          "recoverable": True, "details": {}}})
        if not isinstance(body.get("spec"), dict) or not isinstance(
                body.get("state"), dict):
            return JSONResponse(status_code=400, content={
                "error": {"code": "bad_request",
                          "message": "request needs 'spec' and 'state' objects",
                          "recoverable": True, "details": {}}})
        # Per-client policy: server-side policy wins over the body policy.
        client_id = request.headers.get(config.client_id_header)
        policy_dict = body.get("policy")
        if client_id and client_id in client_policies:
            from hugrgate.client import policy_to_dict
            policy_dict = policy_to_dict(client_policies[client_id])
        try:
            result = await queue.submit(
                body["state"], body["spec"], policy_dict,
                body.get("backend_name"), body.get("context"))
        except QueueFull as e:
            return JSONResponse(status_code=429, content={
                "error": {"code": "queue_full", "message": str(e),
                          "recoverable": True, "details": {}}})
        except Abstention as e:
            return JSONResponse(status_code=200, content={
                "decision": None, "abstained": True, "reason": e.reason,
                "message": e.message, "code": e.code})
        except BackendUnavailable as e:
            return _error_response(e, 503)
        except BackendError as e:
            return _error_response(e, 502)
        except (SpecError, PolicyError) as e:
            return _error_response(e, 400)
        except HugrGateError as e:
            return _error_response(e, 500)
        return JSONResponse(status_code=200, content=result.to_dict())

    @app.get("/daemon")
    def daemon_info() -> dict[str, Any]:
        return {"batching": queue.stats(),
                "client_policies": sorted(client_policies),
                "warm_pool": gate.registry.list()}

    app.state.batching_queue = queue
    app.state.daemon_config = config
    return app


class Daemon:
    """Owns the daemon's listener threads and lifecycle."""

    def __init__(self, config: DaemonConfig | None = None,
                 gate: HugrGate | None = None) -> None:
        self.config = config or DaemonConfig()
        self.gate = gate or build_gate()
        self.app = create_daemon_app(self.config, self.gate)
        self._servers: list[tuple[Any, threading.Thread]] = []
        self._stopped = threading.Event()

    def start(self) -> None:
        """Start HTTP (and Unix-socket, if configured) listeners."""
        import uvicorn
        logger.info("daemon starting: http=%s:%d unix_socket=%s",
                    self.config.host, self.config.port,
                    self.config.unix_socket)
        http = uvicorn.Server(uvicorn.Config(
            self.app, host=self.config.host, port=self.config.port,
            log_level="warning"))
        self._launch(http)
        if self.config.unix_socket:
            uds = uvicorn.Server(uvicorn.Config(
                self.app, uds=self.config.unix_socket, log_level="warning"))
            self._launch(uds)

    def _launch(self, server: Any) -> None:
        thread = threading.Thread(target=server.run, daemon=True,
                                  name=f"hugrgate-{len(self._servers)}")
        self._servers.append((server, thread))
        thread.start()

    def stop(self, timeout: float = 15.0) -> None:
        """Graceful shutdown: stop listeners, drain the batch queue."""
        if self._stopped.is_set():
            return
        logger.info("daemon stopping: draining batch queue")
        self._stopped.set()
        for server, _ in self._servers:
            server.should_exit = True
        for _, thread in self._servers:
            thread.join(timeout=timeout / max(len(self._servers), 1))
        logger.info("daemon stopped")

    def join(self) -> None:
        for _, thread in self._servers:
            thread.join()


def serve_forever(config: DaemonConfig | None = None) -> None:
    """Run the daemon until SIGINT/SIGTERM, then shut down gracefully."""
    daemon = Daemon(config or DaemonConfig())
    daemon.start()

    def _handle_signal(signum: int, _frame: Any) -> None:
        daemon.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (OSError, ValueError):
            pass  # not in main thread — best effort
    daemon.join()


def main(argv: list[str] | None = None) -> int:
    """``hugrgate-server`` entry point."""
    import argparse
    parser = argparse.ArgumentParser(
        prog="hugrgate-server",
        description="HugrGate service daemon (HTTP + Unix socket, "
                    "batching, per-client policies).")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="bind host (default: 127.0.0.1, localhost-only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--unix-socket", default=None,
                        help="also serve on this Unix socket path")
    parser.add_argument("--batch-window-ms", type=float, default=5.0)
    parser.add_argument("--max-batch", type=int, default=32)
    parser.add_argument("--max-queue", type=int, default=1024)
    parser.add_argument("--client-policies", default=None,
                        help="JSON file mapping client id -> policy")
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="hugrgate log level (default: WARNING)")
    parser.add_argument("--log-json", action="store_true",
                        help="emit logs as JSON objects")
    args = parser.parse_args(argv)
    from hugrgate.log import configure_logging
    configure_logging(args.log_level, json_format=args.log_json)
    config = DaemonConfig(
        host=args.host, port=args.port, unix_socket=args.unix_socket,
        batch_window_ms=args.batch_window_ms, max_batch=args.max_batch,
        max_queue=args.max_queue,
        client_policies_path=args.client_policies)
    serve_forever(config)
    return 0
