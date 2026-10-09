"""Run the observability-overhead measurement once; write the artifact.

Slice 336.  Measures the real per-observation cost of the instrumented
path (``HealthDashboard.observe`` → HealthMonitor + registry counter +
histogram) on this host and compares it against the explicit baseline:

    baseline: p99 overhead per observation <= 50 microseconds

The artifact is honest about its limits: it measures CPython
wall-clock on one host, not production tail latency under load.

    python benchmarks/observability_overhead_336.py [--n N] [--seed S]
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.observability.dashboard import HealthDashboard
from hugrgate.observability.metrics import MetricRegistry

BASELINE_P99_US = 50.0


def _measure(n: int, seed: int) -> dict:
    rng = random.Random(seed)
    dash = HealthDashboard(registry=MetricRegistry(max_series=10000))
    latencies = [rng.uniform(1.0, 50.0) for _ in range(n)]
    # Warm up so one-time costs (series creation) don't pollute p99.
    for latency in latencies[:1000]:
        dash.observe("bench", latency, ok=True, verdict="accept")
    samples: list[float] = []
    for latency in latencies:
        start = time.perf_counter()
        dash.observe("bench", latency, ok=True, verdict="accept")
        samples.append((time.perf_counter() - start) * 1e6)
    ordered = sorted(samples)
    rank = max(1, -(-99 * len(ordered) // 100))  # ceil(0.99 * n)
    p99 = ordered[min(rank, len(ordered)) - 1]
    return {
        "n": n,
        "seed": seed,
        "p50_us": statistics.median(samples),
        "p99_us": p99,
        "max_us": max(samples),
        "baseline_p99_us": BASELINE_P99_US,
        "within_baseline": p99 <= BASELINE_P99_US,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=336)
    ap.add_argument("--out",
                    default="benchmarks/observability_overhead_336.json")
    args = ap.parse_args()
    result = _measure(args.n, args.seed)
    artifact = {
        "slice": 336,
        "recorded_at": time.time(),
        "host": platform.node(),
        "python": platform.python_version(),
        "result": result,
    }
    out = Path(args.out)
    out.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["within_baseline"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
