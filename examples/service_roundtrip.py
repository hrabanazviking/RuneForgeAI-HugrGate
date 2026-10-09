"""Service round-trip — HTTP daemon + Python SDK client (Slice 43).

Starts a real HugrGate daemon in a background thread, decides over HTTP
with HugrGateClient, then shows the automatic in-process fallback when
the service is unreachable.

Run:  venv/bin/python examples/service_roundtrip.py
"""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate import DecisionPolicy, DecisionSpec  # noqa: E402
from hugrgate.client import HugrGateClient  # noqa: E402
from hugrgate.daemon import Daemon, DaemonConfig  # noqa: E402

SPEC = DecisionSpec(type="categorical",
                    options=["ignore", "log", "investigate", "escalate"])
POLICY = DecisionPolicy(minimum_probability=0.3)
STATE = {"alert": "ESCALATE: ransomware signature detected "
                  "on web-01 — isolate now."}


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> None:
    port = free_port()
    daemon = Daemon(DaemonConfig(port=port, batch_window_ms=5))
    daemon.start()
    try:
        client = HugrGateClient(f"http://127.0.0.1:{port}")
        for _ in range(100):
            if client.health().get("reachable"):
                break
            time.sleep(0.1)
        print("health:", client.health()["status"],
              "| backends:", client.health()["backends"])

        result = client.decide(STATE, SPEC, POLICY, backend_name="keyword")
        print(f"HTTP decide   -> {result.value} "
              f"(p={result.probability:.3f}, "
              f"transport={result.metadata['client_transport']}, "
              f"latency={result.latency_ms:.1f}ms)")
        client.close()

        # Same interface, no server: automatic in-process fallback.
        offline = HugrGateClient("http://127.0.0.1:1", timeout=1.0)
        result = offline.decide(STATE, SPEC, POLICY, backend_name="keyword")
        print(f"fallback      -> {result.value} "
              f"(p={result.probability:.3f}, "
              f"fallback={result.metadata['client_fallback']})")
        print("offline health:", offline.health())
        offline.close()
    finally:
        daemon.stop()
    print("daemon stopped.")


if __name__ == "__main__":
    main()
