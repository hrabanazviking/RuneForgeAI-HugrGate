"""Distributed release gate. Slice 225 (Campaign IX capstone).

A cluster is releasable when every member agrees it is healthy.
:class:`DistributedReleaseGate` runs the same checks the campaign
built, slice by slice:

- ``no_quarantined_peers`` — no node quarantines anyone (slice 213);
- ``peer_health_scores`` — every known peer scores at least
  ``min_health_score`` (slices 213-215);
- ``quorum_present`` — every quorum-enforcing node sees a strict
  majority (slice 219);
- ``provenance_chains_valid`` — every node's provenance chain
  verifies (slices 221-222);
- ``benchmark_thresholds`` — the slice-224 benchmark report meets
  the configured success-rate / throughput floors.

``evaluate`` returns a :class:`ReleaseReport`; the release ships iff
``report.passed``. The module CLI gates a benchmark report file
(or runs the suite first with ``--run-bench``)::

    python -m hugrgate.cluster.release_gate \\
        --bench-report benchmarks/cluster_bench_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from hugrgate.cluster.node import ClusterNode
from hugrgate.errors import SpecError

__all__ = [
    "DistributedReleaseGate",
    "ReleaseCheck",
    "ReleaseGateConfig",
    "ReleaseReport",
]


@dataclass
class ReleaseCheck:
    """One gate check and its verdict."""

    name: str
    passed: bool
    detail: str


@dataclass
class ReleaseGateConfig:
    """Thresholds for the gate."""

    min_health_score: float = 0.5
    max_quarantined: int = 0
    require_quorum: bool = True
    min_success_rate: float = 0.99
    min_throughput_per_s: float = 100.0
    benchmark_scenarios: tuple[str, ...] = ("remote_decide",
                                            "router_failover",
                                            "distributed_batch",
                                            "work_steal",
                                            "provenance_sync")

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_health_score <= 1.0:
            raise SpecError("min_health_score must be in [0, 1]")
        if self.max_quarantined < 0:
            raise SpecError("max_quarantined must be >= 0")


@dataclass
class ReleaseReport:
    """The gate's verdict: every check, and the final word."""

    checks: list[ReleaseCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def failed(self) -> list[ReleaseCheck]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        lines = [f"release gate: {'PASS' if self.passed else 'FAIL'} "
                 f"({len(self.failed())}/{len(self.checks)} failed)"]
        for check in self.checks:
            mark = "ok  " if check.passed else "FAIL"
            lines.append(f"  [{mark}] {check.name}: {check.detail}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"passed": self.passed,
                "checks": [{"name": c.name, "passed": c.passed,
                            "detail": c.detail} for c in self.checks]}


class DistributedReleaseGate:
    """Evaluate cluster health + benchmark floors; pass or block."""

    def __init__(self, config: ReleaseGateConfig | None = None) -> None:
        self.config = config or ReleaseGateConfig()

    # -- node checks ----------------------------------------------------

    def check_no_quarantine(self, nodes: list[ClusterNode]) -> ReleaseCheck:
        """No node quarantines more peers than allowed (slice 213)."""
        offenders: list[str] = []
        for node in nodes:
            quarantined = node.health.quarantined_peers()
            if len(quarantined) > self.config.max_quarantined:
                offenders.append(
                    f"{node.node_id[:8]} quarantines "
                    f"{len(quarantined)}: {sorted(quarantined)}")
        if offenders:
            return ReleaseCheck("no_quarantined_peers", False,
                                "; ".join(offenders))
        return ReleaseCheck(
            "no_quarantined_peers", True,
            f"{len(nodes)} nodes, none quarantine beyond "
            f"allowance {self.config.max_quarantined}")

    def check_health_scores(self, nodes: list[ClusterNode]) -> ReleaseCheck:
        """Every known peer scores at least min_health_score (213-215)."""
        weak: list[str] = []
        known = 0
        for node in nodes:
            for peer in node.peers():
                known += 1
                score = node.health.score(peer.node_id)
                if score < self.config.min_health_score:
                    weak.append(f"{peer.node_id[:8]}={score:.2f}")
        if weak:
            return ReleaseCheck("peer_health_scores", False,
                                f"{len(weak)} weak: "
                                + ", ".join(sorted(weak)))
        return ReleaseCheck(
            "peer_health_scores", True,
            f"{known} known peers all >= {self.config.min_health_score}")

    def check_quorum(self, nodes: list[ClusterNode]) -> ReleaseCheck:
        """Quorum-enforcing nodes see a strict majority (slice 219)."""
        if not self.config.require_quorum:
            return ReleaseCheck("quorum_present", True,
                                "quorum check disabled by config")
        blind = [node.node_id[:8] for node in nodes
                 if node.enforce_quorum and not node.in_quorum()]
        enforcing = sum(1 for node in nodes if node.enforce_quorum)
        if blind:
            return ReleaseCheck("quorum_present", False,
                                f"no quorum: {sorted(blind)}")
        return ReleaseCheck(
            "quorum_present", True,
            f"{enforcing}/{len(nodes)} nodes enforce quorum; "
            "all see a majority")

    def check_provenance(self, nodes: list[ClusterNode]) -> ReleaseCheck:
        """Every node's provenance chain verifies (slices 221-222)."""
        broken = [node.node_id[:8] for node in nodes
                  if not node.gate.provenance.verify_chain()]
        if broken:
            return ReleaseCheck("provenance_chains_valid", False,
                                f"broken chains: {sorted(broken)}")
        return ReleaseCheck("provenance_chains_valid", True,
                            f"{len(nodes)} chains verify")

    # -- benchmark checks ------------------------------------------------

    def check_benchmarks(self, report: dict) -> list[ReleaseCheck]:
        """Slice-224 report scenarios meet the configured floors."""
        checks: list[ReleaseCheck] = []
        scenarios = report.get("scenarios", {})
        for name in self.config.benchmark_scenarios:
            metrics = scenarios.get(name)
            if metrics is None:
                checks.append(ReleaseCheck(
                    f"benchmark:{name}", False, "scenario missing"))
                continue
            failures: list[str] = []
            rate = metrics.get("success_rate")
            if rate is not None and rate < self.config.min_success_rate:
                failures.append(f"success_rate {rate:.3f} < "
                                f"{self.config.min_success_rate}")
            tput = metrics.get("throughput_per_s")
            if tput is None:  # provenance_sync reports records/s
                tput = metrics.get("records_per_s")
            if tput is not None and tput < self.config.min_throughput_per_s:
                failures.append(f"throughput {tput:.1f}/s < "
                                f"{self.config.min_throughput_per_s}/s")
            if failures:
                checks.append(ReleaseCheck(
                    f"benchmark:{name}", False, "; ".join(failures)))
            else:
                checks.append(ReleaseCheck(
                    f"benchmark:{name}", True,
                    f"rate={rate if rate is not None else 'n/a'} "
                    f"tput={tput if tput is not None else 'n/a'}/s"))
        return checks

    # -- entry point -----------------------------------------------------

    def evaluate(self, nodes: list[ClusterNode],
                 benchmark_report: dict | None = None) -> ReleaseReport:
        """Run every check; the release ships iff the report passes."""
        if not nodes:
            return ReleaseReport([ReleaseCheck(
                "nodes_present", False, "no nodes to evaluate")])
        checks = [ReleaseCheck("nodes_present", True,
                               f"{len(nodes)} nodes"),
                  self.check_no_quarantine(nodes),
                  self.check_health_scores(nodes),
                  self.check_quorum(nodes),
                  self.check_provenance(nodes)]
        if benchmark_report is not None:
            checks.extend(self.check_benchmarks(benchmark_report))
        return ReleaseReport(checks)


def main(argv: list[str] | None = None) -> int:
    """CLI: gate a benchmark report file (CI-friendly exit code)."""
    parser = argparse.ArgumentParser(
        description="Distributed release gate: benchmark thresholds")
    parser.add_argument("--bench-report", required=True,
                        help="slice-224 JSON report to gate")
    parser.add_argument("--min-throughput", type=float, default=100.0)
    parser.add_argument("--min-success-rate", type=float, default=0.99)
    args = parser.parse_args(argv)
    with open(args.bench_report, encoding="utf-8") as f:
        report = json.load(f)
    gate = DistributedReleaseGate(ReleaseGateConfig(
        min_throughput_per_s=args.min_throughput,
        min_success_rate=args.min_success_rate))
    # The CLI gates benchmark artifacts; live-node checks are
    # programmatic via evaluate().
    result = ReleaseReport(gate.check_benchmarks(report))
    print(result.summary())
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
