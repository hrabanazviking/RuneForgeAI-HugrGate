"""Slice 435 — doctor against a live server (slow).

Spawns a real uvicorn HugrGate service on an ephemeral port and
runs ``hugrgate doctor`` against it end to end.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest

pytestmark = pytest.mark.slow

from hugrgate.cli import main


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_url():
    import uvicorn

    from hugrgate.server import create_app
    port = _free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    # trust_env=False: the sandbox sets proxy env vars that httpx
    # chokes on (the same reason hugrgate.client sets it).
    probe = httpx.Client(trust_env=False)
    while time.time() < deadline:
        try:
            r = probe.get(f"{url}/health", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:  # noqa: BLE001 - polling for readiness
            time.sleep(0.05)
    else:
        probe.close()
        pytest.fail("uvicorn server did not start")
    probe.close()
    yield url
    server.should_exit = True
    thread.join(timeout=10)


def test_doctor_passes_against_live_server(live_url, capsys):
    assert main(["doctor", "--url", live_url]) == 0
    out = capsys.readouterr().out
    assert "[ok] service reachable" in out
    assert "[ok] protocol version agreement" in out
    assert "[ok] backend inventory" in out
    assert "[ok] end-to-end decision" in out
    assert "value=" in out
