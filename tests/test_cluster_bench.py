"""Tests for slice 224 — cluster benchmark suite.

Fast smoke only (n_items=10): the full run writes its artifact at
commit time, not in the test suite.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.cluster.bench import (
    ClusterBenchConfig,
    run_cluster_benchmark,
)
from hugrgate.cluster.bench_support import LoopbackCluster, percent_str
from hugrgate.errors import SpecError


def _quick(**kwargs):
    kwargs.setdefault("n_items", 10)
    return ClusterBenchConfig(**kwargs)


def test_config_rejects_bad_items():
    with pytest.raises(SpecError):
        ClusterBenchConfig(n_items=0)


def test_unknown_scenario():
    with pytest.raises(SpecError, match="unknown benchmark scenario"):
        run_cluster_benchmark(_quick(scenarios=("nope",)))


def test_report_shape():
    report = run_cluster_benchmark(_quick())
    assert report["hugrgate_version"]
    assert report["generated_at"]
    assert report["platform"]["python"]
    assert report["config"]["n_items"] == 10
    assert set(report["scenarios"]) == {
        "remote_decide", "router_failover", "distributed_batch",
        "work_steal", "provenance_sync"}


def test_remote_decide_metrics():
    metrics = run_cluster_benchmark(
        _quick(scenarios=("remote_decide",)))["scenarios"]["remote_decide"]
    assert metrics["n_ok"] == 10
    assert metrics["n_errors"] == 0
    assert metrics["latency_p50_ms"] >= 0
    assert metrics["latency_p95_ms"] >= metrics["latency_p50_ms"]
    assert metrics["throughput_per_s"] > 0


def test_router_failover_metrics():
    metrics = run_cluster_benchmark(
        _quick(scenarios=("router_failover",)))["scenarios"]["router_failover"]
    assert metrics["n_ok"] + metrics["n_failed"] == 10
    assert 0.0 <= metrics["success_rate"] <= 1.0
    assert metrics["throughput_per_s"] >= 0
    assert metrics["latency_p50_ms"] >= 0


def test_distributed_batch_metrics():
    metrics = run_cluster_benchmark(
        _quick(scenarios=("distributed_batch",)))["scenarios"]["distributed_batch"]
    assert metrics["n_ok"] == 10
    assert metrics["envelopes_sent"] == 2  # one per peer
    assert metrics["jobs_per_envelope"] == pytest.approx(5.0)


def test_work_steal_metrics():
    metrics = run_cluster_benchmark(
        _quick(scenarios=("work_steal",)))["scenarios"]["work_steal"]
    assert metrics["n_stolen"] == 10
    assert metrics["thief_queue"] == 10
    assert metrics["throughput_per_s"] > 0


def test_provenance_sync_metrics():
    metrics = run_cluster_benchmark(
        _quick(scenarios=("provenance_sync",)))["scenarios"]["provenance_sync"]
    assert metrics["n_merged"] == 10
    assert metrics["chain_valid"] is True
    assert metrics["records_per_s"] > 0


def test_report_is_json_serializable():
    report = run_cluster_benchmark(_quick())
    json.dumps(report)


def test_percent_str():
    assert percent_str(1, 4) == "25.0%"
    assert percent_str(0, 0) == "n/a"


def test_loopback_cluster_basics():
    cluster = LoopbackCluster(["a", "b"])
    assert cluster.node("a").node_id != cluster.node("b").node_id
    assert cluster.port_for("a") != cluster.port_for("b")
    assert cluster.name_for_port(cluster.port_for("a")) == "a"
    peer = cluster.peer_record("b")
    assert peer.node_id == cluster.node("b").node_id
    with pytest.raises(KeyError):
        cluster.port_for("ghost")
