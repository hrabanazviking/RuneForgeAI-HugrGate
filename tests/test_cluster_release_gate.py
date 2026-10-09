"""Tests for slice 225 — distributed release gate.

Uses the slice-224 LoopbackCluster harness: a healthy cluster passes;
each failure mode (quarantine, weak peer, lost quorum, broken
provenance, slow benchmark) blocks the release individually.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.cluster.bench import ClusterBenchConfig, run_cluster_benchmark
from hugrgate.cluster.bench_support import LoopbackCluster
from hugrgate.cluster.release_gate import (
    DistributedReleaseGate,
    ReleaseGateConfig,
    ReleaseReport,
)
from hugrgate.errors import SpecError


def _healthy_cluster() -> LoopbackCluster:
    cluster = LoopbackCluster(["a", "b", "c"])
    ids = {n: cluster.node(n).node_id for n in ("a", "b", "c")}
    for name in ("a", "b", "c"):
        node = cluster.node(name)
        node.discovery.add_adapter(cluster.static_adapter(["a", "b", "c"]))
        for other in ("a", "b", "c"):
            if other != name:
                node.health.record_success(ids[other])
                node.partition.note_heartbeat(ids[other])
    return cluster


def _nodes(cluster: LoopbackCluster):
    return [cluster.node(n) for n in ("a", "b", "c")]


def test_config_rejects_bad_thresholds():
    with pytest.raises(SpecError):
        ReleaseGateConfig(min_health_score=1.5)
    with pytest.raises(SpecError):
        ReleaseGateConfig(max_quarantined=-1)


def test_healthy_cluster_passes():
    cluster = _healthy_cluster()
    report = DistributedReleaseGate().evaluate(_nodes(cluster))
    assert report.passed, report.summary()


def test_empty_cluster_fails():
    report = DistributedReleaseGate().evaluate([])
    assert not report.passed
    assert report.failed()[0].name == "nodes_present"


def test_quarantine_blocks():
    cluster = _healthy_cluster()
    bad_id = cluster.node("b").node_id
    for _ in range(5):
        cluster.node("a").health.record_failure(bad_id)
    report = DistributedReleaseGate().evaluate(_nodes(cluster))
    assert not report.passed
    names = {c.name for c in report.failed()}
    assert "no_quarantined_peers" in names
    assert "peer_health_scores" in names


def test_lost_quorum_blocks():
    cluster = _healthy_cluster()
    for node in _nodes(cluster):
        node.enforce_quorum = True
    assert all(node.in_quorum() for node in _nodes(cluster))
    # Node a loses sight of everyone: it stands alone, the rest are fine.
    ids = {n: cluster.node(n).node_id for n in ("a", "b", "c")}
    cluster.node("a").partition.forget(ids["b"])
    cluster.node("a").partition.forget(ids["c"])
    report = DistributedReleaseGate().evaluate(_nodes(cluster))
    assert not report.passed
    assert {c.name for c in report.failed()} == {"quorum_present"}


def test_broken_provenance_blocks():
    from hugrgate.core import DecisionPolicy
    from hugrgate.spec import DecisionSpec

    cluster = _healthy_cluster()
    node = cluster.node("a")
    node.gate.decide({"text": "release-check"},
                     DecisionSpec(type="categorical", options=["a", "b"]),
                     DecisionPolicy(remote_inference=True))
    chain = node.gate.provenance
    assert chain.count() > 0, "expected provenance records from the decision"
    chain._records[0].value = "tampered"  # break the hash chain
    assert not chain.verify_chain()
    report = DistributedReleaseGate().evaluate(_nodes(cluster))
    assert not report.passed
    assert {c.name for c in report.failed()} == {"provenance_chains_valid"}


def test_benchmark_thresholds_pass():
    bench_report = run_cluster_benchmark(ClusterBenchConfig(n_items=10))
    gate = DistributedReleaseGate(ReleaseGateConfig(
        min_throughput_per_s=1.0))
    report = ReleaseReport(gate.check_benchmarks(bench_report))
    assert report.passed, report.summary()


def test_benchmark_thresholds_block():
    bench_report = run_cluster_benchmark(ClusterBenchConfig(n_items=10))
    gate = DistributedReleaseGate(ReleaseGateConfig(
        min_throughput_per_s=10**12))  # impossibly fast
    report = ReleaseReport(gate.check_benchmarks(bench_report))
    assert not report.passed
    assert all(c.name.startswith("benchmark:") for c in report.failed())


def test_missing_scenario_blocks():
    gate = DistributedReleaseGate()
    report = ReleaseReport(gate.check_benchmarks({"scenarios": {}}))
    assert not report.passed
    assert all(c.detail == "scenario missing" for c in report.failed())


def test_evaluate_with_benchmarks():
    cluster = _healthy_cluster()
    bench_report = run_cluster_benchmark(ClusterBenchConfig(n_items=10))
    gate = DistributedReleaseGate(ReleaseGateConfig(
        min_throughput_per_s=1.0))
    report = gate.evaluate(_nodes(cluster),
                           benchmark_report=bench_report)
    assert report.passed, report.summary()
    assert any(c.name.startswith("benchmark:") for c in report.checks)


def test_report_shape_and_summary():
    cluster = _healthy_cluster()
    report = DistributedReleaseGate().evaluate(_nodes(cluster))
    as_dict = report.to_dict()
    assert as_dict["passed"] is True
    assert {c["name"] for c in as_dict["checks"]} == {
        "nodes_present", "no_quarantined_peers", "peer_health_scores",
        "quorum_present", "provenance_chains_valid"}
    assert "release gate: PASS" in report.summary()
    json.dumps(as_dict)
