"""Slice 074 stress benchmark: routing throughput vs the v1 baseline.

Measures *routing machinery* overhead (not backend work): near-instant
backends with staggered confidences force full climbs every decision.
Each configuration runs real decisions and reports decisions/sec plus
mean/p50/p99 per-decision latency.

Baseline: the v1 LadderRouter serial climb over the same backends and
rungs. v2 configurations: serial executor, parallel, hedged,
early-exit, plus plan-build-only (no execution) to isolate planning
overhead.

Every number is measured on this machine, on this run. No numbers are
invented: rerun to reproduce.

Usage: python benchmarks/routing_stress_074.py [--decisions N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hugrgate import (Backend, BackendRegistry, DecisionPolicy, DecisionResult,
                      DecisionSpec)
from hugrgate.ladder import LadderRouter, LadderRung
from hugrgate.routing import (EarlyExitExecutor, HedgedPlanExecutor,
                              LadderRouterV2, ParallelPlanExecutor,
                              RoutingOptions, SerialPlanExecutor)


class InstantBackend(Backend):
    """Near-zero work; staggered confidence forces full climbs."""

    def __init__(self, name, prob):
        self.name = name
        self._prob = prob

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)

    def estimated_latency(self):
        return 0.5


def build_registry(n_rungs):
    registry = BackendRegistry()
    names = []
    for i in range(n_rungs):
        # all but the last fall below the 0.9 gate: full climb every time
        prob = 0.5 if i < n_rungs - 1 else 0.99
        name = f"rung{i}"
        registry.register(InstantBackend(name, prob))
        names.append(name)
    return registry, names


def percentile(data, pct):
    if not data:
        return 0.0
    ordered = sorted(data)
    k = (len(ordered) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def bench(label, fn, decisions):
    # warmup
    for _ in range(5):
        fn()
    samples = []
    for _ in range(decisions):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    total_s = sum(samples) / 1000.0
    return {
        "label": label,
        "decisions": decisions,
        "decisions_per_sec": round(decisions / total_s, 1),
        "mean_ms": round(statistics.mean(samples), 4),
        "p50_ms": round(percentile(samples, 50), 4),
        "p99_ms": round(percentile(samples, 99), 4),
    }


def _round_floats(obj):
    """Recursively round every float to 6 dp (slice 11: kill float noise)."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v) for v in obj]
    return obj


def main() -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", type=int, default=200)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "routing_stress_074.json"))
    args = ap.parse_args()

    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.9)
    results = []

    for n_rungs in (4, 16):
        registry, names = build_registry(n_rungs)
        rungs = [LadderRung(n, 0.9) for n in names]

        # Baseline: v1 router, serial climb.
        v1 = LadderRouter(registry, rungs=rungs)
        results.append(bench(
            f"v1-baseline/{n_rungs}-rungs",
            lambda: v1.decide({}, spec, policy), args.decisions))

        # v2 serial executor.
        v2 = LadderRouterV2(registry, rungs=rungs,
                            executor=SerialPlanExecutor())
        results.append(bench(
            f"v2-serial/{n_rungs}-rungs",
            lambda: v2.decide({}, spec, policy), args.decisions))

        # v2 plan-build only (no execution): planning overhead isolated.
        results.append(bench(
            f"v2-plan-only/{n_rungs}-rungs",
            lambda: v2.build_plan({}, spec, policy), args.decisions))

        # v2 parallel executor (priority QoS allows fan-out).
        v2p = LadderRouterV2(registry, rungs=rungs,
                             executor=ParallelPlanExecutor())
        popts = RoutingOptions(strategy="parallel", qos="priority",
                               parallel_width=4)
        results.append(bench(
            f"v2-parallel/{n_rungs}-rungs",
            lambda: v2p.decide({}, spec, policy, options=popts),
            args.decisions))

        # v2 hedged executor.
        v2h = LadderRouterV2(registry, rungs=rungs,
                             executor=HedgedPlanExecutor())
        hopts = RoutingOptions(strategy="hedged", qos="priority",
                               hedge_delay_ms=5.0)
        results.append(bench(
            f"v2-hedged/{n_rungs}-rungs",
            lambda: v2h.decide({}, spec, policy, options=hopts),
            args.decisions))

        # v2 early-exit executor.
        v2e = LadderRouterV2(registry, rungs=rungs,
                             executor=EarlyExitExecutor())
        eopts = RoutingOptions(qos="standard", early_exit_delta=0.0,
                               fast_path_probability=0.999)
        results.append(bench(
            f"v2-early-exit/{n_rungs}-rungs",
            lambda: v2e.decide({}, spec, policy, options=eopts),
            args.decisions))

    by_label = {r["label"]: r for r in results}
    comparisons = []
    for n_rungs in (4, 16):
        base = by_label[f"v1-baseline/{n_rungs}-rungs"]
        for variant in ("v2-serial", "v2-parallel", "v2-hedged",
                        "v2-early-exit"):
            row = by_label[f"{variant}/{n_rungs}-rungs"]
            comparisons.append({
                "rungs": n_rungs,
                "variant": variant,
                "vs_v1_baseline": round(
                    row["decisions_per_sec"] / base["decisions_per_sec"],
                    3),
            })

    artifact = {
        "slice": "074",
        "description": "routing throughput: v2 executors vs v1 baseline",
        "decisions_per_config": args.decisions,
        "note": "near-instant backends; staggered confidences force a "
                "full climb every decision, so this measures routing "
                "machinery, not backend work.",
        "results": results,
        "comparisons": comparisons,
    }
    artifact = _round_floats(artifact)
    with open(args.out, "w") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return artifact


if __name__ == "__main__":
    main()
