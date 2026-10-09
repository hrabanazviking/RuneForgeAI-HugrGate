"""Memory benchmark suite. Slice 324.

Reproducible throughput measurements for the decision-memory layer:
record, attach_outcome, find (query), recall (retrieval), and
export/import round-trip. Every run is seeded; the artifact records
the seed, host, workload, and per-operation timing distributions
(mean/p50/p95/min/max microseconds), following the
``benchmarks/`` directory conventions.

``benchmarks/memory_bench.json`` is the checked-in baseline — the
first real measurement on this machine. Re-run with
``python -m hugrgate.memory.benchmarks --compare`` to measure again
and print ratios against that baseline. Never invent numbers: every
figure in the artifact was timed.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from hugrgate.memory import (
    DecisionHistory,
    MemoryQuery,
    Outcome,
    export_jsonl,
    import_jsonl,
    recall,
)
from hugrgate.provenance import DecisionRecord

__all__ = [
    "compare_reports",
    "load_artifact",
    "run_memory_benchmarks",
    "save_artifact",
]

#: Default artifact path (relative to the repository root).
DEFAULT_ARTIFACT = "benchmarks/memory_bench.json"


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = q / 100.0 * (len(sorted_values) - 1)
    low = int(rank)
    frac = rank - low
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + frac * (sorted_values[high]
                                       - sorted_values[low])


def _summarize(samples_us: list[float]) -> dict[str, float]:
    ordered = sorted(samples_us)
    return {
        "n": float(len(ordered)),
        "mean_us": statistics.fmean(ordered) if ordered else 0.0,
        "p50_us": _percentile(ordered, 50),
        "p95_us": _percentile(ordered, 95),
        "min_us": ordered[0] if ordered else 0.0,
        "max_us": ordered[-1] if ordered else 0.0,
    }


def _timed(fn, n: int) -> list[float]:
    """Run ``fn(i)`` ``n`` times; return per-call microseconds."""
    samples = []
    for i in range(n):
        start = time.perf_counter()
        fn(i)
        samples.append((time.perf_counter() - start) * 1e6)
    return samples


def run_memory_benchmarks(n_episodes: int = 2000, n_queries: int = 100,
                          n_recalls: int = 50,
                          seed: int = 324) -> dict[str, Any]:
    """Run the memory benchmark workload; return the artifact dict."""
    if n_episodes < 1 or n_queries < 1 or n_recalls < 1:
        raise ValueError("workload sizes must be >= 1")
    rng = random.Random(seed)
    backends = ["local", "remote", "edge"]
    summary: dict[str, dict[str, float]] = {}

    hist = DecisionHistory()

    def make_record(i: int) -> DecisionRecord:
        return DecisionRecord(
            request_hash=f"{i:016x}",
            spec={"type": "binary"},
            backend=rng.choice(backends),
            model="m1",
            value=rng.random() < 0.7,
            probability=rng.random(),
            latency_ms=rng.random() * 50.0,
            metadata={"state_keys": ["q", "ctx"]},
        )

    # 1. record throughput
    ids: list[str] = []

    def do_record(i: int) -> None:
        episode = hist.record(make_record(i))
        assert episode is not None
        ids.append(episode.episode_id)

    summary["record_us"] = _summarize(_timed(do_record, n_episodes))

    # 2. attach_outcome throughput (half the episodes)
    targets = ids[::2]

    def do_attach(i: int) -> None:
        hist.attach_outcome(
            targets[i % len(targets)],
            Outcome(kind="success" if rng.random() < 0.7 else "failure"),
            overwrite=True)

    summary["attach_outcome_us"] = _summarize(
        _timed(do_attach, max(1, n_episodes // 4)))

    # 3. query throughput (mixed filters)
    queries = [
        MemoryQuery(backends={"local"}, limit=20),
        MemoryQuery(has_outcome=True, sort_by="probability"),
        MemoryQuery(min_probability=0.5, max_probability=0.9, limit=50),
        MemoryQuery(tags_any={"t"}, limit=10),
    ]

    def do_find(i: int) -> None:
        hist.find(queries[i % len(queries)])

    summary["find_us"] = _summarize(_timed(do_find, n_queries))

    # 4. recall throughput
    def do_recall(i: int) -> None:
        recall(hist, k=5, backend=rng.choice(backends),
               spec={"type": "binary"}, probability=rng.random())

    summary["recall_us"] = _summarize(_timed(do_recall, n_recalls))

    # 5. export/import round-trip
    def do_export(i: int) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench.jsonl"
            export_jsonl(hist, path)
            import_jsonl(DecisionHistory(), path)

    summary["export_import_us"] = _summarize(_timed(do_export, 5))

    summary["estimate_bytes_us"] = _summarize(
        _timed(lambda i: hist.estimate_bytes(), 20))

    return {
        "slice": 324,
        "seed": seed,
        "host": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "workload": {
            "n_episodes": n_episodes,
            "n_queries": n_queries,
            "n_recalls": n_recalls,
        },
        "episodes_retained": hist.count(),
        "memory_bytes": hist.estimate_bytes(),
        "summary": summary,
    }


def save_artifact(report: dict[str, Any], path: str | Path) -> Path:
    """Write the artifact as pretty JSON; return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True)
                      + "\n", encoding="utf-8")
    return target


