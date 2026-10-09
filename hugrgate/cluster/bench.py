"""Cluster benchmark suite. Slice 224.

Loopback-only scenarios measuring the distributed machinery:

- ``remote_decide`` — N ``decide_remote`` calls to one peer:
  latency p50/p95/mean and throughput.
- ``router_failover`` — two peers, the first dropping 50% (seeded
  chaos): success rate and failover share.
- ``distributed_batch`` — N jobs across two peers in one flush:
  envelopes sent, jobs per envelope, throughput.
- ``work_steal`` — a victim queues N jobs, a thief steals them:
  steal throughput.
- ``provenance_sync`` — pull + merge N records: records/s.

``run_cluster_benchmark`` returns a JSON-serializable report dict
(``hugrgate_version``, ``generated_at``, ``platform``, ``config``,
per-scenario metrics). ``python -m hugrgate.cluster.bench`` writes
the artifact; the committed report lives at
``benchmarks/cluster_bench_report.json`` (checksummed — regenerate
with ``--full`` and re-record the checksum).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from dataclasses import dataclass, field

from hugrgate import __version__ as HUGRGATE_VERSION
from hugrgate.cluster.bench_support import (
    LoopbackCluster,
    percent_str,
)
from hugrgate.cluster.chaos import ChaosProxy, FaultInjector
from hugrgate.cluster.distributed_batch import BatchJob
from hugrgate.cluster.work_stealing import StealJob
from hugrgate.core import HugrGate
from hugrgate.errors import BackendError, SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

__all__ = [
    "ClusterBenchConfig",
    "run_cluster_benchmark",
    "scenario_distributed_batch",
    "scenario_provenance_sync",
    "scenario_remote_decide",
    "scenario_router_failover",
    "scenario_work_steal",
]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, int(pct / 100.0 * len(ordered) + 0.5))
    return ordered[min(rank, len(ordered)) - 1]


@dataclass
class ClusterBenchConfig:
    """Knobs for the benchmark run."""

    n_items: int = 200
    chaos_seed: int = 20261009
    policy: DecisionPolicy = field(
        default_factory=lambda: DecisionPolicy(remote_inference=True))
    scenarios: tuple[str, ...] = ("remote_decide", "router_failover",
                                  "distributed_batch", "work_steal",
                                  "provenance_sync")

    def __post_init__(self) -> None:
        if not isinstance(self.n_items, int) or self.n_items < 1:
            raise SpecError("n_items must be a positive int")


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["a", "b"])


def scenario_remote_decide(config: ClusterBenchConfig) -> dict:
    """N remote decisions to one peer; latency + throughput."""
    cluster = LoopbackCluster(["bench-a", "bench-b"])
    peer = cluster.peer_record("bench-b")
    spec = _spec()
    latencies: list[float] = []
    errors = 0
    wall = time.perf_counter()
    for i in range(config.n_items):
        start = time.perf_counter()
        try:
            cluster.node("bench-a").decide_remote(
                peer, spec, {"text": f"item-{i}"}, policy=config.policy)
        except BackendError:
            errors += 1
            continue
        latencies.append((time.perf_counter() - start) * 1000.0)
    wall_s = time.perf_counter() - wall
    return {
        "n_items": config.n_items,
        "n_ok": len(latencies),
        "n_errors": errors,
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
        "latency_mean_ms": (sum(latencies) / len(latencies)
                            if latencies else 0.0),
        "throughput_per_s": (len(latencies) / wall_s) if wall_s > 0 else 0.0,
    }


def scenario_router_failover(config: ClusterBenchConfig) -> dict:
    """Two peers, the first dropping half its traffic (seeded)."""
    cluster = LoopbackCluster(["bench-a", "bench-b", "bench-c"])
    node_a = cluster.node("bench-a")
    # Chaos on bench-b's transport only.
    chaos = ChaosProxy(cluster.transport_for("bench-b"),
                       FaultInjector(drop_rate=0.5, seed=config.chaos_seed))
    cluster.set_transport("bench-b", chaos)
    node_a.discovery.add_adapter(cluster.static_adapter(
        ["bench-b", "bench-c"]))
    # Empty local gate: everything must travel the wire.
    node_a.gate = HugrGate()
    spec = _spec()
    served_by: dict[str, int] = {}
    failed = 0
    latencies: list[float] = []
    wall = time.perf_counter()
    for i in range(config.n_items):
        start = time.perf_counter()
        try:
            result = node_a.router.decide(spec, {"text": f"q{i}"},
                                            policy=config.policy)
        except BackendError:
            failed += 1
            continue
        latencies.append((time.perf_counter() - start) * 1000.0)
        node_id = result.metadata["route"]["node_id"]
        served_by[node_id] = served_by.get(node_id, 0) + 1
    wall_s = time.perf_counter() - wall
    peer_b_id = cluster.node("bench-b").node_id
    return {
        "n_items": config.n_items,
        "n_ok": sum(served_by.values()),
        "n_failed": failed,
        "success_rate": (sum(served_by.values()) / config.n_items
                         if config.n_items else 0.0),
        "served_by_first_peer": served_by.get(peer_b_id, 0),
        "served_by_second_peer": sum(
            n for nid, n in served_by.items() if nid != peer_b_id),
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
        "throughput_per_s": (sum(served_by.values()) / wall_s)
                            if wall_s > 0 else 0.0,
        "chaos": chaos.stats(),
    }


def scenario_distributed_batch(config: ClusterBenchConfig) -> dict:
    """N jobs across two peers in batched flushes."""
    cluster = LoopbackCluster(["bench-a", "bench-b", "bench-c"])
    node_a = cluster.node("bench-a")
    node_a.discovery.add_adapter(cluster.static_adapter(
        ["bench-b", "bench-c"]))
    peer_b = cluster.peer_record("bench-b")
    peer_c = cluster.peer_record("bench-c")
    spec = _spec()
    for i in range(config.n_items):
        peer_id = peer_b.node_id if i % 2 == 0 else peer_c.node_id
        node_a.batcher.submit(peer_id, BatchJob(
            spec=spec, state={"text": f"job-{i}"}, policy=config.policy))
    sent_before = cluster.calls_for("bench-b") + cluster.calls_for("bench-c")
    wall = time.perf_counter()
    outcomes = node_a.batcher.flush()
    wall_s = time.perf_counter() - wall
    sent = (cluster.calls_for("bench-b") + cluster.calls_for("bench-c")
            - sent_before)
    ok = sum(1 for results in outcomes.values()
             for o in results if o.ok)
    total = sum(len(results) for results in outcomes.values())
    return {
        "n_items": config.n_items,
        "n_ok": ok,
        "envelopes_sent": sent,
        "jobs_per_envelope": (total / sent) if sent else 0.0,
        "throughput_per_s": (ok / wall_s) if wall_s > 0 else 0.0,
        "note": percent_str(total, config.n_items) + " of jobs in "
                + str(sent) + " envelopes",
    }


def scenario_work_steal(config: ClusterBenchConfig) -> dict:
    """A victim queues N jobs; a thief steals them all."""
    cluster = LoopbackCluster(["victim", "thief"])
    victim = cluster.node("victim")
    thief = cluster.node("thief")

    spec = _spec()
    for i in range(config.n_items):
        victim.steal_queue.offer(StealJob(
            spec=spec.to_dict(), state={"text": f"job-{i}"}))
    peer = cluster.peer_record("victim")
    wall = time.perf_counter()
    stolen = 0
    rounds = 0
    while len(victim.steal_queue) > 0 and rounds < config.n_items + 10:
        stolen += thief.request_steal(peer, max_jobs=16)
        rounds += 1
    wall_s = time.perf_counter() - wall
    return {
        "n_items": config.n_items,
        "n_stolen": stolen,
        "steal_rounds": rounds,
        "thief_queue": len(thief.steal_queue),
        "throughput_per_s": (stolen / wall_s) if wall_s > 0 else 0.0,
    }


def scenario_provenance_sync(config: ClusterBenchConfig) -> dict:
    """Pull + merge N records from a peer."""
    cluster = LoopbackCluster(["bench-a", "bench-b"])
    node_a = cluster.node("bench-a")
    node_b = cluster.node("bench-b")
    spec = _spec()
    for i in range(config.n_items):
        node_b.gate.decide({"text": f"r{i}"}, spec, config.policy)
    peer = cluster.peer_record("bench-b")
    wall = time.perf_counter()
    added = node_a.provenance_exchange.pull_and_merge(
        peer, limit=config.n_items)
    wall_s = time.perf_counter() - wall
    return {
        "n_items": config.n_items,
        "n_merged": added,
        "records_per_s": (added / wall_s) if wall_s > 0 else 0.0,
        "chain_valid": node_a.gate.provenance.verify_chain(),
    }


_SCENARIOS = {
    "remote_decide": scenario_remote_decide,
    "router_failover": scenario_router_failover,
    "distributed_batch": scenario_distributed_batch,
    "work_steal": scenario_work_steal,
    "provenance_sync": scenario_provenance_sync,
}


def run_cluster_benchmark(
        config: ClusterBenchConfig | None = None) -> dict:
    """Run the selected scenarios; return the JSON report dict."""
    config = config or ClusterBenchConfig()
    report: dict = {
        "hugrgate_version": HUGRGATE_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                     time.localtime()),
        "platform": {"system": platform.system(),
                     "release": platform.release(),
                     "machine": platform.machine(),
                     "python": platform.python_version()},
        "config": {"n_items": config.n_items,
                   "chaos_seed": config.chaos_seed,
                   "scenarios": list(config.scenarios)},
        "scenarios": {},
    }
    for name in config.scenarios:
        scenario = _SCENARIOS.get(name)
        if scenario is None:
            raise SpecError(f"unknown benchmark scenario {name!r}")
        started = time.perf_counter()
        metrics = scenario(config)
        metrics["wall_s"] = time.perf_counter() - started
        report["scenarios"][name] = metrics
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HugrGate cluster benchmark suite (loopback only)")
    parser.add_argument("--out", default="benchmarks/cluster_bench_report.json",
                        help="where to write the JSON report")
    parser.add_argument("--items", type=int, default=200,
                        help="items per scenario")
    parser.add_argument("--scenarios", nargs="*", default=None,
                        help="subset of scenarios to run")
    args = parser.parse_args(argv)
    config = ClusterBenchConfig(n_items=args.items)
    if args.scenarios:
        config.scenarios = tuple(args.scenarios)
    report = run_cluster_benchmark(config)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {args.out} "
          f"({len(report['scenarios'])} scenarios, "
          f"{args.items} items each)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
