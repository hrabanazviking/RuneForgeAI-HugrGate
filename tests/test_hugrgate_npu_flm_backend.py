"""NPU Phase 2 gate tests — FastFlowLM (flm serve) judgment engine.

The live-model numbers live in campaign/hg_npu_benchmark_report.json
(produced by benchmarks/hg_npu_benchmark.py against a real ``flm
serve`` on the deployment host's XDNA2 NPU). These tests prove the
mechanism deterministically, in the HG-T2 style: the OpenAI-shaped
client over real HTTP (a stub FLM server on an ephemeral port),
logprob-derived confidence with its honest fallback, transport
failure as BackendUnavailable, and the selective backend's rules
routing + rules-fallback behaviour unchanged on the new wire.
"""

from __future__ import annotations

import json
import math
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "benchmarks"))
from hg_t2_cases import CASES, SPEC  # noqa: E402

from hugrgate.core import HugrGate  # noqa: E402
from hugrgate.errors import BackendError, BackendUnavailable  # noqa: E402
from hugrgate.flm_backend import (  # noqa: E402
    FlmEngine,
    build_flm_backend,
)
from hugrgate.model_backend import (  # noqa: E402
    UNCALIBRATED_CONFIDENCE,
    SelectiveModelBackend,
)
from hugrgate.spec import DecisionSpec  # noqa: E402

pytestmark = pytest.mark.integration


def _spec():
    return DecisionSpec.from_dict(dict(SPEC))


class _StubFlm:
    """A minimal flm-serve-shaped stub: /v1/models + completions."""

    def __init__(self, content="escalate", logprob=None):
        self.content = content
        self.logprob = logprob
        self.requests = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _json(self, payload):
                raw = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/v1/models":
                    self._json({"data": [{"id": "qwen3:0.6b",
                                          "object": "model"}]})
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.end_headers()
                    return
                outer.requests += 1
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                choice = {"index": 0,
                          "message": {"role": "assistant",
                                      "content": outer.content}}
                if outer.logprob is not None:
                    choice["logprobs"] = {"content": [{
                        "token": outer.content,
                        "logprob": outer.logprob,
                        "top_logprobs": []}]}
                self._json({"id": "stub", "object": "chat.completion",
                            "choices": [choice]})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        return None


def test_flm_engine_generate_over_http_with_logprob_confidence():
    with _StubFlm(content="escalate",
                  logprob=math.log(0.9)) as stub:
        engine = FlmEngine(base_url=stub.base_url)
        choice = engine.generate("prompt", ["routine", "attention",
                                              "escalate"], 32, 5.0)
    assert choice.value == "escalate"
    assert choice.confidence == pytest.approx(0.9, abs=1e-6)
    assert stub.requests == 1


def test_flm_engine_confidence_falls_back_without_logprobs():
    with _StubFlm(content="attention") as stub:
        engine = FlmEngine(base_url=stub.base_url)
        choice = engine.generate("prompt", ["routine"], 32, 5.0)
    assert choice.value == "attention"
    assert choice.confidence == UNCALIBRATED_CONFIDENCE


def test_flm_engine_empty_response_is_an_error_not_a_choice():
    with _StubFlm(content="  ") as stub:
        engine = FlmEngine(base_url=stub.base_url)
        with pytest.raises(BackendError):
            engine.generate("prompt", ["routine"], 32, 5.0)


def test_flm_engine_down_endpoint_is_unavailable():
    engine = FlmEngine(base_url="http://127.0.0.1:1", timeout_s=2.0)
    with pytest.raises(BackendUnavailable):
        engine.generate("prompt", ["routine"], 32, 2.0)
    assert engine.health()["status"] == "unavailable"


def test_flm_engine_health_lists_served_model():
    with _StubFlm() as stub:
        engine = FlmEngine(base_url=stub.base_url)
        health = engine.health()
    assert health["status"] == "ok"
    assert health["model_present"] is True
    assert health["model"] == "qwen3:0.6b"


def test_selective_backend_on_flm_wire_routes_and_falls_back():
    clear = next(c for c in CASES if c["kind"] == "clear")
    hard = next(c for c in CASES if c["kind"] == "hard")
    with _StubFlm(content=hard["expected"]) as stub:
        backend = SelectiveModelBackend(
            model_backend=build_flm_backend(base_url=stub.base_url))
        clear_result = backend.evaluate({"text": clear["text"]},
                                        _spec())
        assert clear_result.metadata["route"] == "rules"
        assert stub.requests == 0  # clear cases never pay model cost
        hard_result = backend.evaluate({"text": hard["text"]},
                                       _spec())
        assert hard_result.metadata["route"] == "model"
        assert hard_result.value == hard["expected"]
        assert stub.requests == 1
    # NPU endpoint gone: the same hard case degrades to rules-only
    # with the failure recorded — judgment never breaks.
    dead = SelectiveModelBackend(model_backend=build_flm_backend(
        base_url="http://127.0.0.1:1"))
    fallen = dead.evaluate({"text": hard["text"]}, _spec())
    assert fallen.metadata["route"] == "rules-fallback"
    assert "model_error" in fallen.metadata


def test_flm_backend_surfaces_in_gate_registry():
    gate = HugrGate()
    gate.register(SelectiveModelBackend(
        model_backend=build_flm_backend()))
    assert "model-assisted" in gate.registry.list()
    caps = gate.registry.get("model-assisted").capabilities()
    assert caps["model_engine"] == "flm:qwen3:0.6b"
    assert caps["selective"] is True
