"""HugrGate resident supervisor — NPU Phase 2 (Volmarr's commission).

The resident shape Volmarr approved for this service (2026-11-19),
mirroring gufo-resident / whisper-resident: a cheap supervisor that
is always up, owning exactly ONE expensive child. Here the child is
``flm serve <judge-model>`` on the XDNA2 NPU (the NPU grants a
single context — a second FLM process cannot get one), and the
supervisor itself hosts the HG-T1 decision server in-process,
configured with the FLM-backed selective model backend
(:mod:`hugrgate.flm_backend`).

Behaviour contract:

- The judge stays resident on the NPU while the service is up:
  judge calls are latency-critical and rare (rules settle the clear
  half of judgments without any model call at all).
- If the flm child dies, the supervisor restarts it (backoff,
  logged). While it is down, the decision server keeps answering:
  the selective backend degrades unsettled cases to rules-only
  verdicts with ``model_error`` recorded. Judgment never wedges.
- Loopback only, both hops (decision server and flm serve).
- SIGTERM/SIGINT: decision server drains, flm child is terminated,
  supervisor exits. Boring shutdown, like HG-T1.

The systemd user unit that runs this supervisor is authored with
the service (deploy/systemd/hugrgate-resident.service) and carries
``LimitMEMLOCK=infinity``: ``flm`` refuses to run under the default
8 MiB memlock a systemd user service inherits, and the PAM limits
file does not reach user services (proven in Phase 2 step 1).

Stdlib only. Run: python3 tools/hugrgate_resident.py --judge-model qwen3:0.6b
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.core import HugrGate  # noqa: E402
from hugrgate.decision_server import (  # noqa: E402
    DecisionServer,
    KeywordBackend,
    UniformBackend,
)
from hugrgate.flm_backend import build_flm_backend  # noqa: E402
from hugrgate.model_backend import SelectiveModelBackend  # noqa: E402


def _log(event: str, **fields) -> None:
    print(json.dumps({"ts": round(time.time(), 3),
                      "service": "hugrgate-resident",
                      "event": event, **fields}), flush=True)


def _flm_healthy(base_url: str, timeout_s: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/v1/models",
                                    timeout=timeout_s) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 - a probe, any failure is "no"
        return False


class FlmSupervisor:
    """Owns the single flm serve child; restarts it on death."""

    def __init__(self, flm_bin: str, model: str, base_url: str,
                 port: int):
        self.flm_bin = flm_bin
        self.model = model
        self.base_url = base_url
        self.port = port
        self.child: subprocess.Popen | None = None
        self.restarts = 0
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def _spawn(self) -> None:
        self.child = subprocess.Popen(
            [self.flm_bin, "serve", self.model,
             "--host", "127.0.0.1", "-p", str(self.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _log("flm_spawned", pid=self.child.pid, model=self.model)

    def _wait_healthy(self, timeout_s: float = 120.0) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline and not self._stopped.is_set():
            if self.child is not None and self.child.poll() is not None:
                return False  # died during load
            if _flm_healthy(self.base_url):
                return True
            time.sleep(0.5)
        return False

    def start(self) -> bool:
        self._spawn()
        ok = self._wait_healthy()
        _log("flm_healthy" if ok else "flm_unhealthy_at_start",
             model=self.model)
        self._thread = threading.Thread(target=self._watch,
                                        name="flm-watch", daemon=True)
        self._thread.start()
        return ok

    def _watch(self) -> None:
        delay = 3.0
        while not self._stopped.wait(2.0):
            if self.child is None or self.child.poll() is None:
                continue
            rc = self.child.returncode
            self.restarts += 1
            _log("flm_child_died", returncode=rc,
                 restart=self.restarts,
                 note="gate is rules-only until the judge is back")
            if self._stopped.wait(delay):
                break
            self._spawn()
            if self._wait_healthy():
                _log("flm_revived", restart=self.restarts)
                delay = 3.0
            else:
                _log("flm_revive_failed", restart=self.restarts)
                delay = min(delay * 2, 30.0)

    def stop(self) -> None:
        self._stopped.set()
        if self.child is not None and self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                self.child.kill()
        _log("flm_stopped", restarts=self.restarts)


def build_resident_gate(model: str, flm_base_url: str) -> HugrGate:
    """The resident gate: deterministic backends + FLM selective."""
    gate = HugrGate()
    gate.register(UniformBackend())
    gate.register(KeywordBackend())
    gate.register(SelectiveModelBackend(
        model_backend=build_flm_backend(model=model,
                                        base_url=flm_base_url)))
    return gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hugrgate-resident")
    parser.add_argument("--judge-model", default="qwen3:0.6b")
    parser.add_argument("--flm-bin", default="/usr/bin/flm")
    parser.add_argument("--flm-port", type=int, default=52625)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8387)
    parser.add_argument("--ledger", default=None,
                        help="HG-T6 judgment ledger path")
    args = parser.parse_args(argv)

    flm_base_url = f"http://127.0.0.1:{args.flm_port}"
    supervisor = FlmSupervisor(args.flm_bin, args.judge_model,
                               flm_base_url, args.flm_port)
    supervisor.start()

    gate = build_resident_gate(args.judge_model, flm_base_url)
    server = DecisionServer(host=args.host, port=args.port, gate=gate,
                            ledger_path=args.ledger)
    server.start()
    _log("resident_up", judge_model=args.judge_model,
         flm_base_url=flm_base_url,
         decision_address=f"{args.host}:{args.port}")

    stopped = threading.Event()

    def _signal(_signum, _frame):
        stopped.set()

    signal.signal(signal.SIGINT, _signal)
    signal.signal(signal.SIGTERM, _signal)
    try:
        while not stopped.wait(1.0):
            pass
    finally:
        server.stop()
        supervisor.stop()
        _log("resident_down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
