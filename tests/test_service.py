"""Tests for Batch E (Slices 41-50): service & ecosystem."""

import pytest
from fastapi.testclient import TestClient

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backends.rules import RuleBackend
from hugrgate.bench import run_benchmark
from hugrgate.client import HugrGateClient, policy_from_dict
from hugrgate.drift import DriftMonitor
from hugrgate.server import build_gate, create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_backends_list(client):
    r = client.get("/backends")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_decide_endpoint(client):
    payload = {
        "state": {"temperature": 95},
        "spec": {"type": "categorical", "options": ["ignore", "escalate"]},
        "policy": {"minimum_probability": 0.0},
    }
    r = client.post("/decide", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["value"] in ["ignore", "escalate"]
    assert 0.0 <= data["probability"] <= 1.0


def test_decide_invalid_spec(client):
    payload = {
        "state": {},
        "spec": {"type": "categorical", "options": ["only_one"]},
    }
    r = client.post("/decide", json=payload)
    # Server returns 400 with structured error for invalid spec
    assert r.status_code in (400, 422)


def test_build_gate():
    gate = build_gate()
    assert isinstance(gate, HugrGate)
    assert len(gate.registry.list()) >= 1


def test_policy_from_dict():
    p = policy_from_dict({"minimum_probability": 0.9})
    assert isinstance(p, DecisionPolicy)
    assert p.minimum_probability == 0.9


def _make_rules_gate() -> HugrGate:
    """Helper: gate with a simple temperature triage ruleset."""
    gate = HugrGate()
    gate.register(RuleBackend.from_dicts([
        {"if": {"field": "temperature", "gt": 90}, "then": "escalate",
         "confidence": 0.99},
        {"default": "ignore", "confidence": 0.5},
    ], name="rules"))
    return gate


def test_client_in_process():
    gate = _make_rules_gate()
    client = HugrGateClient(gate=gate)
    spec = DecisionSpec(type="categorical", options=["ignore", "escalate"])
    result = client.decide({"temperature": 95}, spec)
    assert result.value == "escalate"


def test_benchmark_harness():
    gate = HugrGate()
    gate.register(RuleBackend.from_dicts([
        {"if": {"field": "x", "gt": 0}, "then": "pos", "confidence": 0.9},
        {"default": "neg", "confidence": 0.9},
    ], name="rules"))
    dataset = {
        "spec": {"type": "categorical", "options": ["pos", "neg"]},
        "items": [
            {"state": {"x": 1}, "expected": "pos"},
            {"state": {"x": -1}, "expected": "neg"},
        ],
    }
    report = run_benchmark(dataset, gate, backends=["rules"])
    assert "rules" in report["backends"]
    assert report["backends"]["rules"]["accuracy"] == 1.0


def test_drift_monitor():
    dm = DriftMonitor()
    # Reference: high confidences
    dm.fit_reference([0.9] * 100)
    # Live: still high → no drift
    report = dm.observe([0.9] * 50)
    assert not report.alert
    # Live: low confidences → drift
    report2 = dm.observe([0.3] * 50)
    assert report2.psi > 0

# ---------------------------------------------------------------------------
# Additional Batch E tests (subagent E): deeper coverage of slices 41-48.
# ---------------------------------------------------------------------------

import asyncio as _asyncio
import hashlib as _hashlib
import inspect as _inspect
import json as _json
import os as _os
import socket as _socket
import sys as _sys

import hugrgate.server as _server_mod
from hugrgate import Abstention as _Abstention
from hugrgate import DecisionResult as _DecisionResult
from hugrgate import cli as _cli
from hugrgate.bench import Benchmark as _Benchmark
from hugrgate.bench import accuracy as _accuracy
from hugrgate.bench import brier_score as _brier
from hugrgate.bench import expected_calibration_error as _ece
from hugrgate.bench import run_benchmark as _run_benchmark
from hugrgate.bench_report import ascii_reliability_diagram as _ascii_diag
from hugrgate.bench_report import render_markdown as _render_markdown
from hugrgate.bench_report import write_report as _write_report
from hugrgate.client import HugrGateClient as _Client2
from hugrgate.client import policy_to_dict as _policy_to_dict
from hugrgate.client import result_from_dict as _result_from_dict
from hugrgate.daemon import BatchingQueue as _BatchingQueue
from hugrgate.daemon import Daemon as _Daemon
from hugrgate.daemon import DaemonConfig as _DaemonConfig
from hugrgate.daemon import create_daemon_app as _create_daemon_app
from hugrgate.daemon import load_client_policies as _load_client_policies
from hugrgate.drift import DriftMonitor as _DriftMonitor2
from hugrgate.drift import population_stability_index as _psi_fn
from hugrgate.drift import recalibration_advisory as _advisory
from hugrgate.server import KeywordBackend as _KeywordBackend
from hugrgate.server import UniformBackend as _UniformBackend
from hugrgate.server import build_gate as _build_gate2

_TRIAGE_SPEC = {"type": "categorical",
                "options": ["ignore", "log", "investigate", "escalate"]}
_TRIAGE_STATE = {"alert": "ESCALATE: ransomware signature detected "
                          "on web-01 — isolate now."}


def _free_port():
    s = _socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _tiny_dataset(n=20):
    items = []
    for i in range(n):
        label = "yes" if i % 2 == 0 else "no"
        items.append({"id": f"t-{i:03d}",
                      "state": {"text": f"this is clearly {label} stuff"},
                      "spec_type": "categorical",
                      "expected": label})
    return {"name": "tiny", "version": "test",
            "spec": {"type": "categorical", "options": ["yes", "no"]},
            "items": items}


# --- Slice 41 extras -------------------------------------------------------

def test_health_reports_version_and_backends(client):
    body = client.get("/health").json()
    assert body["version"] == "0.1.0"
    assert {b["name"] for b in client.get("/backends").json()} >= {
        "uniform", "keyword"}


def test_models_endpoint_lists_catalogue(client):
    names = {m["name"] for m in client.get("/models").json()}
    assert {"uniform-1.0", "keyword-1.0"} <= names


def test_decide_abstention_flag(client):
    r = client.post("/decide", json={
        "spec": _TRIAGE_SPEC, "state": _TRIAGE_STATE,
        "backend_name": "keyword",
        "policy": {"minimum_probability": 1.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["abstained"] is True
    assert body["code"] == "abstention"


def test_decide_unknown_backend_503(client):
    r = client.post("/decide", json={
        "spec": _TRIAGE_SPEC, "state": _TRIAGE_STATE,
        "backend_name": "nope"})
    assert r.status_code == 503


def test_decide_bad_policy_422(client):
    r = client.post("/decide", json={
        "spec": _TRIAGE_SPEC, "state": _TRIAGE_STATE,
        "policy": {"minimum_probability": 2.0}})
    assert r.status_code == 422


def test_server_run_defaults_to_localhost():
    sig = _inspect.signature(_server_mod.run)
    assert sig.parameters["host"].default == "127.0.0.1"


def test_keyword_backend_picks_escalate():
    spec = DecisionSpec(type="categorical",
                        options=_TRIAGE_SPEC["options"])
    res = _KeywordBackend().evaluate(_TRIAGE_STATE, spec)
    assert res.value == "escalate"
    assert abs(sum(res.distribution.values()) - 1.0) < 1e-9


def test_uniform_backend_numeric_midpoint():
    spec = DecisionSpec(type="numeric", minimum=0.0, maximum=10.0)
    assert _UniformBackend().evaluate({"x": 1}, spec).value == 5.0


# --- Slice 42 extras -------------------------------------------------------

def test_batching_queue_coalesces():
    async def go():
        queue = _BatchingQueue(_build_gate2(), window_ms=30, max_batch=32)
        await queue.start()
        spec = DecisionSpec(type="categorical", options=["a", "b"])
        results = await _asyncio.gather(*[
            queue.submit({"t": "a a a"}, spec.to_dict(), None,
                         "keyword", None) for _ in range(10)])
        stats = queue.stats()
        await queue.stop()
        return results, stats

    results, stats = _asyncio.run(go())
    assert all(r.value == "a" for r in results)
    assert stats["decisions"] == 10
    assert stats["max_batch_seen"] >= 2


def test_batching_queue_abstention_propagates():
    async def go():
        queue = _BatchingQueue(_build_gate2(), window_ms=5)
        await queue.start()
        spec = DecisionSpec(type="categorical", options=["a", "b"])
        policy = _policy_to_dict(DecisionPolicy(minimum_probability=1.0))
        try:
            await queue.submit({"t": "a"}, spec.to_dict(), policy,
                               "keyword", None)
        except _Abstention:
            caught = True
        else:
            caught = False
        await queue.stop()
        return caught

    assert _asyncio.run(go()) is True


def test_daemon_per_client_policy(tmp_path):
    path = tmp_path / "policies.json"
    path.write_text(_json.dumps({
        "strict-client": _policy_to_dict(
            DecisionPolicy(minimum_probability=1.0))}))
    config = _DaemonConfig(client_policies_path=str(path),
                           batch_window_ms=2)
    app = _create_daemon_app(config)
    with TestClient(app) as tc:
        body = {"spec": _TRIAGE_SPEC, "state": _TRIAGE_STATE,
                "backend_name": "keyword"}
        r = tc.post("/decide", json=body,
                    headers={"x-client-id": "strict-client"})
        assert r.json()["abstained"] is True
        r = tc.post("/decide", json=body,
                    headers={"x-client-id": "nobody"})
        assert r.json()["value"] == "escalate"
        assert tc.get("/daemon").json()["client_policies"] == [
            "strict-client"]


def test_load_client_policies(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(_json.dumps(
        {"c": _policy_to_dict(DecisionPolicy(minimum_probability=0.9))}))
    assert _load_client_policies(str(path))["c"].minimum_probability == 0.9


def test_daemon_lifecycle_threaded():
    import httpx
    port = _free_port()
    daemon = _Daemon(_DaemonConfig(port=port, batch_window_ms=5))
    daemon.start()
    try:
        with httpx.Client(trust_env=False) as http:
            for _ in range(100):
                try:
                    r = http.get(f"http://127.0.0.1:{port}/health",
                                 timeout=2)
                    if r.status_code == 200:
                        break
                except Exception:  # noqa: BLE001 - retry until the server answers
                    import time
                    time.sleep(0.1)
            else:
                raise AssertionError("daemon did not become healthy")
            assert r.json()["status"] == "ok"
            r = http.post(f"http://127.0.0.1:{port}/decide", json={
                "spec": _TRIAGE_SPEC, "state": _TRIAGE_STATE,
                "backend_name": "keyword"}, timeout=10)
            assert r.json()["value"] == "escalate"
    finally:
        daemon.stop()
    assert not any(t.is_alive() for _, t in daemon._servers)


# --- Slice 43 extras -------------------------------------------------------

def test_policy_serde_roundtrip():
    p = DecisionPolicy(minimum_probability=0.7, remote_inference=True,
                       allowed_backends=["keyword"],
                       fallback_behavior="escalate",
                       privacy_class="strict", review_band=(0.4, 0.7))
    q = _policy_to_dict(p)
    r = _json.loads(_json.dumps(q))
    from hugrgate.client import policy_from_dict as _pfd
    s = _pfd(r)
    assert s.minimum_probability == 0.7
    assert s.review_band == (0.4, 0.7)
    assert s.privacy_class == "strict"


def test_result_serde_roundtrip():
    r = _DecisionResult(value="a", probability=0.8,
                        distribution={"a": 0.8, "b": 0.2},
                        backend="keyword")
    q = _result_from_dict(_json.loads(_json.dumps(r.to_dict())))
    assert (q.value, q.probability, q.backend) == ("a", 0.8, "keyword")


def test_client_fallback_inprocess():
    c = _Client2(url="http://127.0.0.1:1", timeout=1.0,
                 fallback_inprocess=True)
    try:
        spec = DecisionSpec(type="categorical", options=["a", "b"])
        result = c.decide({"t": "a a"}, spec, backend_name="keyword")
        assert result.value == "a"
        assert result.metadata["client_fallback"] == "inprocess"
        assert c.health()["reachable"] is False
    finally:
        c.close()


def test_client_no_fallback_raises():
    from hugrgate import BackendError
    c = _Client2(url="http://127.0.0.1:1", timeout=1.0,
                 fallback_inprocess=False)
    try:
        with pytest.raises(BackendError):
            c.decide({"t": "a"},
                     DecisionSpec(type="categorical", options=["a", "b"]))
    finally:
        c.close()


def test_client_roundtrip_against_daemon():
    port = _free_port()
    daemon = _Daemon(_DaemonConfig(port=port, batch_window_ms=5))
    daemon.start()
    c = _Client2(url=f"http://127.0.0.1:{port}")
    try:
        import time
        for _ in range(100):
            if c.health().get("reachable"):
                break
            time.sleep(0.1)
        spec = DecisionSpec(type="categorical",
                            options=_TRIAGE_SPEC["options"])
        result = c.decide(_TRIAGE_STATE, spec, backend_name="keyword")
        assert result.value == "escalate"
        assert result.metadata["client_transport"] == "http"
        assert {b["name"] for b in c.backends()} == {"uniform", "keyword"}
        with pytest.raises(_Abstention):
            c.decide(_TRIAGE_STATE, spec, backend_name="keyword",
                     policy=DecisionPolicy(minimum_probability=1.0))
    finally:
        c.close()
        daemon.stop()


# --- Slice 44 extras -------------------------------------------------------

def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return str(p)


def test_cli_decide_inprocess(tmp_path, capsys):
    spec = _write(tmp_path, "spec.yaml",
                  "type: categorical\noptions: [ignore, log, investigate, escalate]\n")
    state = _write(tmp_path, "state.json", _json.dumps(_TRIAGE_STATE))
    assert _cli.main(["decide", "--spec", spec, "--state", state,
                      "--backend", "keyword"]) == 0
    out = _json.loads(capsys.readouterr().out)
    assert out["abstained"] is False
    assert out["decision"]["value"] == "escalate"


def test_cli_decide_abstains(tmp_path, capsys):
    spec = _write(tmp_path, "spec.json", _json.dumps(_TRIAGE_SPEC))
    state = _write(tmp_path, "state.json", _json.dumps(_TRIAGE_STATE))
    policy = _write(tmp_path, "policy.yaml", "minimum_probability: 1.0\n")
    assert _cli.main(["decide", "--spec", spec, "--state", state,
                      "--policy", policy, "--backend", "keyword"]) == 0
    assert _json.loads(capsys.readouterr().out)["abstained"] is True


def test_cli_backends_models_health_local(tmp_path, capsys):
    assert _cli.main(["backends"]) == 0
    assert "keyword" in capsys.readouterr().out
    assert _cli.main(["models"]) == 0
    assert "keyword-1.0" in capsys.readouterr().out


def test_cli_against_daemon(tmp_path, capsys):
    port = _free_port()
    daemon = _Daemon(_DaemonConfig(port=port, batch_window_ms=5))
    daemon.start()
    try:
        import time
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            if _cli.main(["health", "--url", url]) == 0:
                break
            time.sleep(0.1)
        assert _json.loads(capsys.readouterr().out)["reachable"] is True
        spec = _write(tmp_path, "spec.json", _json.dumps(_TRIAGE_SPEC))
        state = _write(tmp_path, "state.json", _json.dumps(_TRIAGE_STATE))
        assert _cli.main(["decide", "--spec", spec, "--state", state,
                          "--backend", "keyword", "--url", url]) == 0
        out = _json.loads(capsys.readouterr().out)
        assert out["abstained"] is False
        assert out["decision"]["value"] == "escalate"
    finally:
        daemon.stop()


def test_cli_bench_and_report(tmp_path, capsys):
    ds = _write(tmp_path, "tiny.json", _json.dumps(_tiny_dataset()))
    out = str(tmp_path / "bench.json")
    assert _cli.main(["bench", "--dataset", ds, "--backends",
                      "keyword,uniform", "--out", out]) == 0
    report = _json.loads(open(out).read())
    assert set(report["backends"]) == {"keyword", "uniform"}
    md = str(tmp_path / "bench.md")
    assert _cli.main(["report", "--report", out, "--out", md]) == 0
    text = open(md).read()
    assert text.startswith("# HugrGate benchmark report")
    assert "Reliability diagram" in text


# --- Slice 45 extras -------------------------------------------------------

def test_run_benchmark_full_metrics():
    report = _run_benchmark(_tiny_dataset(), _build_gate2(),
                            backends=["keyword", "uniform"])
    kw = report["backends"]["keyword"]
    assert kw["accuracy"] == 1.0
    assert 0.0 <= kw["brier_score"] <= 2.0
    assert 0.0 <= kw["ece"] <= 1.0
    assert kw["latency_p99_ms"] >= kw["latency_p50_ms"] >= 0.0
    assert kw["throughput_per_s"] > 0
    assert len(kw["reliability_bins"]) == 10
    assert report["backends"]["uniform"]["accuracy"] == 0.5
    _json.dumps(report)


def test_benchmark_class_list_dataset():
    gate = _build_gate2()
    dataset = [{"state": {"text": "yes indeed"}, "expected": "yes",
                "spec": {"type": "categorical", "options": ["yes", "no"]}},
               {"state": {"text": "no way"}, "expected": "no",
                "spec": {"type": "categorical", "options": ["yes", "no"]}}]
    report = _Benchmark(gate, dataset).run(["keyword"])
    assert report["backends"]["keyword"]["accuracy"] == 1.0


def test_benchmark_abstentions_counted():
    report = _run_benchmark(
        _tiny_dataset(), _build_gate2(), backends=["keyword"],
        policy=DecisionPolicy(minimum_probability=1.0))
    m = report["backends"]["keyword"]
    assert m["n_decided"] == 0 and m["abstention_rate"] == 1.0
    assert m["accuracy"] is None


def test_metric_primitives_known_values():
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    pairs = [("a", _DecisionResult(value="a", probability=1.0,
                                   distribution={"a": 1.0, "b": 0.0})),
             ("b", _DecisionResult(value="a", probability=1.0,
                                   distribution={"a": 1.0, "b": 0.0}))]
    assert _accuracy(pairs) == 0.5
    assert _brier(pairs, spec) == pytest.approx(1.0)
    assert _ece(pairs) == pytest.approx(0.5)


# --- Slice 46: dataset integrity -------------------------------------------

def _load_dataset(kind):
    base = _os.path.join(_os.path.dirname(__file__), "..", "benchmarks")
    with open(_os.path.join(base, f"{kind}_500.json"),
              encoding="utf-8") as f:
        return _json.load(f)


@pytest.mark.parametrize("kind,per_class",
                         [("intent", 100), ("urgency", 125), ("triage", 125)])
def test_datasets_balanced(kind, per_class):
    from collections import Counter
    ds = _load_dataset(kind)
    assert len(ds["items"]) == 500
    assert set(Counter(i["expected"] for i in ds["items"]).values()) == {
        per_class}


@pytest.mark.parametrize("kind", ["intent", "urgency", "triage"])
def test_dataset_schema(kind):
    ds = _load_dataset(kind)
    spec = DecisionSpec.from_dict(ds["spec"])
    space = spec.value_space()
    for item in ds["items"]:
        assert set(item) == {"id", "state", "spec_type", "expected"}
        assert item["spec_type"] == spec.type
        assert isinstance(item["state"], dict) and item["state"]
        assert item["expected"] in space


def test_dataset_checksums():
    base = _os.path.join(_os.path.dirname(__file__), "..", "benchmarks")
    lines = open(_os.path.join(base, "CHECKSUMS.sha256")).read().split()
    for digest, name in zip(lines[0::2], lines[1::2], strict=True):
        actual = _hashlib.sha256(
            open(_os.path.join(base, name), "rb").read()).hexdigest()
        assert actual == digest, name


def test_dataset_builder_deterministic():
    _sys_path = _os.path.join(_os.path.dirname(__file__), "..", "benchmarks")
    if _sys_path not in _sys.path:
        _sys.path.insert(0, _sys_path)
    import build as _builder

    from hugrgate.bench import dataset_fingerprint as _fp
    assert _fp(_builder.build_dataset("triage")) == _fp(
        _builder.build_dataset("triage"))


# --- Slice 47 extras -------------------------------------------------------

def test_render_markdown_full_structure():
    text = _render_markdown(
        _run_benchmark(_tiny_dataset(), _build_gate2(),
                       backends=["keyword"]))
    assert text.startswith("# HugrGate benchmark report")
    assert "| backend | n | accuracy |" in text
    assert "## keyword" in text
    assert "### Reliability diagram" in text
    assert "## Methodology & hardware" in text


def test_ascii_diagram_marks():
    text = _ascii_diag([
        {"bin_low": 0.9, "bin_high": 1.0, "count": 10,
         "accuracy": 1.0, "avg_confidence": 0.95},
        {"bin_low": 0.0, "bin_high": 0.1, "count": 0,
         "accuracy": 0.0, "avg_confidence": 0.0}], width=10)
    assert "#" * 10 in text and "|" in text and "(empty)" in text


def test_write_report_to_file(tmp_path):
    path = _write_report(
        _run_benchmark(_tiny_dataset(), _build_gate2(),
                       backends=["keyword"]),
        str(tmp_path / "r.md"))
    assert open(path).read().startswith("# HugrGate benchmark report")


# --- Slice 48 extras -------------------------------------------------------

def test_psi_identical_is_zero():
    vals = [0.1 * (i % 10) + 0.05 for i in range(200)]
    m = _DriftMonitor2()
    m.fit_reference(vals)
    report = m.observe(list(vals))
    assert report.psi == pytest.approx(0.0, abs=1e-9)
    assert report.alert is False


def test_drift_watch_and_advisory():
    m = _DriftMonitor2()
    m.fit_reference([0.9] * 100)
    report = m.observe([0.15] * 100)
    assert report.alert is True and report.severity == "action"
    adv = _advisory(report)
    assert adv["action"] == "recalibrate"
    assert len(adv["recommended_steps"]) >= 3
    calm = _advisory(m.observe([0.9] * 100))
    assert calm["action"] == "none"


def test_drift_min_samples_gate():
    m = _DriftMonitor2(min_live_samples=30)
    m.fit_reference([0.9] * 100)
    report = m.observe([0.1] * 5)
    assert report.alert is False and report.severity == "none"


def test_drift_no_reference_raises():
    with pytest.raises(ValueError):
        _DriftMonitor2().observe([0.5] * 40)


def test_drift_streaming_api():
    m = _DriftMonitor2()
    for _ in range(100):
        m.observe("a", 0.9)
    assert m.check_drift() is False
    assert m.psi() == pytest.approx(0.0)
    for _ in range(100):
        m.observe("b", 0.9)
    assert m.check_drift() is True
    assert m.psi() > 0.1
    assert m.stream_count() == 200


def test_psi_function_symmetric_labels():
    assert _psi_fn([0.5, 0.5], [0.5, 0.5]) == pytest.approx(0.0)
    assert _psi_fn([1.0, 0.0], [0.0, 1.0]) > 1.0