def load_artifact(path: str | Path) -> dict[str, Any]:
    """Load a benchmark artifact; ``ValueError`` when malformed."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load benchmark artifact: {exc}") from exc
    if not isinstance(data, dict) or "summary" not in data:
        raise ValueError("not a memory benchmark artifact")
    return data


def compare_reports(new: dict[str, Any],
                    baseline: dict[str, Any]) -> dict[str, Any]:
    """Per-operation mean ratios (new / baseline); < 1.0 is faster.

    Also reports the workload sizes so mismatched comparisons are
    obvious — ratios are only meaningful for identical workloads.
    """
    ratios: dict[str, float] = {}
    for op, stats in new.get("summary", {}).items():
        base_stats = baseline.get("summary", {}).get(op)
        if not base_stats or not base_stats.get("mean_us"):
            continue
        ratios[op] = stats["mean_us"] / base_stats["mean_us"]
    return {
        "ratios": ratios,
        "new_workload": new.get("workload"),
        "baseline_workload": baseline.get("workload"),
        "workloads_match": (new.get("workload")
                            == baseline.get("workload")),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: run benchmarks, save the artifact, optionally compare."""
    parser = argparse.ArgumentParser(
        description="Decision-memory benchmark suite (slice 324)")
    parser.add_argument("--episodes", type=int, default=2000)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--recalls", type=int, default=50)
    parser.add_argument("--seed", type=int, default=324)
    parser.add_argument("--out", default=DEFAULT_ARTIFACT)
    parser.add_argument("--compare", action="store_true",
                        help="compare the new run against the artifact "
                             "already at --out (baseline) without "
                             "overwriting it")
    args = parser.parse_args(argv)

    baseline = None
    if args.compare and Path(args.out).exists():
        baseline = load_artifact(args.out)

    report = run_memory_benchmarks(n_episodes=args.episodes,
                                   n_queries=args.queries,
                                   n_recalls=args.recalls,
                                   seed=args.seed)
    if baseline is not None:
        comparison = compare_reports(report, baseline)
        print(json.dumps(comparison, indent=2, sort_keys=True))
        if not comparison["workloads_match"]:
            print("WARNING: workloads differ; ratios are not comparable",
                  file=sys.stderr)
        print(f"baseline at {args.out} left untouched")
    else:
        save_artifact(report, args.out)
        print(f"wrote {args.out}")
    for op, stats in report["summary"].items():
        print(f"  {op}: mean={stats['mean_us']:.1f}us "
              f"p50={stats['p50_us']:.1f}us p95={stats['p95_us']:.1f}us")
    return 0


if __name__ == "__main__":
    sys.exit(main())
