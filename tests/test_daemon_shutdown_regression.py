"""Regression tests for the daemon's graceful-shutdown path
(dawn-forge slice: daemon-shutdown-regression).

The behavior already exists in ``hugrgate/daemon.py`` (Solrun's rule),
so these are regression tests, not new behavior:

* ``serve_forever()`` installs a SIGINT/SIGTERM handler that calls
  ``Daemon.stop()``.
* ``Daemon.stop()`` sets ``should_exit`` on every listener and joins
  the listener threads (idempotent).
* The FastAPI lifespan's ``finally`` block drains the
  :class:`BatchingQueue` via ``queue.stop(drain_timeout=...)`` using
  ``config.drain_timeout_s``.
* A real daemon subprocess exits with code 0 when sent SIGTERM.

Every test exercises the REAL handler/drain code (no mocks of the
logic under test). Each test must FAIL if the drain logic or the
handler installation is stubbed out.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time

import pytest

import hugrgate.daemon as daemon_module
from hugrgate import DecisionSpec
from hugrgate.daemon import (
    BatchingQueue,
    Daemon,
    DaemonConfig,
    create_daemon_app,
    serve_forever,
)
from hugrgate.errors import QueueFull

SPEC_DICT = DecisionSpec(type="categorical", options=["a", "b"]).to_dict()


# --- serve_forever(): signal-handler installation ---------------------------


def test_serve_forever_installs_sigint_sigterm_handlers_that_stop_daemon(
        monkeypatch):
    """The REAL _handle_signal closure routes SIGINT/SIGTERM to
    daemon.stop(). Stubbing the closure body or the signal.signal loop
    leaves stop() uncalled and this test fails."""
    calls = {"start": 0, "stop": 0, "join": 0}

    class FakeDaemon:
        def __init__(self, config=None):
            self.config = config

        def start(self):
            calls["start"] += 1

        def stop(self):
            calls["stop"] += 1

        def join(self):
            calls["join"] += 1

    installed = {}

    def fake_signal(sig, handler):
        installed[sig] = handler
        return None

    monkeypatch.setattr(daemon_module, "Daemon", FakeDaemon)
    monkeypatch.setattr(signal, "signal", fake_signal)

    serve_forever(DaemonConfig(port=8123))

    assert calls["start"] == 1
    assert calls["join"] == 1
    assert set(installed) == {signal.SIGINT, signal.SIGTERM}

    installed[signal.SIGTERM](signal.SIGTERM, None)
    installed[signal.SIGINT](signal.SIGINT, None)
    assert calls["stop"] == 2


# --- Daemon.stop(): listeners halt, threads joined ---------------------------


def test_daemon_stop_signals_listeners_and_joins(gate_with_stub):
    """The REAL Daemon.stop() must set should_exit on every listener
    and join each listener thread with the split timeout. A stubbed
    stop() (e.g. just setting _stopped) leaves should_exit False and
    never joins, failing this test."""
    daemon = Daemon(DaemonConfig(port=8123), gate=gate_with_stub)

    class FakeServer:
        def __init__(self):
            self.should_exit = False

    class FakeThread:
        def __init__(self):
            self.joins = []

        def join(self, timeout=None):
            self.joins.append(timeout)

    servers = [FakeServer(), FakeServer()]
    threads = [FakeThread(), FakeThread()]
    daemon._servers.extend(zip(servers, threads, strict=True))

    daemon.stop(timeout=6.0)

    assert all(s.should_exit for s in servers)
    assert daemon._stopped.is_set()
    for t in threads:
        assert t.joins == [3.0]  # 6.0 split across the two listeners

    # Idempotent: a second stop() must not touch the servers again.
    daemon.stop(timeout=6.0)
    for t in threads:
        assert t.joins == [3.0]


# --- lifespan finally: queue drains with config.drain_timeout_s -------------


def test_lifespan_shutdown_drains_queued_decisions(gate_with_stub):
    """Exiting the app lifespan runs the REAL finally block:
    ``await queue.stop(drain_timeout=config.drain_timeout_s)``. The
    queued decisions must resolve (drained), not hang or fail. If the
    finally/stop call were stubbed out, _accepting stays True and the
    worker task keeps running, failing the assertions below."""
    async def main():
        config = DaemonConfig(drain_timeout_s=5.0)
        app = create_daemon_app(config, gate_with_stub)
        queue = app.state.batching_queue

        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        try:
            pending = [
                asyncio.create_task(
                    queue.submit({"n": i}, SPEC_DICT, None, None, None))
                for i in range(4)
            ]
            # Let every submitter run its synchronous prefix (the
            # _accepting check + enqueue) before the lifespan exits;
            # create_task only schedules, it does not run them. One
            # sleep(0) drains the ready queue: all four submits were
            # scheduled before main's own resumption, and the worker
            # cannot resolve anything before main yields again, so the
            # drain below genuinely has queued work to do.
            await asyncio.sleep(0)
            assert queue.stats()["queued"] == 4
            # Exit WITHOUT waiting first: the lifespan's finally block
            # must drain the queue before __aexit__ returns. wait_for
            # turns a broken drain into a failure instead of a hang.
            await asyncio.wait_for(
                lifespan.__aexit__(None, None, None), timeout=15.0)
            results = await asyncio.wait_for(
                asyncio.gather(*pending), timeout=5.0)
            assert [r.value for r in results] == ["a"] * 4
            assert queue.stats()["decisions"] == 4
        finally:
            if queue._task is not None and not queue._task.done():
                await queue.stop(drain_timeout=1.0)

        # The drain path really ran: no longer accepting, worker halted.
        assert not queue._accepting
        assert queue._task.done()
        with pytest.raises(QueueFull):
            await queue.submit({"n": 9}, SPEC_DICT, None, None, None)

    asyncio.run(main())


def test_lifespan_shutdown_uses_config_drain_timeout(gate_with_stub,
                                                     monkeypatch):
    """The lifespan's finally block must pass the daemon config's
    drain_timeout_s through to queue.stop(). A hardcoded timeout or a
    dropped call records the wrong value (or nothing)."""
    async def main():
        config = DaemonConfig(drain_timeout_s=7.5)
        app = create_daemon_app(config, gate_with_stub)
        seen = {}
        real_stop = BatchingQueue.stop

        async def spy_stop(self, drain_timeout=10.0):
            seen["drain_timeout"] = drain_timeout
            return await real_stop(self, drain_timeout=drain_timeout)

        monkeypatch.setattr(BatchingQueue, "stop", spy_stop)
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        await lifespan.__aexit__(None, None, None)
        assert seen.get("drain_timeout") == 7.5

    asyncio.run(main())


# --- end to end: a real daemon process exits 0 on SIGTERM --------------------


@pytest.mark.slow
def test_sigterm_to_real_daemon_exits_cleanly():
    """Spawn the REAL daemon (``hugrgate.daemon:main``) as a subprocess,
    send SIGTERM, and require a clean exit code 0. If the signal handler
    were never installed, the default SIGTERM action kills the process
    (returncode -15); if stop() never halts the listeners, the process
    hangs and the wait times out."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = os.path.join(repo, "venv", "bin", "python")
    if not os.path.exists(py):  # pragma: no cover - dev fallback
        py = sys.executable

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    proc = subprocess.Popen(
        [py, "-c",
         "from hugrgate.daemon import main; raise SystemExit(main())",
         "--port", str(port)],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.time() + 25.0
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port),
                                              timeout=1.0):
                    break
            except OSError:
                if proc.poll() is not None:
                    err = proc.stderr.read().decode("utf-8", "replace")
                    raise AssertionError(
                        f"daemon died during startup: {err[-2000:]}") from None
                if time.time() > deadline:
                    raise AssertionError(
                        "daemon did not start listening in 25s") from None
                time.sleep(0.2)
        proc.send_signal(signal.SIGTERM)
        try:
            rc = proc.wait(timeout=25.0)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                "daemon hung after SIGTERM (shutdown path broken?)") from None
        assert rc == 0, f"daemon exited with code {rc}, expected 0"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10.0)
        proc.stderr.close()
