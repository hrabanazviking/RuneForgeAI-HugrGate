"""HG-T2 gate tests — small-fast-model judgment backend.

Gate (roadmap): benchmark report banked — median judgment latency
and accuracy vs the rules-only path; the model path is used only
where the case set proves it earns its cost.

The live-model numbers live in campaign/hg_t2_benchmark_report.json
(produced by benchmarks/hg_t2_benchmark.py against a real local
Ollama endpoint). These tests prove the mechanism deterministically:
selective routing, fallback honesty, the Ollama-shaped client over
real HTTP (a stub Ollama server on an ephemeral port), and the
frozen case set's clear/hard construction.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "benchmarks"))
from hg_t2_cases import CASES, SPEC  # noqa: E402

from hugrgate.backends.llm import LLMBackend, LLMChoice, LLMEngine  # noqa: E402
from hugrgate.decision_server import KeywordBackend  # noqa: E402
from hugrgate.errors import BackendUnavailable  # noqa: E402
from hugrgate.model_backend import (  # noqa: E402
    OllamaEngine,
    SelectiveModelBackend,
    needs_model,
)
from hugrgate.spec import DecisionSpec  # noqa: E402

pytestmark = pytest.mark.integration


def _spec():
    return DecisionSpec.from_dict(dict(SPEC))


class _CountingEngine(LLMEngine):
    name = "counting-fake"

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def generate(self, prompt, choices, max_tokens, timeout_s):
        self.calls += 1
        return LLMChoice(value=self.value, confidence=0.9)


class _DownEngine(LLMEngine):
    name = "down-fake"

    def generate(self, prompt, choices, max_tokens, timeout_s):
        raise BackendUnavailable("endpoint down", backend="fake")


def test_case_set_construction():
    assert len(CASES) == 24
    options = set(SPEC["options"])
    for case in CASES:
        assert case["expected"] in options
        toks = set(case["text"].lower().replace(",", " ")
                   .replace(":", " ").split())
        if case["kind"] == "hard":
            assert not (toks & options), case["id"]
            assert not any(t.startswith(o) for t in toks
                           for o in options if len(o) >= 4), case["id"]
        else:
            assert case["expected"] in toks, case["id"]


def test_rules_settle_clear_but_not_hard():
    rules = KeywordBackend()
    for case in CASES:
        result = rules.evaluate({"text": case["text"]}, _spec())
        if case["kind"] == "clear":
            assert result.value == case["expected"], case["id"]
            assert not needs_model(result), case["id"]
        else:
            assert needs_model(result), case["id"]


def test_selective_backend_skips_model_on_clear_cases():
    engine = _CountingEngine("escalate")
    backend = SelectiveModelBackend(
        model_backend=LLMBackend(engine=engine))
    result = backend.evaluate(
        {"text": "escalate this incident now"}, _spec())
    assert result.value == "escalate"
    assert result.metadata["route"] == "rules"
    assert result.metadata["model_used"] is False
    assert engine.calls == 0  # model never paid for a settled case


def test_selective_backend_uses_model_on_hard_cases():
    engine = _CountingEngine("escalate")
    backend = SelectiveModelBackend(
        model_backend=LLMBackend(engine=engine))
    result = backend.evaluate(
        {"text": "smoke is coming from the server rack"}, _spec())
    assert engine.calls == 1
    assert result.value == "escalate"
    assert result.metadata["route"] == "model"
    assert result.metadata["model_used"] is True
    assert result.metadata["rules_value"] == "routine"
    assert result.metadata["confidence_calibrated"] is False


def test_model_failure_falls_back_to_rules_honestly():
    backend = SelectiveModelBackend(
        model_backend=LLMBackend(engine=_DownEngine()))
    result = backend.evaluate(
        {"text": "payments failing for every order since noon"},
        _spec())
    assert result.metadata["route"] == "rules-fallback"
    assert result.metadata["model_used"] is False
    assert "model_error" in result.metadata
    assert result.value in SPEC["options"]  # a verdict still exists


# --- Ollama client over real HTTP (stub Ollama-shaped server) --------

class _StubOllama(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/api/tags":
            body = {"models": [{"name": "stub-model:latest"}]}
        else:
            body = {"error": "not found"}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        assert payload["model"] == "stub-model:latest"
        assert payload["stream"] is False
        raw = json.dumps({"response": "escalate."}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture()
def stub_ollama():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _StubOllama)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_ollama_engine_against_stub_endpoint(stub_ollama):
    engine = OllamaEngine(model="stub-model:latest",
                          base_url=stub_ollama)
    health = engine.health()
    assert health["status"] == "ok"
    assert health["model_present"] is True
    choice = engine.generate("prompt", ["routine", "escalate"], 8, 5.0)
    assert choice.value == "escalate"  # trailing punctuation stripped


def test_ollama_engine_unreachable_is_unavailable():
    engine = OllamaEngine(model="x", base_url="http://127.0.0.1:9",
                          timeout_s=1.0)
    assert engine.health()["status"] == "unavailable"
    with pytest.raises(BackendUnavailable):
        engine.generate("p", ["routine"], 4, 1.0)
